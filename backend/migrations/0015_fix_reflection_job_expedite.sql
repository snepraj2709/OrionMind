-- PostgreSQL implements LEAST as a conditional expression, not a function in
-- pg_catalog. The 0014 definition created successfully but failed at runtime
-- whenever the reflection read path attempted to enqueue or expedite a job.

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
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
        source_version = EXCLUDED.source_version,
        run_after = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
            THEN LEAST(public.processing_jobs.run_after, EXCLUDED.run_after)
            ELSE public.processing_jobs.run_after
        END,
        updated_at = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
             AND EXCLUDED.run_after < public.processing_jobs.run_after
            THEN pg_catalog.now()
            ELSE public.processing_jobs.updated_at
        END
    RETURNING id INTO result;
    RETURN result;
END
$function$;
