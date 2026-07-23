-- Owner-scoped, durable, idempotent Reflection recalculation request.
-- The HTTP request only queues work; synthesis remains worker-only.

CREATE FUNCTION public.get_reflection_recalculation_basis_for_owner(
    p_user_id uuid,
    p_now timestamptz DEFAULT pg_catalog.now()
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    owner_timezone text;
    target_source bigint := 0;
    current_end date;
    current_start date;
    basis_valid integer := 0;
    basis_excluded integer := 0;
    basis_dates integer := 0;
    basis_words integer := 0;
    excluded_reasons jsonb := '{}'::jsonb;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_user_id IS NULL
       OR p_now IS NULL
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'operation not permitted';
    END IF;

    SELECT profile.timezone
    INTO owner_timezone
    FROM public.user_profiles AS profile
    WHERE profile.user_id = p_user_id;
    IF owner_timezone IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0002',
            MESSAGE = 'profile not found';
    END IF;

    SELECT state.latest_accepted_source_version
    INTO target_source
    FROM public.reflection_user_state AS state
    WHERE state.user_id = p_user_id;
    target_source := COALESCE(target_source, 0);

    SELECT pg_catalog.max(entry.entry_date)
    INTO current_end
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id
     AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.eligibility = 'accepted'
      AND analysis.source_version <= target_source
      AND EXISTS (
          SELECT 1
          FROM public.entry_signals AS signal
          JOIN public.review_items AS review
            ON review.entry_signal_id = signal.id
           AND review.user_id = signal.user_id
          WHERE signal.analysis_id = analysis.id
            AND signal.user_id = analysis.user_id
            AND review.scope = 'entry_insight'
            AND review.reflection_eligible
            AND review.evidence_weight > 0
      );

    IF current_end IS NULL THEN
        SELECT pg_catalog.max(entry.entry_date)
        INTO current_end
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id
         AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.source_version <= target_source;
    END IF;
    current_end := COALESCE(
        current_end,
        (p_now AT TIME ZONE owner_timezone)::date
    );
    current_start := current_end - 89;

    WITH basis_rows AS (
        SELECT
            analysis.eligibility,
            analysis.entry_kind,
            analysis.reflective_word_count,
            entry.entry_date,
            (
                analysis.eligibility = 'accepted'
                AND EXISTS (
                    SELECT 1
                    FROM public.entry_signals AS signal
                    JOIN public.review_items AS review
                      ON review.entry_signal_id = signal.id
                     AND review.user_id = signal.user_id
                    WHERE signal.analysis_id = analysis.id
                      AND signal.user_id = analysis.user_id
                      AND review.scope = 'entry_insight'
                      AND review.reflection_eligible
                      AND review.evidence_weight > 0
                )
            ) AS included
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id
         AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.source_version <= target_source
          AND entry.entry_date BETWEEN current_start AND current_end
    )
    SELECT
        pg_catalog.count(*) FILTER (WHERE included)::integer,
        pg_catalog.count(*) FILTER (
            WHERE eligibility <> 'accepted'
        )::integer,
        pg_catalog.count(DISTINCT entry_date) FILTER (
            WHERE included
        )::integer,
        COALESCE(
            pg_catalog.sum(reflective_word_count) FILTER (WHERE included),
            0
        )::integer
    INTO basis_valid, basis_excluded, basis_dates, basis_words
    FROM basis_rows;

    SELECT COALESCE(
        pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total),
        '{}'::jsonb
    )
    INTO excluded_reasons
    FROM (
        SELECT analysis.entry_kind,
               pg_catalog.count(*)::integer AS total
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id
         AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.source_version <= target_source
          AND analysis.eligibility <> 'accepted'
          AND entry.entry_date BETWEEN current_start AND current_end
        GROUP BY analysis.entry_kind
        ORDER BY analysis.entry_kind
    ) AS summary;

    RETURN pg_catalog.jsonb_build_object(
        'basis_start', current_start,
        'basis_end', current_end,
        'valid_entry_count', basis_valid,
        'excluded_entry_count', basis_excluded,
        'distinct_entry_dates', basis_dates,
        'reflective_word_count', basis_words,
        'excluded_reasons', excluded_reasons
    );
END
$function$;

CREATE FUNCTION public.request_reflection_recalculation_for_owner(
    p_user_id uuid,
    p_now timestamptz DEFAULT pg_catalog.now()
)
RETURNS TABLE (
    request_outcome text,
    requested_job_id uuid,
    requested_source_version bigint,
    valid_entry_count integer,
    distinct_entry_dates integer,
    reflective_word_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    state public.reflection_user_state%ROWTYPE;
    existing_job public.processing_jobs%ROWTYPE;
    target_source bigint := 0;
    basis_payload jsonb;
    basis_valid integer := 0;
    basis_dates integer := 0;
    basis_words integer := 0;
    snapshot_stale boolean := false;
    result_job_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_user_id IS NULL
       OR p_now IS NULL
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501',
            MESSAGE = 'operation not permitted';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'orion-reflection:' || p_user_id::text,
            0
        )
    );

    SELECT *
    INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id
    FOR UPDATE;

    IF FOUND THEN
        target_source := state.latest_accepted_source_version;
        SELECT snapshot.status = 'stale'
        INTO snapshot_stale
        FROM public.reflection_snapshots AS snapshot
        WHERE snapshot.id = state.last_successful_snapshot_id
          AND snapshot.user_id = p_user_id;
        snapshot_stale := COALESCE(snapshot_stale, false);
    END IF;

    basis_payload := public.get_reflection_recalculation_basis_for_owner(
        p_user_id,
        p_now
    );
    basis_valid := (basis_payload ->> 'valid_entry_count')::integer;
    basis_dates := (basis_payload ->> 'distinct_entry_dates')::integer;
    basis_words := (basis_payload ->> 'reflective_word_count')::integer;

    IF state.user_id IS NULL OR target_source <= 0 THEN
        RETURN QUERY
        SELECT 'not_eligible'::text, NULL::uuid, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    SELECT *
    INTO existing_job
    FROM public.processing_jobs
    WHERE user_id = p_user_id
      AND job_type = 'reflection_synthesis'
      AND source_version = target_source::text
    ORDER BY created_at DESC, id DESC
    LIMIT 1
    FOR UPDATE;

    IF FOUND AND existing_job.status = 'pending' THEN
        UPDATE public.processing_jobs
        SET execution_mode = 'publish',
            priority = 80,
            run_after = LEAST(run_after, p_now),
            updated_at = p_now
        WHERE id = existing_job.id;
        UPDATE public.reflection_user_state
        SET last_processing_error_code = NULL,
            updated_at = p_now
        WHERE user_id = p_user_id;
        RETURN QUERY
        SELECT 'accepted'::text, existing_job.id, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    IF FOUND
       AND existing_job.status = 'running'
       AND existing_job.execution_mode = 'publish'
    THEN
        UPDATE public.reflection_user_state
        SET last_processing_error_code = NULL,
            updated_at = p_now
        WHERE user_id = p_user_id;
        RETURN QUERY
        SELECT 'accepted'::text, existing_job.id, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    IF NOT snapshot_stale
       AND state.last_successful_snapshot_id IS NOT NULL
       AND state.last_snapshot_source_version >= target_source
    THEN
        RETURN QUERY
        SELECT 'already_current'::text,
               CASE WHEN FOUND THEN existing_job.id ELSE NULL::uuid END,
               target_source, basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    IF FOUND
       AND (
           existing_job.status = 'failed'
           OR (
               existing_job.status = 'completed'
               AND existing_job.execution_mode = 'shadow'
           )
       )
    THEN
        UPDATE public.processing_jobs
        SET status = 'pending',
            execution_mode = 'publish',
            priority = 80,
            run_after = p_now,
            attempts = 0,
            worker_id = NULL,
            claim_token = NULL,
            heartbeat_at = NULL,
            last_error_code = NULL,
            completed_at = NULL,
            updated_at = p_now
        WHERE id = existing_job.id;
        UPDATE public.reflection_user_state
        SET last_processing_error_code = NULL,
            updated_at = p_now
        WHERE user_id = p_user_id;
        RETURN QUERY
        SELECT 'accepted'::text, existing_job.id, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    IF FOUND THEN
        RETURN QUERY
        SELECT 'unavailable'::text, existing_job.id, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    IF NOT snapshot_stale
       AND (
           basis_valid < 3
           OR basis_dates < 2
           OR basis_words < 150
       )
    THEN
        RETURN QUERY
        SELECT 'not_eligible'::text, NULL::uuid, target_source,
               basis_valid, basis_dates, basis_words;
        RETURN;
    END IF;

    INSERT INTO public.processing_jobs (
        user_id,
        entry_id,
        job_type,
        execution_mode,
        priority,
        source_version,
        status,
        run_after
    )
    VALUES (
        p_user_id,
        NULL,
        'reflection_synthesis',
        'publish',
        80,
        target_source::text,
        'pending',
        p_now
    )
    RETURNING id INTO result_job_id;

    UPDATE public.reflection_user_state
    SET last_processing_error_code = NULL,
        updated_at = p_now
    WHERE user_id = p_user_id;

    RETURN QUERY
    SELECT 'accepted'::text, result_job_id, target_source,
           basis_valid, basis_dates, basis_words;
END
$function$;

REVOKE ALL ON FUNCTION public.get_reflection_recalculation_basis_for_owner(
    uuid,
    timestamptz
) FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.request_reflection_recalculation_for_owner(
    uuid,
    timestamptz
) FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.get_reflection_recalculation_basis_for_owner(
    uuid,
    timestamptz
) TO authenticated;
GRANT EXECUTE ON FUNCTION public.request_reflection_recalculation_for_owner(
    uuid,
    timestamptz
) TO authenticated;

COMMENT ON FUNCTION public.get_reflection_recalculation_basis_for_owner(
    uuid,
    timestamptz
) IS
'Owner-only, Review-weighted 90-day basis used by cached Reflection reads and recalculation requests.';
COMMENT ON FUNCTION public.request_reflection_recalculation_for_owner(
    uuid,
    timestamptz
) IS
'Owner-only durable recalculation request. Reuses a current pending/running publish job and never performs synthesis inline.';
