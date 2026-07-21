-- P0-04 combined entry analysis. The worker now persists legacy extraction,
-- quality audit, accepted signals, lifecycle state, and reflection counters in
-- one claim-bound transaction.

DROP FUNCTION public.get_entry_processing_payload(uuid, text, uuid);

CREATE FUNCTION public.get_entry_processing_payload(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
)
RETURNS TABLE (
    content_envelope jsonb,
    theme_config_id uuid,
    entry_date date,
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
    SELECT entry.content_envelope, entry.original_theme_config_id, entry.entry_date,
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

CREATE FUNCTION public.get_entry_quality_history(
    p_user_id uuid,
    p_entry_id uuid,
    p_entry_date date
)
RETURNS TABLE (
    duplicate_cluster_key text,
    ngram_sketch text[],
    eligibility text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_entry_date IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT analysis.duplicate_cluster_key, analysis.ngram_sketch, analysis.eligibility
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.entry_id <> p_entry_id
      AND entry.entry_date BETWEEN p_entry_date - 90 AND p_entry_date
    ORDER BY analysis.source_version DESC
    LIMIT 1000;
END
$function$;

CREATE FUNCTION public.apply_combined_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb,
    p_analysis jsonb,
    p_signals jsonb,
    p_apply_legacy boolean
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    imported boolean;
    analysis_payload jsonb := p_analysis;
    signals_payload jsonb := p_signals;
    existing_source_version bigint;
    reason_codes jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
       OR pg_catalog.jsonb_typeof(p_analysis) <> 'object'
       OR pg_catalog.jsonb_typeof(p_signals) <> 'array'
       OR p_apply_legacy IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO job FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    IF job.job_type = 'entry_processing' AND job.status = 'completed'
       AND job.claim_token = p_claim_token
    THEN
        SELECT source_version INTO existing_source_version
        FROM public.entry_analyses
        WHERE entry_id = job.entry_id AND user_id = job.user_id;
        IF existing_source_version IS NOT NULL THEN
            RETURN existing_source_version;
        END IF;
    END IF;
    IF job.job_type <> 'entry_processing' OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    IF EXISTS (
        SELECT 1 FROM public.entry_analyses
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'entry analysis already persisted';
    END IF;

    -- Close the exact-duplicate race under the same per-user lock that protects
    -- counters. The Python gate supplies the canonical cluster fingerprint.
    IF analysis_payload ->> 'eligibility' = 'accepted'
       AND NULLIF(analysis_payload ->> 'duplicate_cluster_key', '') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM public.entry_analyses AS existing
           WHERE existing.user_id = job.user_id
             AND existing.eligibility = 'accepted'
             AND existing.duplicate_cluster_key =
                 analysis_payload ->> 'duplicate_cluster_key'
       )
    THEN
        SELECT pg_catalog.to_jsonb(ARRAY(
            SELECT code
            FROM (
                SELECT DISTINCT code
                FROM pg_catalog.jsonb_array_elements_text(
                    COALESCE(
                        analysis_payload -> 'exclusion_reason_codes',
                        '[]'::jsonb
                    ) || '["EXACT_DUPLICATE"]'::jsonb
                ) AS reason(code)
                ORDER BY code
                LIMIT 10
            ) AS distinct_codes
        )) INTO reason_codes;
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{eligibility}', '"excluded"'::jsonb
        );
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{exclusion_reason_codes}', reason_codes
        );
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{deterministic_features,exact_duplicate}', 'true'::jsonb
        );
        signals_payload := '[]'::jsonb;
    END IF;

    IF p_apply_legacy THEN
        IF EXISTS (
            SELECT 1 FROM public.entry_classifications
            WHERE entry_id = job.entry_id AND user_id = job.user_id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
        END IF;
        PERFORM pg_catalog.set_config(
            'request.jwt.claims',
            pg_catalog.jsonb_build_object(
                'sub', job.user_id, 'role', 'authenticated'
            )::text,
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
    ELSIF NOT EXISTS (
        SELECT 1 FROM public.entries AS entry
        WHERE entry.id = job.entry_id AND entry.user_id = job.user_id
          AND entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'materialized entry is invalid';
    END IF;

    RETURN public.apply_entry_analysis(
        p_job_id, p_worker_id, p_claim_token, analysis_payload, signals_payload
    );
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_entry_processing_backfill(
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
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = entry.id
                AND analysis.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.processing_jobs AS running
              WHERE running.user_id = entry.user_id
                AND running.job_type = 'entry_processing'
                AND running.source_version = entry.id::text
                AND running.status IN ('pending', 'running')
          )
        ORDER BY entry.created_at, entry.id
        LIMIT p_limit
        FOR UPDATE OF entry SKIP LOCKED
    ), upserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', id::text, p_run_after
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
            status = 'pending', run_after = EXCLUDED.run_after, attempts = 0,
            worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
            last_error_code = NULL, completed_at = NULL
        WHERE public.processing_jobs.status IN ('completed', 'failed')
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = public.processing_jobs.entry_id
                AND analysis.user_id = public.processing_jobs.user_id
          )
        RETURNING 1
    )
    SELECT pg_catalog.count(*)::integer INTO enqueued FROM upserted;
    RETURN enqueued;
END
$function$;

DROP FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid);

REVOKE ALL ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_entry_quality_history(uuid, uuid, date)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_combined_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, boolean
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_entry_quality_history(uuid, uuid, date)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_combined_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, boolean
) TO orion_worker;
