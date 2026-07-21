CREATE FUNCTION public.mark_entry_processing_failed_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_processing_token uuid,
    p_error_code text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_error_code !~ '^[A-Z][A-Z0-9_]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entries
    SET processing_status = 'failed',
        processing_token = NULL,
        processing_error_code = p_error_code,
        completed_at = NULL
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.claim_failed_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    token uuid := gen_random_uuid();
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entries
    SET processing_status = 'processing',
        processing_token = token,
        processing_error_code = NULL,
        processing_started_at = pg_catalog.now(),
        completed_at = NULL
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'failed';
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN token;
END
$function$;

CREATE FUNCTION public.apply_entry_extraction_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_processing_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb,
    p_past_import boolean DEFAULT false
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    theme_count integer;
    classification_id uuid;
    item jsonb;
    item_index integer;
    selected_theme_id uuid;
    expected_tier text;
    selected_score numeric(6,5);
    candidate_status text := 'pending_approval';
    candidate_source text := NULL;
    candidate_decided_at timestamptz := NULL;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_past_import
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
       OR pg_catalog.jsonb_array_length(p_ideas) > 10
       OR pg_catalog.jsonb_array_length(p_memories) > 10
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid extraction payload';
    END IF;

    PERFORM 1
    FROM public.entries
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND original_theme_config_id = p_theme_config_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    IF EXISTS (SELECT 1 FROM public.entry_classifications WHERE entry_id = p_entry_id) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
    END IF;

    theme_count := pg_catalog.jsonb_array_length(p_themes);
    IF theme_count > 3
       OR (theme_count = 0 AND p_mode IS NOT NULL)
       OR (theme_count = 1 AND p_mode IS DISTINCT FROM 'dominant')
       OR (theme_count >= 2 AND p_mode NOT IN ('dominant', 'balanced'))
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid classification shape';
    END IF;

    INSERT INTO public.entry_classifications (user_id, entry_id, theme_config_id, source, mode)
    VALUES (p_user_id, p_entry_id, p_theme_config_id, 'initial', p_mode)
    RETURNING id INTO classification_id;

    item_index := 0;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_themes)
    LOOP
        item_index := item_index + 1;
        expected_tier := (ARRAY['primary', 'secondary', 'tertiary'])[item_index];
        IF item ->> 'tier' IS DISTINCT FROM expected_tier
           OR item ->> 'key' IS NULL
        THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid theme assignment';
        END IF;
        SELECT id INTO selected_theme_id
        FROM public.themes
        WHERE theme_config_id = p_theme_config_id AND theme_key = item ->> 'key';
        IF selected_theme_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'unknown theme';
        END IF;
        selected_score := CASE
            WHEN theme_count = 1 THEN 1.00000
            WHEN theme_count = 2 AND p_mode = 'dominant' AND item_index = 1 THEN 0.62650
            WHEN theme_count = 2 AND p_mode = 'dominant' THEN 0.37350
            WHEN theme_count = 2 AND p_mode = 'balanced' AND item_index = 1 THEN 0.53330
            WHEN theme_count = 2 AND p_mode = 'balanced' THEN 0.46670
            WHEN theme_count = 3 AND p_mode = 'dominant' AND item_index = 1 THEN 0.52000
            WHEN theme_count = 3 AND p_mode = 'dominant' AND item_index = 2 THEN 0.31000
            WHEN theme_count = 3 AND p_mode = 'dominant' THEN 0.17000
            WHEN theme_count = 3 AND p_mode = 'balanced' AND item_index = 1 THEN 0.40000
            WHEN theme_count = 3 AND p_mode = 'balanced' AND item_index = 2 THEN 0.35000
            ELSE 0.25000
        END;
        INSERT INTO public.entry_themes (
            user_id, classification_id, theme_config_id, theme_id, tier, score
        ) VALUES (
            p_user_id, classification_id, p_theme_config_id, selected_theme_id,
            expected_tier, selected_score
        );
    END LOOP;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_ideas)
    LOOP
        INSERT INTO public.ideas (
            user_id, entry_id, content, status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'content', candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_memories)
    LOOP
        INSERT INTO public.extracted_memories (
            user_id, entry_id, content, status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'content', candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_reflections)
    LOOP
        INSERT INTO public.reflections (
            user_id, entry_id, reflection_type, activity, confidence_score,
            status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'reflection_type', item ->> 'activity',
            (item ->> 'confidence_score')::numeric, candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;

    UPDATE public.entries
    SET processing_status = 'completed',
        processing_token = NULL,
        processing_error_code = NULL,
        completed_at = pg_catalog.now()
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.mark_entry_processing_failed_for_owner(uuid, uuid, uuid, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.claim_failed_entry_for_owner(uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.apply_entry_extraction_for_owner(
    uuid, uuid, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, boolean
) FROM PUBLIC, anon, orion_app, orion_worker;

GRANT EXECUTE ON FUNCTION public.mark_entry_processing_failed_for_owner(uuid, uuid, uuid, text)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.claim_failed_entry_for_owner(uuid, uuid)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.apply_entry_extraction_for_owner(
    uuid, uuid, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, boolean
) TO authenticated;
