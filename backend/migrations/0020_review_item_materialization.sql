-- Claim-bound Entry Insight Review materialization.
-- Accepted signal rows, encrypted Review rows, and embeddings are applied by
-- the worker in one transaction. Review feedback is never changed on replay.

ALTER TABLE public.entry_signals
    DROP CONSTRAINT entry_signals_type_check;
ALTER TABLE public.entry_signals
    ADD CONSTRAINT entry_signals_type_check CHECK (signal_type IN (
        'event', 'emotion', 'energy_gain', 'energy_loss', 'self_knowledge',
        'desire', 'explicit_preference', 'need', 'avoidance', 'belief',
        'self_statement', 'action', 'outcome', 'conflict',
        'protective_strategy', 'realization', 'causal_relationship'
    ));

DROP POLICY review_items_insert_worker ON public.review_items;
REVOKE INSERT ON public.review_items FROM orion_worker;
REVOKE EXECUTE ON FUNCTION public.is_valid_encrypted_envelope_v1(jsonb)
    FROM orion_worker;

CREATE FUNCTION public.materialize_entry_review_items(
    p_job_id uuid,
    p_claim_token uuid,
    p_signals jsonb
)
RETURNS TABLE (
    analysis_accepted boolean,
    review_item_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    analysis public.entry_analyses%ROWTYPE;
    entry_local_date date;
    persisted_signal public.entry_signals%ROWTYPE;
    supplied_signal jsonb;
    review_item jsonb;
    expected_review_items integer := 0;
    persisted_review_items integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_signals) <> 'array'
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
           WHERE pg_catalog.jsonb_typeof(item.value) <> 'object'
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;
    IF NOT FOUND
       OR job.job_type <> 'entry_processing'
       OR job.status <> 'completed'
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    SELECT * INTO analysis
    FROM public.entry_analyses
    WHERE entry_id = job.entry_id AND user_id = job.user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    IF analysis.eligibility <> 'accepted' THEN
        RETURN QUERY SELECT false, 0;
        RETURN;
    END IF;

    SELECT entry_date INTO entry_local_date
    FROM public.entries
    WHERE id = job.entry_id AND user_id = job.user_id;

    IF pg_catalog.jsonb_array_length(p_signals) <> (
        SELECT pg_catalog.count(*)::integer
        FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'signal materialization is incomplete';
    END IF;

    FOR persisted_signal IN
        SELECT *
        FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
        ORDER BY id
    LOOP
        SELECT item.value INTO supplied_signal
        FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
        WHERE item.value ->> 'id' = persisted_signal.id::text;

        IF supplied_signal IS NULL
           OR supplied_signal ->> 'signal_type'
                IS DISTINCT FROM persisted_signal.signal_type
           OR (supplied_signal ->> 'source_start')::integer
                IS DISTINCT FROM persisted_signal.source_start
           OR (supplied_signal ->> 'source_end')::integer
                IS DISTINCT FROM persisted_signal.source_end
           OR (supplied_signal ->> 'occurred_on')::date
                IS DISTINCT FROM entry_local_date
        THEN
            RAISE EXCEPTION USING
                ERRCODE = '22023', MESSAGE = 'signal identity is invalid';
        END IF;

        IF persisted_signal.signal_type IN (
            'energy_gain', 'energy_loss', 'self_knowledge', 'realization',
            'explicit_preference', 'need', 'belief', 'avoidance',
            'protective_strategy', 'conflict', 'causal_relationship'
        ) THEN
            review_item := supplied_signal -> 'review_item';
            expected_review_items := expected_review_items + 1;
            IF pg_catalog.jsonb_typeof(review_item) <> 'object'
               OR NOT review_item ?& ARRAY[
                    'id', 'category', 'statement_envelope',
                    'source_quote_envelope', 'inference_level', 'metadata'
               ]
               OR review_item - ARRAY[
                    'id', 'category', 'statement_envelope',
                    'source_quote_envelope', 'inference_level', 'metadata'
               ] <> '{}'::jsonb
               OR public.is_valid_encrypted_envelope_v1(
                    review_item -> 'statement_envelope'
               ) IS NOT TRUE
               OR public.is_valid_encrypted_envelope_v1(
                    review_item -> 'source_quote_envelope'
               ) IS NOT TRUE
               OR review_item ->> 'inference_level'
                    NOT IN ('direct', 'inferred')
               OR pg_catalog.jsonb_typeof(review_item -> 'metadata') <> 'object'
               OR NOT (review_item -> 'metadata') ?& ARRAY[
                    'model_id', 'prompt_version', 'source'
               ]
               OR (review_item -> 'metadata') - ARRAY[
                    'model_id', 'prompt_version', 'source'
               ] <> '{}'::jsonb
               OR review_item #>> '{metadata,model_id}'
                    IS DISTINCT FROM analysis.model_id
               OR review_item #>> '{metadata,prompt_version}'
                    IS DISTINCT FROM analysis.prompt_version
               OR review_item #>> '{metadata,source}'
                    IS DISTINCT FROM 'entry_analysis'
               OR review_item ->> 'category' IS DISTINCT FROM (CASE
                    WHEN persisted_signal.signal_type IN (
                        'energy_gain', 'energy_loss'
                    ) THEN 'energy'
                    WHEN persisted_signal.signal_type IN (
                        'self_knowledge', 'realization', 'explicit_preference'
                    ) THEN 'self_knowledge'
                    ELSE 'needs_beliefs'
               END)
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '22023', MESSAGE = 'review item is invalid';
            END IF;

            INSERT INTO public.review_items (
                id, user_id, entry_id, entry_signal_id, scope, item_type,
                category, statement_envelope, source_quote_envelope,
                source_entry_ids, source_dates, inference_level,
                model_confidence, review_status, evidence_weight,
                reflection_eligible, metadata
            ) VALUES (
                (review_item ->> 'id')::uuid, job.user_id, job.entry_id,
                persisted_signal.id, 'entry_insight',
                persisted_signal.signal_type, review_item ->> 'category',
                review_item -> 'statement_envelope',
                review_item -> 'source_quote_envelope',
                ARRAY[job.entry_id], ARRAY[entry_local_date],
                review_item ->> 'inference_level', persisted_signal.confidence,
                'pending', 1.0, true, review_item -> 'metadata'
            )
            ON CONFLICT (entry_signal_id)
                WHERE entry_signal_id IS NOT NULL
            DO NOTHING;
        ELSIF supplied_signal ? 'review_item' THEN
            RAISE EXCEPTION USING
                ERRCODE = '22023',
                MESSAGE = 'non-reviewable signal has a review item';
        END IF;
    END LOOP;

    IF (
        SELECT pg_catalog.count(*)::integer
        FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
        WHERE item.value ? 'review_item'
    ) <> expected_review_items THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'review item mapping is incomplete';
    END IF;

    SELECT pg_catalog.count(*)::integer INTO persisted_review_items
    FROM public.review_items
    WHERE entry_signal_id IN (
        SELECT id FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
    );
    IF persisted_review_items <> expected_review_items THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'review item persistence is incomplete';
    END IF;

    RETURN QUERY SELECT true, persisted_review_items;
END
$function$;

REVOKE ALL ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb)
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE
    ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb)
    TO orion_worker;

COMMENT ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb) IS
    'Materializes validated encrypted Entry Insight Review rows for a completed claim without changing feedback on replay.';
