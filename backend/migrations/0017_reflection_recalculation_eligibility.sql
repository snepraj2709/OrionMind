-- Centralize incremental recalculation eligibility so scheduler and aggregate
-- reads cannot disagree or trigger synthesis after only one recent entry.

CREATE FUNCTION public.is_reflection_recalculation_eligible(
    p_user_id uuid,
    p_now timestamptz
)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    state public.reflection_user_state%ROWTYPE;
    pending_valid_entries integer;
    pending_reflective_words bigint;
    oldest_pending_valid_entry_at timestamptz;
    has_pending_signal boolean;
    current_end date;
    current_start date;
    basis_valid_entries integer;
    basis_distinct_dates integer;
    basis_reflective_words bigint;
BEGIN
    IF p_user_id IS NULL OR p_now IS NULL THEN
        RETURN false;
    END IF;

    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id;
    IF NOT FOUND
       OR state.latest_accepted_source_version <= state.last_snapshot_source_version
    THEN
        RETURN false;
    END IF;

    SELECT pg_catalog.count(*)::integer,
           COALESCE(pg_catalog.sum(analysis.reflective_word_count), 0)::bigint,
           pg_catalog.min(entry.created_at)
    INTO pending_valid_entries, pending_reflective_words,
         oldest_pending_valid_entry_at
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.eligibility = 'accepted'
      AND analysis.source_version > state.last_snapshot_source_version;

    IF pending_valid_entries = 0 THEN
        RETURN false;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted'
          AND analysis.source_version > state.last_snapshot_source_version
    ) INTO has_pending_signal;
    IF NOT has_pending_signal THEN
        RETURN false;
    END IF;

    -- A first snapshot still requires the global 3-entry, 2-date, 200-word
    -- basis. Incremental word/age triggers apply only after that first result.
    IF state.last_successful_snapshot_id IS NULL
       OR state.last_snapshot_source_version = 0
    THEN
        SELECT pg_catalog.max(entry.entry_date)
        INTO current_end
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted';
        IF current_end IS NULL THEN
            RETURN false;
        END IF;
        current_start := current_end - 89;
        SELECT pg_catalog.count(*)::integer,
               pg_catalog.count(DISTINCT entry.entry_date)::integer,
               COALESCE(pg_catalog.sum(analysis.reflective_word_count), 0)::bigint
        INTO basis_valid_entries, basis_distinct_dates, basis_reflective_words
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted'
          AND entry.entry_date BETWEEN current_start AND current_end;
        RETURN basis_valid_entries >= 3
           AND basis_distinct_dates >= 2
           AND basis_reflective_words >= 200;
    END IF;

    RETURN pending_valid_entries >= 3
       OR pending_reflective_words >= 500
       OR (
           pending_valid_entries >= 1
           AND oldest_pending_valid_entry_at <= p_now - INTERVAL '3 days'
       );
END
$function$;

CREATE FUNCTION public.request_reflection_synthesis_if_eligible(
    p_user_id uuid,
    p_now timestamptz DEFAULT pg_catalog.now()
)
RETURNS TABLE (requested_job_id uuid, requested_source_version bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    state public.reflection_user_state%ROWTYPE;
    existing_job public.processing_jobs%ROWTYPE;
    target_source bigint;
    result uuid;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_now IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || p_user_id::text, 0)
    );
    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id
    FOR UPDATE;
    IF NOT FOUND
       OR NOT public.is_reflection_recalculation_eligible(p_user_id, p_now)
    THEN
        RETURN;
    END IF;

    SELECT * INTO existing_job
    FROM public.processing_jobs
    WHERE user_id = p_user_id AND job_type = 'reflection_synthesis'
    ORDER BY created_at DESC, id DESC
    LIMIT 1;
    IF FOUND THEN
        IF existing_job.status = 'running' THEN
            RETURN;
        END IF;
        IF existing_job.status = 'pending' THEN
            target_source := existing_job.source_version::bigint;
            IF target_source > state.latest_accepted_source_version THEN
                RETURN;
            END IF;
            result := public.enqueue_processing_job(
                p_user_id,
                NULL,
                'reflection_synthesis',
                target_source::text,
                p_now
            );
            RETURN QUERY SELECT result, target_source;
            RETURN;
        END IF;
        IF existing_job.source_version::bigint >= state.latest_accepted_source_version THEN
            RETURN;
        END IF;
    END IF;

    target_source := state.latest_accepted_source_version;
    result := public.enqueue_processing_job(
        p_user_id,
        NULL,
        'reflection_synthesis',
        target_source::text,
        p_now
    );
    RETURN QUERY SELECT result, target_source;
END
$function$;

CREATE OR REPLACE FUNCTION public.schedule_reflection_jobs_observed(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    profile record;
    state public.reflection_user_state%ROWTYPE;
    local_date date;
    checked integer := 0;
    eligible integer := 0;
    enqueued integer := 0;
    changed integer;
    job_priority smallint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_now IS NULL
       OR p_execution_mode NOT IN ('shadow', 'publish')
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT pg_catalog.count(*)::integer INTO checked
    FROM public.user_profiles
    WHERE user_id = ANY(p_user_ids);
    job_priority := CASE p_execution_mode WHEN 'publish' THEN 80 ELSE 60 END;
    FOR profile IN
        SELECT user_id, timezone
        FROM public.user_profiles
        WHERE user_id = ANY(p_user_ids)
          AND (p_now AT TIME ZONE timezone)::time >= TIME '18:00:00'
        ORDER BY user_id
    LOOP
        local_date := (p_now AT TIME ZONE profile.timezone)::date;
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('orion-reflection:' || profile.user_id::text, 0)
        );
        SELECT * INTO state FROM public.reflection_user_state
        WHERE user_id = profile.user_id FOR UPDATE;
        IF NOT FOUND OR state.last_schedule_local_date >= local_date THEN
            CONTINUE;
        END IF;
        UPDATE public.reflection_user_state
        SET last_schedule_local_date = local_date
        WHERE user_id = profile.user_id;
        IF public.is_reflection_recalculation_eligible(profile.user_id, p_now)
        THEN
            eligible := eligible + 1;
            INSERT INTO public.processing_jobs (
                user_id, entry_id, job_type, execution_mode, priority,
                source_version, run_after
            ) VALUES (
                profile.user_id, NULL, 'reflection_synthesis',
                p_execution_mode, job_priority,
                state.latest_accepted_source_version::text, p_now
            ) ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
                execution_mode = EXCLUDED.execution_mode,
                priority = EXCLUDED.priority,
                status = 'pending',
                run_after = EXCLUDED.run_after,
                attempts = 0,
                worker_id = NULL,
                claim_token = NULL,
                heartbeat_at = NULL,
                last_error_code = NULL,
                completed_at = NULL,
                updated_at = pg_catalog.now()
            WHERE public.processing_jobs.job_type = 'reflection_synthesis'
              AND public.processing_jobs.execution_mode = 'shadow'
              AND EXCLUDED.execution_mode = 'publish'
              AND public.processing_jobs.status IN ('pending', 'completed', 'failed')
              AND NOT EXISTS (
                  SELECT 1 FROM public.reflection_snapshots AS snapshot
                  WHERE snapshot.user_id = public.processing_jobs.user_id
                    AND snapshot.source_version = public.processing_jobs.source_version::bigint
              );
            GET DIAGNOSTICS changed = ROW_COUNT;
            enqueued := enqueued + changed;
        END IF;
    END LOOP;
    RETURN pg_catalog.jsonb_build_object(
        'checked', checked,
        'eligible', eligible,
        'enqueued', enqueued
    );
END
$function$;

REVOKE ALL ON FUNCTION public.is_reflection_recalculation_eligible(uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.request_reflection_synthesis_if_eligible(uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.is_reflection_recalculation_eligible(uuid, timestamptz)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.request_reflection_synthesis_if_eligible(uuid, timestamptz)
    TO orion_worker;
