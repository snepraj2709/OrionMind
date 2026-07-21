CREATE TABLE public.voice_entry_actions (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL,
    effective_date date NOT NULL,
    status text NOT NULL DEFAULT 'claimed',
    claim_token uuid NOT NULL,
    entry_id uuid,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    PRIMARY KEY (user_id, idempotency_key),
    CONSTRAINT voice_entry_actions_status_check CHECK (status IN ('claimed', 'completed')),
    CONSTRAINT voice_entry_actions_key_check CHECK (
        idempotency_key = pg_catalog.btrim(idempotency_key)
        AND pg_catalog.length(idempotency_key) BETWEEN 1 AND 128
    ),
    CONSTRAINT voice_entry_actions_lifecycle_check CHECK (
        (status = 'claimed' AND entry_id IS NULL)
        OR (status = 'completed' AND entry_id IS NOT NULL)
    ),
    CONSTRAINT voice_entry_actions_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE
);
CREATE TRIGGER voice_entry_actions_set_updated_at
BEFORE UPDATE ON public.voice_entry_actions
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
ALTER TABLE public.voice_entry_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_entry_actions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.voice_entry_actions FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

ALTER TABLE public.past_entry_imports
    ADD COLUMN completed_processing_token uuid;
ALTER TABLE public.past_entry_imports
    ADD CONSTRAINT past_entry_imports_completion_token_check CHECK (
        (status = 'completed') = (completed_processing_token IS NOT NULL)
    );

CREATE FUNCTION public.claim_voice_action_for_owner(
    p_user_id uuid, p_idempotency_key text, p_effective_date date, p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE action public.voice_entry_actions%ROWTYPE;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.length(p_idempotency_key) NOT BETWEEN 1 AND 128
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-voice:' || p_user_id::text || ':' || p_idempotency_key, 0)
    );
    SELECT * INTO action FROM public.voice_entry_actions
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO public.voice_entry_actions (
            user_id, idempotency_key, effective_date, claim_token
        ) VALUES (p_user_id, p_idempotency_key, p_effective_date, p_claim_token);
        RETURN pg_catalog.jsonb_build_object('outcome', 'claimed', 'claim_token', p_claim_token);
    END IF;
    IF action.effective_date IS DISTINCT FROM p_effective_date THEN
        RETURN pg_catalog.jsonb_build_object('outcome', 'date_conflict');
    END IF;
    IF action.status = 'completed' THEN
        RETURN pg_catalog.jsonb_build_object('outcome', 'replay', 'entry_id', action.entry_id);
    END IF;
    RETURN pg_catalog.jsonb_build_object('outcome', 'in_progress');
END
$function$;

CREATE FUNCTION public.release_voice_action_for_owner(
    p_user_id uuid, p_idempotency_key text, p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    DELETE FROM public.voice_entry_actions
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND status = 'claimed' AND claim_token = p_claim_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.create_voice_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_idempotency_key text,
    p_processing_token uuid,
    p_claim_token uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_idempotency_key IS NULL
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.length(p_idempotency_key) NOT BETWEEN 1 AND 128
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status, processing_token,
        processing_started_at, idempotency_key
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'audio', p_entry_date,
        p_theme_config_id, 'processing', p_processing_token,
        pg_catalog.now(), p_idempotency_key
    );
    UPDATE public.voice_entry_actions
    SET status = 'completed', entry_id = p_entry_id
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND effective_date = p_entry_date AND status = 'claimed' AND claim_token = p_claim_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale voice claim';
    END IF;
    RETURN p_entry_id;
END
$function$;

CREATE FUNCTION public.queue_past_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_fingerprint_key_id text,
    p_request_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_request_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid past entry';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
        p_theme_config_id, 'pending'
    );
    INSERT INTO public.past_entry_imports (
        user_id, entry_id, fingerprint_key_id, request_fingerprint, status
    ) VALUES (
        p_user_id, p_entry_id, p_fingerprint_key_id, p_request_fingerprint, 'pending'
    );
    RETURN p_entry_id;
END
$function$;

CREATE FUNCTION public.claim_past_entry_import(p_worker_id text)
RETURNS TABLE(
    import_id uuid,
    user_id uuid,
    entry_id uuid,
    processing_token uuid,
    content_envelope jsonb,
    theme_config_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    claimed public.past_entry_imports%ROWTYPE;
    token uuid := gen_random_uuid();
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.length(pg_catalog.btrim(p_worker_id)) NOT BETWEEN 1 AND 100
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO claimed
    FROM public.past_entry_imports
    WHERE status = 'pending' AND attempts < 3
    ORDER BY created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.past_entry_imports
    SET status = 'running', attempts = attempts + 1, worker_id = p_worker_id,
        processing_token = token, completed_processing_token = NULL,
        heartbeat_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = claimed.id;
    UPDATE public.entries AS entry
    SET processing_status = 'processing', processing_token = token,
        processing_error_code = NULL, processing_started_at = pg_catalog.now(), completed_at = NULL
    WHERE entry.id = claimed.entry_id AND entry.user_id = claimed.user_id;
    RETURN QUERY
    SELECT claimed.id, claimed.user_id, claimed.entry_id, token,
        entry.content_envelope, entry.original_theme_config_id
    FROM public.entries AS entry
    WHERE entry.id = claimed.entry_id AND entry.user_id = claimed.user_id;
END
$function$;

CREATE FUNCTION public.renew_past_entry_import(
    p_import_id uuid, p_worker_id text, p_processing_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.past_entry_imports SET heartbeat_at = pg_catalog.now()
    WHERE id = p_import_id AND status = 'running' AND worker_id = p_worker_id
      AND processing_token = p_processing_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.recover_stale_past_entry_imports(p_stale_before timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE item record; recovered integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    FOR item IN
        SELECT id, user_id, entry_id, attempts FROM public.past_entry_imports
        WHERE status = 'running' AND heartbeat_at < p_stale_before
        FOR UPDATE SKIP LOCKED
    LOOP
        IF item.attempts < 3 THEN
            UPDATE public.past_entry_imports
            SET status = 'pending', worker_id = NULL, processing_token = NULL,
                heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED'
            WHERE id = item.id;
            UPDATE public.entries
            SET processing_status = 'pending', processing_token = NULL,
                processing_error_code = NULL, processing_started_at = NULL
            WHERE id = item.entry_id AND user_id = item.user_id;
        ELSE
            UPDATE public.past_entry_imports
            SET status = 'failed', worker_id = NULL, processing_token = NULL,
                heartbeat_at = NULL, completed_at = pg_catalog.now(),
                last_error_code = 'WORKER_RETRIES_EXHAUSTED'
            WHERE id = item.id;
            UPDATE public.entries
            SET processing_status = 'failed', processing_token = NULL,
                processing_error_code = 'PROCESSING_FAILED'
            WHERE id = item.entry_id AND user_id = item.user_id;
        END IF;
        recovered := recovered + 1;
    END LOOP;
    RETURN recovered;
END
$function$;

CREATE FUNCTION public.complete_past_entry_import(
    p_import_id uuid, p_worker_id text, p_processing_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.past_entry_imports AS import
    SET status = 'completed', worker_id = NULL, processing_token = NULL,
        completed_processing_token = p_processing_token,
        heartbeat_at = NULL, completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE import.id = p_import_id AND import.status = 'running'
      AND import.worker_id = p_worker_id
      AND import.processing_token = p_processing_token
      AND EXISTS (
          SELECT 1 FROM public.entries e
          WHERE e.id = import.entry_id AND e.user_id = import.user_id
            AND e.processing_status = 'completed'
      );
    GET DIAGNOSTICS changed = ROW_COUNT;
    IF changed = 1 THEN
        RETURN true;
    END IF;
    RETURN EXISTS (
        SELECT 1 FROM public.past_entry_imports AS import
        WHERE import.id = p_import_id AND import.status = 'completed'
          AND import.completed_processing_token = p_processing_token
    );
END
$function$;

CREATE FUNCTION public.apply_past_entry_extraction(
    p_import_id uuid,
    p_worker_id text,
    p_processing_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE item public.past_entry_imports%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO item FROM public.past_entry_imports WHERE id = p_import_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import claim';
    END IF;
    IF item.status = 'completed' AND item.completed_processing_token = p_processing_token THEN
        RETURN true;
    END IF;
    IF item.status <> 'running' OR item.worker_id IS DISTINCT FROM p_worker_id
       OR item.processing_token IS DISTINCT FROM p_processing_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import claim';
    END IF;
    PERFORM pg_catalog.set_config(
        'request.jwt.claims',
        pg_catalog.jsonb_build_object('sub', item.user_id, 'role', 'authenticated')::text,
        true
    );
    PERFORM public.apply_entry_extraction_for_owner(
        item.user_id, item.entry_id, p_processing_token, p_theme_config_id, p_mode,
        p_themes, p_ideas, p_memories, p_reflections, false
    );
    UPDATE public.ideas SET status = 'approved', decision_source = 'past_import_auto',
        decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.extracted_memories SET status = 'approved',
        decision_source = 'past_import_auto', decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.reflections SET status = 'approved', decision_source = 'past_import_auto',
        decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.past_entry_imports
    SET status = 'completed', worker_id = NULL, processing_token = NULL,
        completed_processing_token = p_processing_token,
        heartbeat_at = NULL, completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = p_import_id AND processing_token = p_processing_token;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.claim_voice_action_for_owner(uuid, text, date, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.release_voice_action_for_owner(uuid, text, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.create_voice_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.queue_past_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.claim_voice_action_for_owner(uuid, text, date, uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.release_voice_action_for_owner(uuid, text, uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.create_voice_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, uuid, uuid)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.queue_past_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, text)
    TO authenticated;

REVOKE ALL ON FUNCTION public.claim_past_entry_import(text) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.renew_past_entry_import(uuid, text, uuid) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.recover_stale_past_entry_imports(timestamptz) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_past_entry_import(uuid, text, uuid) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;
GRANT EXECUTE ON FUNCTION public.claim_past_entry_import(text) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.renew_past_entry_import(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.recover_stale_past_entry_imports(timestamptz) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_past_entry_import(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
