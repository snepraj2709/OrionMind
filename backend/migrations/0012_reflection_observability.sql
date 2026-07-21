-- P0-09C: worker-only queue observations and scheduler outcome counts.

DROP FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[]);

CREATE FUNCTION public.schedule_reflection_jobs_observed(
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
        IF (
            state.new_valid_entries >= 3
            OR (
                state.new_valid_entries >= 2
                AND pg_catalog.cardinality(state.pending_local_dates) >= 2
            )
        ) AND state.new_accepted_signals >= 1
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

CREATE FUNCTION public.schedule_reflection_jobs(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
    SELECT COALESCE(
        (public.schedule_reflection_jobs_observed(
            p_now, p_execution_mode, p_user_ids
        )->>'enqueued')::integer,
        0
    )
$function$;

CREATE FUNCTION public.get_processing_queue_observability()
RETURNS TABLE (
    job_type text,
    queue_depth bigint,
    oldest_pending_seconds bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
    SELECT requested.job_type,
        pg_catalog.count(queued.id)::bigint AS queue_depth,
        COALESCE(
            pg_catalog.floor(
                pg_catalog.date_part(
                    'epoch', pg_catalog.now() - pg_catalog.min(queued.created_at)
                )
            )::bigint,
            0
        ) AS oldest_pending_seconds
    FROM (
        VALUES ('entry_processing'::text), ('reflection_synthesis'::text)
    ) AS requested(job_type)
    LEFT JOIN public.processing_jobs AS queued
      ON queued.job_type = requested.job_type
     AND queued.status = 'pending'
    WHERE pg_catalog.current_setting('role', true) = 'orion_worker'
    GROUP BY requested.job_type
    ORDER BY requested.job_type
$function$;

REVOKE ALL ON FUNCTION public.schedule_reflection_jobs_observed(
    timestamptz, text, uuid[]
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.schedule_reflection_jobs(
    timestamptz, text, uuid[]
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_processing_queue_observability()
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs_observed(
    timestamptz, text, uuid[]
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs(
    timestamptz, text, uuid[]
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_processing_queue_observability()
    TO orion_worker;
