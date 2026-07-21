CREATE FUNCTION public.retry_entry_processing_for_owner(
    p_user_id uuid,
    p_entry_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    PERFORM 1
    FROM public.entries
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed'
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    UPDATE public.processing_jobs
    SET status = 'pending', run_after = pg_catalog.now(), attempts = 0,
        worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
        last_error_code = NULL, completed_at = NULL
    WHERE user_id = p_user_id AND entry_id = p_entry_id
      AND job_type = 'entry_processing' AND source_version = p_entry_id::text
      AND status = 'failed'
    RETURNING id INTO job_id;

    IF job_id IS NULL THEN
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version
        ) VALUES (
            p_user_id, p_entry_id, 'entry_processing', p_entry_id::text
        )
        ON CONFLICT (user_id, job_type, source_version) DO NOTHING
        RETURNING id INTO job_id;
    END IF;
    IF job_id IS NULL THEN
        RETURN false;
    END IF;

    UPDATE public.entries
    SET processing_status = 'pending', processing_token = NULL,
        processing_error_code = NULL, processing_started_at = NULL,
        completed_at = NULL
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed';

    UPDATE public.past_entry_imports
    SET status = 'pending', attempts = 0, worker_id = NULL,
        processing_token = NULL, completed_processing_token = NULL,
        heartbeat_at = NULL, last_error_code = NULL, completed_at = NULL
    WHERE entry_id = p_entry_id AND user_id = p_user_id AND status = 'failed';

    RETURN true;
END
$function$;

CREATE OR REPLACE FUNCTION public.submit_text_entry_from_draft_for_owner(
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
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_processing_token IS NULL
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
            original_theme_config_id, processing_status, source_draft_id
        ) VALUES (
            p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
            p_theme_config_id, 'pending', draft_row.id
        );
        UPDATE public.entry_drafts
        SET status = 'submitted', content_envelope = NULL,
            submitted_entry_id = p_entry_id, submitted_at = pg_catalog.now()
        WHERE id = draft_row.id AND user_id = p_user_id;
        PERFORM public.enqueue_processing_job_for_owner(
            p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
        );
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', p_entry_id,
            'processing_token', NULL,
            'processing_status', 'pending',
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
        IF public.retry_entry_processing_for_owner(p_user_id, existing_entry.id) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'entry retry is not current';
        END IF;
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', existing_entry.id,
            'processing_token', NULL,
            'processing_status', 'pending',
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

CREATE OR REPLACE FUNCTION public.create_voice_entry_for_owner(
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
       OR p_processing_token IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status, idempotency_key
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'audio', p_entry_date,
        p_theme_config_id, 'pending', p_idempotency_key
    );
    UPDATE public.voice_entry_actions
    SET status = 'completed', entry_id = p_entry_id
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND effective_date = p_entry_date AND status = 'claimed' AND claim_token = p_claim_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale voice claim';
    END IF;
    PERFORM public.enqueue_processing_job_for_owner(
        p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
    );
    RETURN p_entry_id;
END
$function$;

CREATE OR REPLACE FUNCTION public.queue_past_entry_for_owner(
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
    PERFORM public.enqueue_processing_job_for_owner(
        p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
    );
    RETURN p_entry_id;
END
$function$;

CREATE OR REPLACE FUNCTION public.claim_processing_job(p_worker_id text)
RETURNS TABLE (
    job_id uuid,
    user_id uuid,
    entry_id uuid,
    job_type text,
    source_version text,
    claim_token uuid,
    attempts smallint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    claimed public.processing_jobs%ROWTYPE;
    token uuid := gen_random_uuid();
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.length(pg_catalog.btrim(p_worker_id)) NOT BETWEEN 1 AND 100
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT queued.* INTO claimed
    FROM public.processing_jobs AS queued
    WHERE queued.status = 'pending' AND queued.attempts < 3
      AND queued.run_after <= pg_catalog.now()
    ORDER BY queued.run_after, queued.created_at, queued.id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.processing_jobs AS target
    SET status = 'running', attempts = target.attempts + 1, worker_id = p_worker_id,
        claim_token = token, heartbeat_at = pg_catalog.now(),
        last_error_code = NULL, completed_at = NULL
    WHERE target.id = claimed.id
    RETURNING target.* INTO claimed;
    IF claimed.job_type = 'entry_processing' THEN
        UPDATE public.entries AS target_entry
        SET processing_status = 'processing', processing_token = token,
            processing_error_code = NULL, processing_started_at = pg_catalog.now(),
            completed_at = NULL
        WHERE target_entry.id = claimed.entry_id
          AND target_entry.user_id = claimed.user_id
          AND NOT (
              target_entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS classification
                  WHERE classification.entry_id = target_entry.id
                    AND classification.user_id = target_entry.user_id
              )
          );
        UPDATE public.past_entry_imports AS imported
        SET status = 'running', attempts = claimed.attempts,
            worker_id = p_worker_id, processing_token = token,
            completed_processing_token = NULL, heartbeat_at = pg_catalog.now(),
            last_error_code = NULL, completed_at = NULL
        WHERE imported.entry_id = claimed.entry_id
          AND imported.user_id = claimed.user_id
          AND imported.status = 'pending';
    END IF;
    RETURN QUERY SELECT claimed.id, claimed.user_id, claimed.entry_id,
        claimed.job_type, claimed.source_version, token, claimed.attempts;
END
$function$;

CREATE OR REPLACE FUNCTION public.renew_processing_job(
    p_job_id uuid, p_worker_id text, p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.processing_jobs
    SET heartbeat_at = pg_catalog.now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
      AND claim_token = p_claim_token
    RETURNING * INTO item;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF item.job_type = 'entry_processing' THEN
        UPDATE public.past_entry_imports
        SET heartbeat_at = pg_catalog.now()
        WHERE entry_id = item.entry_id AND user_id = item.user_id
          AND status = 'running' AND worker_id = p_worker_id
          AND processing_token = p_claim_token;
    END IF;
    RETURN true;
END
$function$;

CREATE OR REPLACE FUNCTION public.fail_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_error_code text,
    p_retryable boolean
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
    terminal boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_error_code !~ '^[A-Z][A-Z0-9_]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO item FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND OR item.status <> 'running'
       OR item.worker_id IS DISTINCT FROM p_worker_id
       OR item.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RETURN 'stale';
    END IF;
    terminal := NOT p_retryable OR item.attempts >= 3;
    IF terminal THEN
        UPDATE public.processing_jobs
        SET status = 'failed', worker_id = NULL, heartbeat_at = NULL,
            completed_at = pg_catalog.now(), last_error_code = p_error_code
        WHERE id = item.id;
        IF item.job_type = 'entry_processing' THEN
            UPDATE public.entries
            SET processing_status = 'failed', processing_token = NULL,
                processing_error_code = 'PROCESSING_FAILED', completed_at = NULL
            WHERE id = item.entry_id AND user_id = item.user_id
              AND processing_token = p_claim_token;
            UPDATE public.past_entry_imports
            SET status = 'failed', attempts = item.attempts, worker_id = NULL,
                processing_token = NULL, completed_processing_token = NULL,
                heartbeat_at = NULL, completed_at = pg_catalog.now(),
                last_error_code = p_error_code
            WHERE entry_id = item.entry_id AND user_id = item.user_id
              AND status = 'running' AND processing_token = p_claim_token;
        ELSE
            INSERT INTO public.reflection_user_state (user_id, last_processing_error_code)
            VALUES (item.user_id, p_error_code)
            ON CONFLICT (user_id) DO UPDATE
                SET last_processing_error_code = EXCLUDED.last_processing_error_code;
        END IF;
        RETURN 'failed';
    END IF;
    UPDATE public.processing_jobs
    SET status = 'pending', worker_id = NULL, claim_token = NULL,
        heartbeat_at = NULL, last_error_code = p_error_code,
        run_after = pg_catalog.now() + CASE item.attempts
            WHEN 1 THEN pg_catalog.make_interval(secs => 30)
            ELSE pg_catalog.make_interval(mins => 2)
        END
    WHERE id = item.id;
    IF item.job_type = 'entry_processing' THEN
        UPDATE public.entries
        SET processing_status = 'pending', processing_token = NULL,
            processing_error_code = NULL, processing_started_at = NULL,
            completed_at = NULL
        WHERE id = item.entry_id AND user_id = item.user_id
          AND processing_token = p_claim_token;
        UPDATE public.past_entry_imports
        SET status = 'pending', attempts = item.attempts, worker_id = NULL,
            processing_token = NULL, completed_processing_token = NULL,
            heartbeat_at = NULL, last_error_code = p_error_code, completed_at = NULL
        WHERE entry_id = item.entry_id AND user_id = item.user_id
          AND status = 'running' AND processing_token = p_claim_token;
    END IF;
    RETURN 'pending';
END
$function$;

CREATE OR REPLACE FUNCTION public.recover_stale_processing_jobs(p_stale_before timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
    recovered integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_stale_before IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    FOR item IN
        SELECT * FROM public.processing_jobs
        WHERE status = 'running' AND heartbeat_at < p_stale_before
        ORDER BY heartbeat_at, id
        FOR UPDATE SKIP LOCKED
    LOOP
        IF item.attempts >= 3 THEN
            UPDATE public.processing_jobs
            SET status = 'failed', worker_id = NULL, heartbeat_at = NULL,
                completed_at = pg_catalog.now(), last_error_code = 'WORKER_RETRIES_EXHAUSTED'
            WHERE id = item.id;
            IF item.job_type = 'entry_processing' THEN
                UPDATE public.entries
                SET processing_status = 'failed', processing_token = NULL,
                    processing_error_code = 'PROCESSING_FAILED', completed_at = NULL
                WHERE id = item.entry_id AND user_id = item.user_id
                  AND processing_token = item.claim_token;
                UPDATE public.past_entry_imports
                SET status = 'failed', attempts = item.attempts, worker_id = NULL,
                    processing_token = NULL, completed_processing_token = NULL,
                    heartbeat_at = NULL, completed_at = pg_catalog.now(),
                    last_error_code = 'WORKER_RETRIES_EXHAUSTED'
                WHERE entry_id = item.entry_id AND user_id = item.user_id
                  AND status = 'running' AND processing_token = item.claim_token;
            ELSE
                INSERT INTO public.reflection_user_state (user_id, last_processing_error_code)
                VALUES (item.user_id, 'WORKER_RETRIES_EXHAUSTED')
                ON CONFLICT (user_id) DO UPDATE SET
                    last_processing_error_code = EXCLUDED.last_processing_error_code;
            END IF;
        ELSE
            UPDATE public.processing_jobs
            SET status = 'pending', worker_id = NULL, claim_token = NULL,
                heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED',
                run_after = pg_catalog.now() + CASE item.attempts
                    WHEN 1 THEN pg_catalog.make_interval(secs => 30)
                    ELSE pg_catalog.make_interval(mins => 2)
                END
            WHERE id = item.id;
            IF item.job_type = 'entry_processing' THEN
                UPDATE public.entries
                SET processing_status = 'pending', processing_token = NULL,
                    processing_error_code = NULL, processing_started_at = NULL,
                    completed_at = NULL
                WHERE id = item.entry_id AND user_id = item.user_id
                  AND processing_token = item.claim_token;
                UPDATE public.past_entry_imports
                SET status = 'pending', attempts = item.attempts, worker_id = NULL,
                    processing_token = NULL, completed_processing_token = NULL,
                    heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED',
                    completed_at = NULL
                WHERE entry_id = item.entry_id AND user_id = item.user_id
                  AND status = 'running' AND processing_token = item.claim_token;
            END IF;
        END IF;
        recovered := recovered + 1;
    END LOOP;
    RETURN recovered;
END
$function$;

CREATE FUNCTION public.get_entry_processing_payload(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
)
RETURNS TABLE (
    content_envelope jsonb,
    theme_config_id uuid,
    past_import boolean,
    already_materialized boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT entry.content_envelope, entry.original_theme_config_id,
        EXISTS (
            SELECT 1 FROM public.past_entry_imports AS imported
            WHERE imported.entry_id = entry.id AND imported.user_id = entry.user_id
        ),
        entry.processing_status = 'completed' AND EXISTS (
            SELECT 1 FROM public.entry_classifications AS classification
            WHERE classification.entry_id = entry.id
              AND classification.user_id = entry.user_id
        )
    FROM public.processing_jobs AS job
    JOIN public.entries AS entry
      ON entry.id = job.entry_id AND entry.user_id = job.user_id
    WHERE job.id = p_job_id AND job.job_type = 'entry_processing'
      AND job.status = 'running' AND job.worker_id = p_worker_id
      AND job.claim_token = p_claim_token
      AND (
          (entry.processing_status = 'processing' AND entry.processing_token = p_claim_token)
          OR (
              entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS existing
                  WHERE existing.entry_id = entry.id AND existing.user_id = entry.user_id
              )
          )
      );
END
$function$;

CREATE FUNCTION public.apply_legacy_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
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
DECLARE
    job public.processing_jobs%ROWTYPE;
    imported boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO job FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND OR job.job_type <> 'entry_processing' OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    IF EXISTS (
        SELECT 1 FROM public.entry_classifications
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
    END IF;
    PERFORM pg_catalog.set_config(
        'request.jwt.claims',
        pg_catalog.jsonb_build_object('sub', job.user_id, 'role', 'authenticated')::text,
        true
    );
    PERFORM public.apply_entry_extraction_for_owner(
        job.user_id, job.entry_id, p_claim_token, p_theme_config_id, p_mode,
        p_themes, p_ideas, p_memories, p_reflections, false
    );
    SELECT EXISTS (
        SELECT 1 FROM public.past_entry_imports
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) INTO imported;
    IF imported THEN
        UPDATE public.ideas
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.extracted_memories
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.reflections
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.past_entry_imports
        SET status = 'completed', worker_id = NULL, processing_token = NULL,
            completed_processing_token = p_claim_token, heartbeat_at = NULL,
            completed_at = pg_catalog.now(), last_error_code = NULL
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'running' AND processing_token = p_claim_token;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import audit claim';
        END IF;
    END IF;
    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = job.id;
    RETURN true;
END
$function$;

CREATE FUNCTION public.complete_materialized_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.processing_jobs AS job
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE job.id = p_job_id AND job.job_type = 'entry_processing'
      AND job.status = 'running' AND job.worker_id = p_worker_id
      AND job.claim_token = p_claim_token
      AND EXISTS (
          SELECT 1 FROM public.entries AS entry
          WHERE entry.id = job.entry_id AND entry.user_id = job.user_id
            AND entry.processing_status = 'completed'
            AND EXISTS (
                SELECT 1 FROM public.entry_classifications AS classification
                WHERE classification.entry_id = entry.id
                  AND classification.user_id = entry.user_id
            )
      );
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.enqueue_entry_processing_backfill(
    p_limit integer DEFAULT 100,
    p_run_after timestamptz DEFAULT pg_catalog.now() + pg_catalog.make_interval(mins => 5)
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    enqueued integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_limit NOT BETWEEN 1 AND 100 OR p_run_after IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    WITH selected AS (
        SELECT entry.id, entry.user_id
        FROM public.entries AS entry
        WHERE entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.processing_jobs AS existing
              WHERE existing.user_id = entry.user_id
                AND existing.job_type = 'entry_processing'
                AND existing.source_version = entry.id::text
          )
        ORDER BY entry.created_at, entry.id
        LIMIT p_limit
        FOR UPDATE OF entry SKIP LOCKED
    ), inserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', id::text, p_run_after
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO NOTHING
        RETURNING 1
    )
    SELECT pg_catalog.count(*)::integer INTO enqueued FROM inserted;
    RETURN enqueued;
END
$function$;

-- The generalized processing queue supersedes the historical-import-only
-- worker contract. Remove those worker RPCs so there is a single claim,
-- heartbeat, recovery, completion, and failure path after this migration.
DROP FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
);
DROP FUNCTION public.complete_past_entry_import(uuid, text, uuid);
DROP FUNCTION public.recover_stale_past_entry_imports(timestamptz);
DROP FUNCTION public.renew_past_entry_import(uuid, text, uuid);
DROP FUNCTION public.claim_past_entry_import(text);

REVOKE ALL ON FUNCTION public.retry_entry_processing_for_owner(uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.retry_entry_processing_for_owner(uuid, uuid)
    TO authenticated;

REVOKE ALL ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_legacy_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_legacy_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz)
    TO orion_worker;
