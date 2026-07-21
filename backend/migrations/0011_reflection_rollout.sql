-- P0-09B: cohort-scoped rollout, real shadow completion, queue priority,
-- and persisted/resumable entry-analysis backfill control.

ALTER TABLE public.processing_jobs
    ADD COLUMN execution_mode text,
    ADD COLUMN priority smallint;

UPDATE public.processing_jobs
SET execution_mode = CASE job_type
        WHEN 'entry_processing' THEN 'user'
        ELSE 'publish'
    END,
    priority = CASE job_type
        WHEN 'entry_processing' THEN 100
        ELSE 80
    END;

ALTER TABLE public.processing_jobs
    ALTER COLUMN execution_mode SET DEFAULT 'user',
    ALTER COLUMN execution_mode SET NOT NULL,
    ALTER COLUMN priority SET DEFAULT 100,
    ALTER COLUMN priority SET NOT NULL,
    ADD CONSTRAINT processing_jobs_execution_mode_check CHECK (
        (job_type = 'entry_processing' AND execution_mode IN ('user', 'backfill'))
        OR (job_type = 'reflection_synthesis' AND execution_mode IN ('shadow', 'publish'))
    ),
    ADD CONSTRAINT processing_jobs_priority_check CHECK (
        (execution_mode = 'user' AND priority = 100)
        OR (execution_mode = 'publish' AND priority = 80)
        OR (execution_mode = 'shadow' AND priority = 60)
        OR (execution_mode = 'backfill' AND priority = 10)
    );

DROP INDEX public.processing_jobs_claim_idx;
CREATE INDEX processing_jobs_claim_idx
    ON public.processing_jobs (priority DESC, run_after, created_at, id)
    WHERE status = 'pending' AND attempts < 3;

CREATE TABLE public.reflection_shadow_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id uuid NOT NULL,
    source_version bigint NOT NULL,
    candidate_count integer NOT NULL,
    selected_count integer NOT NULL,
    provider_called boolean NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (job_id),
    UNIQUE (user_id, source_version),
    CONSTRAINT reflection_shadow_runs_job_owner_fk
        FOREIGN KEY (job_id, user_id)
        REFERENCES public.processing_jobs(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_shadow_runs_counts_check CHECK (
        source_version >= 1
        AND candidate_count >= 0
        AND selected_count >= 0
        AND selected_count <= candidate_count
    )
);

CREATE INDEX reflection_shadow_runs_owner_source_idx
    ON public.reflection_shadow_runs (user_id, source_version DESC);

CREATE TABLE public.processing_backfill_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'planned',
    batch_size smallint NOT NULL,
    max_queue_depth integer NOT NULL,
    max_oldest_pending_seconds integer NOT NULL,
    planned_count integer NOT NULL,
    enqueued_count integer NOT NULL DEFAULT 0,
    cursor_created_at timestamptz,
    cursor_entry_id uuid,
    upper_bound_created_at timestamptz,
    upper_bound_entry_id uuid,
    last_throttle_reason text,
    last_checked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    completed_at timestamptz,
    CONSTRAINT processing_backfill_runs_status_check CHECK (
        status IN ('planned', 'running', 'paused', 'completed')
    ),
    CONSTRAINT processing_backfill_runs_limits_check CHECK (
        batch_size BETWEEN 1 AND 100
        AND max_queue_depth BETWEEN 1 AND 100000
        AND max_oldest_pending_seconds BETWEEN 30 AND 86400
        AND planned_count >= 0
        AND enqueued_count >= 0
        AND enqueued_count <= planned_count
    ),
    CONSTRAINT processing_backfill_runs_cursor_check CHECK (
        (cursor_created_at IS NULL) = (cursor_entry_id IS NULL)
        AND (upper_bound_created_at IS NULL) = (upper_bound_entry_id IS NULL)
    ),
    CONSTRAINT processing_backfill_runs_throttle_check CHECK (
        last_throttle_reason IS NULL
        OR last_throttle_reason IN ('QUEUE_DEPTH', 'OLDEST_PENDING_AGE')
    ),
    CONSTRAINT processing_backfill_runs_lifecycle_check CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    )
);

CREATE UNIQUE INDEX processing_backfill_runs_one_active_idx
    ON public.processing_backfill_runs ((true))
    WHERE status IN ('planned', 'running', 'paused');

CREATE TABLE public.processing_backfill_users (
    run_id uuid NOT NULL REFERENCES public.processing_backfill_runs(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, user_id)
);

CREATE INDEX processing_backfill_users_owner_idx
    ON public.processing_backfill_users (user_id, run_id);

ALTER TABLE public.reflection_shadow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_shadow_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_users FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.reflection_shadow_runs,
    public.processing_backfill_runs, public.processing_backfill_users
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

CREATE OR REPLACE FUNCTION public.enqueue_processing_job_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_source_version text,
    p_run_after timestamptz DEFAULT pg_catalog.now()
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_source_version IS DISTINCT FROM p_entry_id::text
       OR p_run_after IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM public.entries
           WHERE id = p_entry_id AND user_id = p_user_id
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid processing job';
    END IF;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, 'entry_processing', 'user', 100,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_processing_job(
    p_user_id uuid,
    p_entry_id uuid,
    p_job_type text,
    p_source_version text,
    p_run_after timestamptz DEFAULT pg_catalog.now()
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
    mode text;
    job_priority smallint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_job_type NOT IN ('entry_processing', 'reflection_synthesis')
       OR p_run_after IS NULL
       OR (
           p_job_type = 'entry_processing'
           AND (
               p_entry_id IS NULL
               OR p_source_version IS DISTINCT FROM p_entry_id::text
               OR NOT EXISTS (
                   SELECT 1 FROM public.entries
                   WHERE id = p_entry_id AND user_id = p_user_id
               )
           )
       )
       OR (
           p_job_type = 'reflection_synthesis'
           AND (p_entry_id IS NOT NULL OR p_source_version !~ '^[1-9][0-9]*$')
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    mode := CASE p_job_type WHEN 'entry_processing' THEN 'user' ELSE 'publish' END;
    job_priority := CASE p_job_type WHEN 'entry_processing' THEN 100 ELSE 80 END;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, p_job_type, mode, job_priority,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

DROP FUNCTION public.claim_processing_job(text);
CREATE FUNCTION public.claim_processing_job(p_worker_id text)
RETURNS TABLE (
    job_id uuid,
    user_id uuid,
    entry_id uuid,
    job_type text,
    execution_mode text,
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
    ORDER BY queued.priority DESC, queued.run_after, queued.created_at, queued.id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.processing_jobs AS target
    SET status = 'running', attempts = target.attempts + 1, worker_id = p_worker_id,
        claim_token = token, heartbeat_at = pg_catalog.now(),
        last_error_code = NULL, completed_at = NULL,
        updated_at = pg_catalog.now()
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
        claimed.job_type, claimed.execution_mode, claimed.source_version,
        token, claimed.attempts;
END
$function$;

DROP FUNCTION public.schedule_reflection_jobs(timestamptz);
CREATE FUNCTION public.schedule_reflection_jobs(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    profile record;
    state public.reflection_user_state%ROWTYPE;
    local_date date;
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
    RETURN enqueued;
END
$function$;

CREATE FUNCTION public.complete_reflection_shadow(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_candidate_count integer,
    p_selected_count integer,
    p_provider_called boolean
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    result uuid;
    changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_candidate_count < 0
       OR p_selected_count < 0
       OR p_selected_count > p_candidate_count
       OR p_provider_called IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    IF job.status = 'completed'
       AND job.execution_mode = 'shadow'
       AND job.claim_token IS NOT DISTINCT FROM p_claim_token
    THEN
        SELECT id INTO result
        FROM public.reflection_shadow_runs
        WHERE job_id = job.id AND user_id = job.user_id;
        IF result IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
        END IF;
        RETURN result;
    END IF;
    IF job.job_type <> 'reflection_synthesis'
       OR job.execution_mode <> 'shadow'
       OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
       OR job.source_version !~ '^[1-9][0-9]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    INSERT INTO public.reflection_shadow_runs (
        user_id, job_id, source_version, candidate_count,
        selected_count, provider_called
    ) VALUES (
        job.user_id, job.id, job.source_version::bigint, p_candidate_count,
        p_selected_count, p_provider_called
    )
    ON CONFLICT (job_id) DO UPDATE SET job_id = EXCLUDED.job_id
    RETURNING id INTO result;

    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL,
        updated_at = pg_catalog.now()
    WHERE id = job.id AND status = 'running'
      AND worker_id = p_worker_id AND claim_token = p_claim_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    IF changed <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    UPDATE public.reflection_user_state
    SET last_processing_error_code = NULL, updated_at = pg_catalog.now()
    WHERE user_id = job.user_id;
    RETURN result;
END
$function$;

CREATE FUNCTION public.plan_entry_processing_backfill(
    p_user_ids uuid[],
    p_batch_size integer,
    p_max_queue_depth integer,
    p_max_oldest_pending_seconds integer
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
    planned integer;
    upper_created timestamptz;
    upper_id uuid;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR p_batch_size NOT BETWEEN 1 AND 100
       OR p_max_queue_depth NOT BETWEEN 1 AND 100000
       OR p_max_oldest_pending_seconds NOT BETWEEN 30 AND 86400
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
       OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
           WHERE NOT EXISTS (
               SELECT 1 FROM auth.users WHERE id = requested.user_id
           )
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT pg_catalog.count(*)::integer
    INTO planned
    FROM public.entries AS entry
    WHERE entry.user_id = ANY(p_user_ids)
      AND entry.processing_status = 'completed'
      AND EXISTS (
          SELECT 1 FROM public.entry_classifications AS classification
          WHERE classification.entry_id = entry.id
            AND classification.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.entry_analyses AS analysis
          WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.processing_jobs AS active
          WHERE active.user_id = entry.user_id
            AND active.job_type = 'entry_processing'
            AND active.source_version = entry.id::text
            AND active.status IN ('pending', 'running')
      );

    SELECT entry.created_at, entry.id
    INTO upper_created, upper_id
    FROM public.entries AS entry
    WHERE entry.user_id = ANY(p_user_ids)
      AND entry.processing_status = 'completed'
      AND EXISTS (
          SELECT 1 FROM public.entry_classifications AS classification
          WHERE classification.entry_id = entry.id
            AND classification.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.entry_analyses AS analysis
          WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.processing_jobs AS active
          WHERE active.user_id = entry.user_id
            AND active.job_type = 'entry_processing'
            AND active.source_version = entry.id::text
            AND active.status IN ('pending', 'running')
      )
    ORDER BY entry.created_at DESC, entry.id DESC
    LIMIT 1;

    INSERT INTO public.processing_backfill_runs (
        status, batch_size, max_queue_depth, max_oldest_pending_seconds,
        planned_count, upper_bound_created_at, upper_bound_entry_id, completed_at
    ) VALUES (
        CASE WHEN planned = 0 THEN 'completed' ELSE 'planned' END,
        p_batch_size, p_max_queue_depth, p_max_oldest_pending_seconds,
        planned, upper_created, upper_id,
        CASE WHEN planned = 0 THEN pg_catalog.now() ELSE NULL END
    ) RETURNING id INTO result;

    INSERT INTO public.processing_backfill_users (run_id, user_id)
    SELECT result, requested.user_id
    FROM pg_catalog.unnest(p_user_ids) AS requested(user_id);
    RETURN result;
END
$function$;

CREATE FUNCTION public.get_entry_processing_backfill_status(p_run_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
    queue_depth integer;
    oldest_pending integer;
    cohort_size integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run FROM public.processing_backfill_runs WHERE id = p_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    SELECT pg_catalog.count(*)::integer INTO queue_depth
    FROM public.processing_jobs
    WHERE status IN ('pending', 'running');
    SELECT COALESCE(
        GREATEST(
            0,
            EXTRACT(
                EPOCH FROM pg_catalog.now() - pg_catalog.min(created_at)
            )::integer
        ),
        0
    ) INTO oldest_pending
    FROM public.processing_jobs
    WHERE status = 'pending';
    SELECT pg_catalog.count(*)::integer INTO cohort_size
    FROM public.processing_backfill_users WHERE run_id = p_run_id;
    RETURN pg_catalog.jsonb_build_object(
        'run_id', run.id,
        'status', run.status,
        'planned_count', run.planned_count,
        'enqueued_count', run.enqueued_count,
        'cohort_size', cohort_size,
        'batch_size', run.batch_size,
        'queue_depth', queue_depth,
        'oldest_pending_seconds', oldest_pending,
        'cursor_created_at', run.cursor_created_at,
        'cursor_entry_id', run.cursor_entry_id,
        'throttled', run.last_throttle_reason IS NOT NULL,
        'throttle_reason', run.last_throttle_reason
    );
END
$function$;

CREATE FUNCTION public.run_entry_processing_backfill_batch(p_run_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
    queue_depth integer;
    oldest_pending integer;
    selected_count integer;
    changed_count integer;
    last_created timestamptz;
    last_id uuid;
    has_more boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run
    FROM public.processing_backfill_runs
    WHERE id = p_run_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    IF run.status IN ('paused', 'completed') THEN
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    SELECT pg_catalog.count(*)::integer INTO queue_depth
    FROM public.processing_jobs WHERE status IN ('pending', 'running');
    SELECT COALESCE(
        GREATEST(
            0,
            EXTRACT(
                EPOCH FROM pg_catalog.now() - pg_catalog.min(created_at)
            )::integer
        ),
        0
    ) INTO oldest_pending
    FROM public.processing_jobs WHERE status = 'pending';

    IF queue_depth >= run.max_queue_depth
       OR oldest_pending >= run.max_oldest_pending_seconds
    THEN
        UPDATE public.processing_backfill_runs
        SET status = 'running',
            last_throttle_reason = CASE
                WHEN queue_depth >= run.max_queue_depth THEN 'QUEUE_DEPTH'
                ELSE 'OLDEST_PENDING_AGE'
            END,
            last_checked_at = pg_catalog.now(),
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    WITH selected AS MATERIALIZED (
        SELECT entry.id, entry.user_id, entry.created_at
        FROM public.entries AS entry
        JOIN public.processing_backfill_users AS cohort
          ON cohort.user_id = entry.user_id AND cohort.run_id = p_run_id
        WHERE entry.processing_status = 'completed'
          AND (entry.created_at, entry.id) <=
              (run.upper_bound_created_at, run.upper_bound_entry_id)
          AND (
              run.cursor_created_at IS NULL
              OR (entry.created_at, entry.id) >
                 (run.cursor_created_at, run.cursor_entry_id)
          )
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
              SELECT 1 FROM public.processing_jobs AS active
              WHERE active.user_id = entry.user_id
                AND active.job_type = 'entry_processing'
                AND active.source_version = entry.id::text
                AND active.status IN ('pending', 'running')
          )
        ORDER BY entry.created_at, entry.id
        LIMIT run.batch_size
        FOR UPDATE OF entry
    ), upserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, execution_mode, priority,
            source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', 'backfill', 10,
               id::text, pg_catalog.now()
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
            execution_mode = 'backfill', priority = 10,
            status = 'pending', run_after = EXCLUDED.run_after, attempts = 0,
            worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
            last_error_code = NULL, completed_at = NULL,
            updated_at = pg_catalog.now()
        WHERE public.processing_jobs.status IN ('completed', 'failed')
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = public.processing_jobs.entry_id
                AND analysis.user_id = public.processing_jobs.user_id
          )
        RETURNING 1
    )
    SELECT
        (SELECT pg_catalog.count(*)::integer FROM selected),
        (SELECT pg_catalog.count(*)::integer FROM upserted),
        (SELECT created_at FROM selected ORDER BY created_at DESC, id DESC LIMIT 1),
        (SELECT id FROM selected ORDER BY created_at DESC, id DESC LIMIT 1)
    INTO selected_count, changed_count, last_created, last_id;

    IF selected_count = 0 THEN
        UPDATE public.processing_backfill_runs
        SET status = 'completed', completed_at = pg_catalog.now(),
            last_throttle_reason = NULL, last_checked_at = pg_catalog.now(),
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM public.entries AS entry
        JOIN public.processing_backfill_users AS cohort
          ON cohort.user_id = entry.user_id AND cohort.run_id = p_run_id
        WHERE (entry.created_at, entry.id) > (last_created, last_id)
          AND (entry.created_at, entry.id) <=
              (run.upper_bound_created_at, run.upper_bound_entry_id)
          AND entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
          )
    ) INTO has_more;

    UPDATE public.processing_backfill_runs
    SET status = CASE WHEN has_more THEN 'running' ELSE 'completed' END,
        enqueued_count = enqueued_count + changed_count,
        cursor_created_at = last_created,
        cursor_entry_id = last_id,
        last_throttle_reason = NULL,
        last_checked_at = pg_catalog.now(),
        completed_at = CASE WHEN has_more THEN NULL ELSE pg_catalog.now() END,
        updated_at = pg_catalog.now()
    WHERE id = p_run_id;
    RETURN public.get_entry_processing_backfill_status(p_run_id);
END
$function$;

CREATE FUNCTION public.set_entry_processing_backfill_state(
    p_run_id uuid,
    p_action text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_action NOT IN ('pause', 'resume')
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run FROM public.processing_backfill_runs
    WHERE id = p_run_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    IF run.status = 'completed' THEN
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;
    IF p_action = 'pause' AND run.status IN ('planned', 'running') THEN
        UPDATE public.processing_backfill_runs
        SET status = 'paused', last_throttle_reason = NULL,
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
    ELSIF p_action = 'resume' AND run.status = 'paused' THEN
        UPDATE public.processing_backfill_runs
        SET status = 'running', last_throttle_reason = NULL,
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
    END IF;
    RETURN public.get_entry_processing_backfill_status(p_run_id);
END
$function$;

DROP FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz);

CREATE OR REPLACE FUNCTION public.retry_entry_processing_for_owner(
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
    SET status = 'pending', execution_mode = 'user', priority = 100,
        run_after = pg_catalog.now(), attempts = 0,
        worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
        last_error_code = NULL, completed_at = NULL
    WHERE user_id = p_user_id AND entry_id = p_entry_id
      AND job_type = 'entry_processing' AND source_version = p_entry_id::text
      AND status = 'failed'
    RETURNING id INTO job_id;
    IF job_id IS NULL THEN
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, execution_mode, priority, source_version
        ) VALUES (
            p_user_id, p_entry_id, 'entry_processing', 'user', 100, p_entry_id::text
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

-- Entry deletion can invalidate a published snapshot, but an authenticated RPC
-- must not choose a rollout cohort or shadow/publish mode. The cohort-aware
-- scheduler is the sole synthesis enqueuer after this migration.
CREATE OR REPLACE FUNCTION public.delete_entry_with_reflection_for_owner(
    p_user_id uuid, p_entry_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    affected_candidates uuid[];
    accepted boolean;
    latest_source bigint;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || p_user_id::text, 0)
    );
    SELECT analysis.eligibility = 'accepted' INTO accepted
    FROM public.entry_analyses AS analysis
    WHERE analysis.entry_id = p_entry_id AND analysis.user_id = p_user_id;
    SELECT pg_catalog.array_agg(DISTINCT evidence.candidate_id)
    INTO affected_candidates
    FROM public.pattern_candidate_evidence AS evidence
    JOIN public.entry_signals AS signal
      ON signal.id = evidence.signal_id AND signal.user_id = evidence.user_id
    WHERE signal.entry_id = p_entry_id AND signal.user_id = p_user_id;
    DELETE FROM public.entries WHERE id = p_entry_id AND user_id = p_user_id;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF pg_catalog.cardinality(affected_candidates) > 0 THEN
        UPDATE public.pattern_candidates
        SET status = 'weakened', version = version + 1
        WHERE user_id = p_user_id AND id = ANY(affected_candidates) AND status <> 'rejected';
    END IF;
    IF accepted IS TRUE THEN
        UPDATE public.reflection_snapshots
        SET status = 'stale'
        WHERE id = (
            SELECT last_successful_snapshot_id FROM public.reflection_user_state
            WHERE user_id = p_user_id
        );
        SELECT COALESCE(pg_catalog.max(source_version), 0) INTO latest_source
        FROM public.entry_analyses
        WHERE user_id = p_user_id AND eligibility = 'accepted';
        UPDATE public.reflection_user_state
        SET latest_accepted_source_version = latest_source,
            last_snapshot_source_version = LEAST(last_snapshot_source_version, latest_source),
            last_schedule_local_date = NULL,
            new_valid_entries = (
                SELECT pg_catalog.count(*)::integer FROM public.entry_analyses
                WHERE user_id = p_user_id AND eligibility = 'accepted'
                  AND source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ),
            new_accepted_signals = (
                SELECT pg_catalog.count(*)::integer
                FROM public.entry_signals AS signal
                JOIN public.entry_analyses AS analysis
                  ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
                WHERE signal.user_id = p_user_id AND analysis.eligibility = 'accepted'
                  AND analysis.source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ),
            pending_local_dates = COALESCE((
                SELECT pg_catalog.array_agg(DISTINCT entry.entry_date ORDER BY entry.entry_date)
                FROM public.entry_analyses AS analysis
                JOIN public.entries AS entry
                  ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
                WHERE analysis.user_id = p_user_id AND analysis.eligibility = 'accepted'
                  AND analysis.source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ), '{}'::date[])
        WHERE user_id = p_user_id;
    END IF;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.claim_processing_job(text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[])
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_reflection_shadow(
    uuid, text, uuid, integer, integer, boolean
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.plan_entry_processing_backfill(
    uuid[], integer, integer, integer
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_entry_processing_backfill_status(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.run_entry_processing_backfill_batch(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.set_entry_processing_backfill_state(uuid, text)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.claim_processing_job(text) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[])
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_reflection_shadow(
    uuid, text, uuid, integer, integer, boolean
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.plan_entry_processing_backfill(
    uuid[], integer, integer, integer
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_entry_processing_backfill_status(uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.run_entry_processing_backfill_batch(uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.set_entry_processing_backfill_state(uuid, text)
    TO orion_worker;
