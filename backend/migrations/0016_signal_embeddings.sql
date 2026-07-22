CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

GRANT USAGE ON SCHEMA extensions TO authenticated, orion_app, orion_worker;

ALTER TABLE public.entry_signals
    ADD COLUMN embedding extensions.vector(1536),
    ADD COLUMN embedding_model text,
    ADD COLUMN embedded_at timestamptz,
    ADD CONSTRAINT entry_signals_embedding_metadata_check CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND embedded_at IS NULL)
        OR (
            embedding IS NOT NULL
            AND embedding_model ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
            AND embedded_at IS NOT NULL
        )
    );

CREATE FUNCTION public.store_entry_signal_embeddings(
    p_job_id uuid,
    p_claim_token uuid,
    p_embeddings jsonb,
    p_model_id text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    item jsonb;
    signal_id uuid;
    vector_value extensions.vector;
    expected_count integer;
    updated_count integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_embeddings) <> 'array'
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND
       OR job.job_type <> 'entry_processing'
       OR job.entry_id IS NULL
       OR job.status <> 'completed'
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    SELECT pg_catalog.count(*)::integer INTO expected_count
    FROM public.entry_signals
    WHERE user_id = job.user_id AND entry_id = job.entry_id;

    IF expected_count <> pg_catalog.jsonb_array_length(p_embeddings)
       OR (
           SELECT pg_catalog.count(DISTINCT value ->> 'signal_id')
           FROM pg_catalog.jsonb_array_elements(p_embeddings)
       ) <> expected_count
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embeddings are incomplete';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_embeddings)
    LOOP
        IF pg_catalog.jsonb_typeof(item) <> 'object'
           OR (
               SELECT pg_catalog.count(*)
               FROM pg_catalog.jsonb_object_keys(item)
           ) <> 2
           OR NOT item ?& ARRAY['signal_id', 'values']
           OR pg_catalog.jsonb_typeof(item -> 'signal_id') <> 'string'
           OR pg_catalog.jsonb_typeof(item -> 'values') <> 'array'
           OR pg_catalog.jsonb_array_length(item -> 'values') <> 1536
        THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embedding is invalid';
        END IF;

        signal_id := (item ->> 'signal_id')::uuid;
        vector_value := (item -> 'values')::text::extensions.vector;

        UPDATE public.entry_signals
        SET embedding = vector_value,
            embedding_model = p_model_id,
            embedded_at = pg_catalog.now()
        WHERE id = signal_id
          AND user_id = job.user_id
          AND entry_id = job.entry_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embedding is invalid';
        END IF;
        updated_count := updated_count + 1;
    END LOOP;

    RETURN updated_count;
END
$function$;

REVOKE ALL ON FUNCTION public.store_entry_signal_embeddings(
    uuid, uuid, jsonb, text
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.store_entry_signal_embeddings(
    uuid, uuid, jsonb, text
) TO orion_worker;

