CREATE FUNCTION public.save_entry_draft_for_owner(
    p_user_id uuid,
    p_draft_id uuid,
    p_content_envelope jsonb,
    p_fingerprint_key_id text,
    p_content_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    active_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_fingerprint_key_id IS NULL
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid draft request';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    SELECT id INTO active_id
    FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active'
    FOR UPDATE;
    IF active_id IS NULL THEN
        INSERT INTO public.entry_drafts (
            id, user_id, content_envelope, fingerprint_key_id, content_fingerprint, status
        ) VALUES (
            p_draft_id, p_user_id, p_content_envelope, p_fingerprint_key_id,
            p_content_fingerprint, 'active'
        );
        RETURN p_draft_id;
    END IF;
    IF active_id IS DISTINCT FROM p_draft_id THEN
        RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'draft changed concurrently';
    END IF;
    UPDATE public.entry_drafts
    SET content_envelope = p_content_envelope,
        fingerprint_key_id = p_fingerprint_key_id,
        content_fingerprint = p_content_fingerprint
    WHERE id = active_id AND user_id = p_user_id AND status = 'active';
    RETURN active_id;
END
$function$;

CREATE FUNCTION public.discard_entry_draft_for_owner(p_user_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    DELETE FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active';
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.submit_text_entry_from_draft_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_fingerprint_key_id text,
    p_content_fingerprint text,
    p_entry_date date,
    p_theme_config_id uuid,
    p_processing_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    draft_row public.entry_drafts%ROWTYPE;
    existing_entry public.entries%ROWTYPE;
    retry_token uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid text submission';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    SELECT * INTO draft_row
    FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active'
    FOR UPDATE;
    IF FOUND THEN
        IF draft_row.fingerprint_key_id IS DISTINCT FROM p_fingerprint_key_id
           OR draft_row.content_fingerprint IS DISTINCT FROM p_content_fingerprint
        THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'draft content mismatch';
        END IF;
        INSERT INTO public.entries (
            id, user_id, content_envelope, input_type, entry_date,
            original_theme_config_id, processing_status, processing_token,
            processing_started_at, source_draft_id
        ) VALUES (
            p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
            p_theme_config_id, 'processing', p_processing_token,
            pg_catalog.now(), draft_row.id
        );
        UPDATE public.entry_drafts
        SET status = 'submitted',
            content_envelope = NULL,
            submitted_entry_id = p_entry_id,
            submitted_at = pg_catalog.now()
        WHERE id = draft_row.id AND user_id = p_user_id;
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', p_entry_id,
            'processing_token', p_processing_token,
            'processing_status', 'processing',
            'created', true,
            'reclaimed', false
        );
    END IF;

    SELECT entry.* INTO existing_entry
    FROM public.entry_drafts AS draft
    JOIN public.entries AS entry ON entry.id = draft.submitted_entry_id
    WHERE draft.user_id = p_user_id
      AND draft.status = 'submitted'
      AND draft.fingerprint_key_id = p_fingerprint_key_id
      AND draft.content_fingerprint = p_content_fingerprint
    ORDER BY draft.submitted_at DESC, draft.id DESC
    LIMIT 1
    FOR UPDATE OF entry;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'matching draft is required';
    END IF;
    IF existing_entry.processing_status = 'failed' THEN
        retry_token := gen_random_uuid();
        UPDATE public.entries
        SET processing_status = 'processing',
            processing_token = retry_token,
            processing_error_code = NULL,
            processing_started_at = pg_catalog.now(),
            completed_at = NULL
        WHERE id = existing_entry.id
          AND user_id = p_user_id
          AND processing_status = 'failed';
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', existing_entry.id,
            'processing_token', retry_token,
            'processing_status', 'processing',
            'created', false,
            'reclaimed', true
        );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
        'entry_id', existing_entry.id,
        'processing_token', NULL,
        'processing_status', existing_entry.processing_status,
        'created', false,
        'reclaimed', false
    );
END
$function$;

REVOKE ALL ON FUNCTION public.save_entry_draft_for_owner(uuid, uuid, jsonb, text, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.discard_entry_draft_for_owner(uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.submit_text_entry_from_draft_for_owner(
    uuid, uuid, jsonb, text, text, date, uuid, uuid
) FROM PUBLIC, anon, orion_app, orion_worker;

GRANT EXECUTE ON FUNCTION public.save_entry_draft_for_owner(uuid, uuid, jsonb, text, text)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.discard_entry_draft_for_owner(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.submit_text_entry_from_draft_for_owner(
    uuid, uuid, jsonb, text, text, date, uuid, uuid
) TO authenticated;
