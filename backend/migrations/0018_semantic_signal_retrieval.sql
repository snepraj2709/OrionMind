-- Worker-only semantic signal retrieval, bounded historical embedding backfill,
-- and exact snapshot evidence-entry counts for the Reflection API.

ALTER TABLE public.entry_signals
    ADD COLUMN embedding_backfill_token uuid,
    ADD COLUMN embedding_backfill_claimed_at timestamptz,
    ADD CONSTRAINT entry_signals_embedding_backfill_claim_check CHECK (
        (embedding_backfill_token IS NULL AND embedding_backfill_claimed_at IS NULL)
        OR (embedding_backfill_token IS NOT NULL AND embedding_backfill_claimed_at IS NOT NULL)
    );

CREATE INDEX entry_signals_embedding_backfill_claim_idx
    ON public.entry_signals (embedding_backfill_claimed_at, id)
    WHERE embedding IS NULL;

CREATE FUNCTION public.find_signal_semantic_neighbors(
    p_user_id uuid,
    p_anchor_signal_ids uuid[],
    p_source_version bigint,
    p_model_id text,
    p_top_k integer DEFAULT 8,
    p_similarity_threshold numeric DEFAULT 0.90
)
RETURNS TABLE (
    anchor_signal_id uuid,
    neighbor_signal_id uuid,
    cosine_distance double precision,
    similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    latest_date date;
    basis_start date;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_anchor_signal_ids IS NULL
       OR pg_catalog.cardinality(p_anchor_signal_ids) < 1
       OR pg_catalog.cardinality(p_anchor_signal_ids) > 4096
       OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(p_anchor_signal_ids) AS requested(id)
           WHERE requested.id IS NULL
       )
       OR (
           SELECT pg_catalog.count(DISTINCT requested.id)
           FROM pg_catalog.unnest(p_anchor_signal_ids) AS requested(id)
       ) <> pg_catalog.cardinality(p_anchor_signal_ids)
       OR p_source_version IS NULL OR p_source_version < 1
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
       OR p_top_k IS NULL OR p_top_k < 1 OR p_top_k > 50
       OR p_similarity_threshold IS NULL
       OR p_similarity_threshold < 0 OR p_similarity_threshold > 1
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT pg_catalog.max(entry.entry_date)
    INTO latest_date
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.eligibility = 'accepted'
      AND analysis.source_version <= p_source_version;

    IF latest_date IS NULL THEN
        RETURN;
    END IF;
    basis_start := latest_date - 89;

    RETURN QUERY
    WITH anchors AS (
        SELECT signal.id, signal.entry_id, signal.embedding
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        JOIN public.entries AS entry
          ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
        WHERE signal.user_id = p_user_id
          AND signal.id = ANY(p_anchor_signal_ids)
          AND signal.embedding IS NOT NULL
          AND signal.embedding_model = p_model_id
          AND extensions.vector_dims(signal.embedding) = 1536
          AND analysis.eligibility = 'accepted'
          AND analysis.source_version <= p_source_version
          AND entry.entry_date BETWEEN basis_start AND latest_date
    ), ranked AS (
        SELECT anchor.id AS anchor_id,
               neighbor.id AS neighbor_id,
               (anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding)::double precision AS distance,
               pg_catalog.row_number() OVER (
                   PARTITION BY anchor.id
                   ORDER BY anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding,
                            neighbor.occurred_on,
                            neighbor.entry_id,
                            neighbor.id
               ) AS neighbor_rank
        FROM anchors AS anchor
        JOIN public.entry_signals AS neighbor
          ON neighbor.user_id = p_user_id
         AND neighbor.id <> anchor.id
         AND neighbor.entry_id <> anchor.entry_id
         AND neighbor.embedding IS NOT NULL
         AND neighbor.embedding_model = p_model_id
         AND extensions.vector_dims(neighbor.embedding) = 1536
        JOIN public.entry_analyses AS neighbor_analysis
          ON neighbor_analysis.id = neighbor.analysis_id
         AND neighbor_analysis.user_id = neighbor.user_id
         AND neighbor_analysis.entry_id = neighbor.entry_id
        JOIN public.entries AS neighbor_entry
          ON neighbor_entry.id = neighbor.entry_id
         AND neighbor_entry.user_id = neighbor.user_id
        WHERE neighbor_analysis.eligibility = 'accepted'
          AND neighbor_analysis.source_version <= p_source_version
          AND neighbor_entry.entry_date BETWEEN basis_start AND latest_date
          AND 1 - (anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding) >= p_similarity_threshold
    )
    SELECT ranked.anchor_id,
           ranked.neighbor_id,
           ranked.distance,
           1 - ranked.distance
    FROM ranked
    WHERE ranked.neighbor_rank <= p_top_k
    ORDER BY ranked.anchor_id, ranked.neighbor_rank, ranked.neighbor_id;
END
$function$;

CREATE FUNCTION public.get_signal_embedding_backfill_status(p_model_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    missing_count integer;
    claimable_count integer;
    active_claim_count integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT pg_catalog.count(*)::integer,
           pg_catalog.count(*) FILTER (
               WHERE signal.embedding_backfill_token IS NULL
                  OR signal.embedding_backfill_claimed_at < pg_catalog.now() - INTERVAL '15 minutes'
           )::integer,
           pg_catalog.count(*) FILTER (
               WHERE signal.embedding_backfill_token IS NOT NULL
                 AND signal.embedding_backfill_claimed_at >= pg_catalog.now() - INTERVAL '15 minutes'
           )::integer
    INTO missing_count, claimable_count, active_claim_count
    FROM public.entry_signals AS signal
    JOIN public.entry_analyses AS analysis
      ON analysis.id = signal.analysis_id
     AND analysis.user_id = signal.user_id
     AND analysis.entry_id = signal.entry_id
    WHERE signal.embedding IS NULL
      AND analysis.eligibility = 'accepted';

    RETURN pg_catalog.jsonb_build_object(
        'model_id', p_model_id,
        'missing_signal_count', missing_count,
        'claimable_signal_count', claimable_count,
        'active_claim_count', active_claim_count
    );
END
$function$;

CREATE FUNCTION public.claim_signal_embedding_backfill_batch(
    p_batch_size integer,
    p_model_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    batch_token uuid := gen_random_uuid();
    items jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_size IS NULL OR p_batch_size < 1 OR p_batch_size > 128
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    WITH claimable AS (
        SELECT signal.id
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        WHERE signal.embedding IS NULL
          AND analysis.eligibility = 'accepted'
          AND (
              signal.embedding_backfill_token IS NULL
              OR signal.embedding_backfill_claimed_at < pg_catalog.now() - INTERVAL '15 minutes'
          )
        ORDER BY analysis.source_version, signal.entry_id, signal.source_start, signal.id
        FOR UPDATE OF signal SKIP LOCKED
        LIMIT p_batch_size
    ), claimed AS (
        UPDATE public.entry_signals AS signal
        SET embedding_backfill_token = batch_token,
            embedding_backfill_claimed_at = pg_catalog.now()
        FROM claimable
        WHERE signal.id = claimable.id AND signal.embedding IS NULL
        RETURNING signal.id, signal.user_id, signal.payload_envelope,
                  signal.signal_type, signal.themes, signal.need_tags, signal.loop_role
    )
    SELECT COALESCE(pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
            'signal_id', claimed.id,
            'user_id', claimed.user_id,
            'payload_envelope', claimed.payload_envelope,
            'signal_type', claimed.signal_type,
            'themes', claimed.themes,
            'need_tags', claimed.need_tags,
            'loop_role', claimed.loop_role
        ) ORDER BY claimed.id
    ), '[]'::jsonb)
    INTO items
    FROM claimed;

    RETURN pg_catalog.jsonb_build_object(
        'batch_token', batch_token,
        'model_id', p_model_id,
        'items', items
    );
END
$function$;

CREATE FUNCTION public.store_signal_embedding_backfill_batch(
    p_batch_token uuid,
    p_embeddings jsonb,
    p_model_id text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item jsonb;
    signal_id uuid;
    vector_value extensions.vector;
    expected_count integer;
    stored_count integer;
    updated_count integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_token IS NULL
       OR p_embeddings IS NULL
       OR pg_catalog.jsonb_typeof(p_embeddings) <> 'array'
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    PERFORM 1
    FROM public.entry_signals
    WHERE embedding_backfill_token = p_batch_token
    ORDER BY id
    FOR UPDATE;

    SELECT pg_catalog.count(*)::integer,
           pg_catalog.count(*) FILTER (WHERE embedding IS NOT NULL)::integer
    INTO expected_count, stored_count
    FROM public.entry_signals
    WHERE embedding_backfill_token = p_batch_token;

    IF expected_count < 1
       OR expected_count <> pg_catalog.jsonb_array_length(p_embeddings)
       OR (
           SELECT pg_catalog.count(DISTINCT value ->> 'signal_id')
           FROM pg_catalog.jsonb_array_elements(p_embeddings)
       ) <> expected_count
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
           WHERE pg_catalog.jsonb_typeof(supplied.value) <> 'object'
              OR (SELECT pg_catalog.count(*)
                  FROM pg_catalog.jsonb_object_keys(supplied.value)) <> 2
              OR NOT supplied.value ?& ARRAY['signal_id', 'values']
              OR pg_catalog.jsonb_typeof(supplied.value -> 'signal_id') <> 'string'
              OR pg_catalog.jsonb_typeof(supplied.value -> 'values') <> 'array'
              OR pg_catalog.jsonb_array_length(supplied.value -> 'values') <> 1536
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embeddings are incomplete';
    END IF;

    IF stored_count = expected_count THEN
        IF EXISTS (
            SELECT 1
            FROM public.entry_signals AS signal
            WHERE signal.embedding_backfill_token = p_batch_token
              AND (
                  signal.embedding_model IS DISTINCT FROM p_model_id
                  OR extensions.vector_dims(signal.embedding) <> 1536
              )
        ) OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.entry_signals AS signal
                WHERE signal.embedding_backfill_token = p_batch_token
                  AND signal.id = (supplied.value ->> 'signal_id')::uuid
            )
        ) OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
            JOIN public.entry_signals AS signal
              ON signal.embedding_backfill_token = p_batch_token
             AND signal.id = (supplied.value ->> 'signal_id')::uuid
            WHERE signal.embedding::text IS DISTINCT FROM
                  ((supplied.value -> 'values')::text::extensions.vector)::text
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding retry is invalid';
        END IF;
        RETURN expected_count;
    ELSIF stored_count > 0 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding state is invalid';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_embeddings)
    LOOP
        signal_id := (item ->> 'signal_id')::uuid;
        vector_value := (item -> 'values')::text::extensions.vector;
        UPDATE public.entry_signals
        SET embedding = vector_value,
            embedding_model = p_model_id,
            embedded_at = pg_catalog.now()
        WHERE id = signal_id
          AND embedding IS NULL
          AND embedding_backfill_token = p_batch_token;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding is invalid';
        END IF;
        updated_count := updated_count + 1;
    END LOOP;
    RETURN updated_count;
END
$function$;

CREATE FUNCTION public.release_signal_embedding_backfill_batch(p_batch_token uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    released integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_token IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entry_signals
    SET embedding_backfill_token = NULL,
        embedding_backfill_claimed_at = NULL
    WHERE embedding IS NULL AND embedding_backfill_token = p_batch_token;
    GET DIAGNOSTICS released = ROW_COUNT;
    RETURN released;
END
$function$;

CREATE OR REPLACE FUNCTION public.get_reflections_for_owner(
    p_user_id uuid,
    p_evidence_limit integer DEFAULT 12
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    owner_timezone text;
    state_payload jsonb;
    job_payload jsonb;
    snapshot_payload jsonb;
    selected_snapshot_id uuid;
    snapshot_start date;
    snapshot_end date;
    snapshot_source bigint;
    current_end date;
    current_start date;
    current_basis jsonb;
    insight_payload jsonb := '[]'::jsonb;
    evidence_payload jsonb := '[]'::jsonb;
    feedback_payload jsonb := '[]'::jsonb;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_evidence_limit < 1
       OR p_evidence_limit > 12
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT profile.timezone INTO owner_timezone
    FROM public.user_profiles AS profile WHERE profile.user_id = p_user_id;
    IF owner_timezone IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'profile not found';
    END IF;

    SELECT pg_catalog.jsonb_build_object(
        'latest_accepted_source_version', state.latest_accepted_source_version,
        'last_snapshot_source_version', state.last_snapshot_source_version,
        'last_processing_error_code', state.last_processing_error_code
    ) INTO state_payload
    FROM public.reflection_user_state AS state WHERE state.user_id = p_user_id;

    SELECT pg_catalog.jsonb_build_object(
        'status', job.status, 'source_version', job.source_version, 'created_at', job.created_at
    ) INTO job_payload
    FROM public.processing_jobs AS job
    WHERE job.user_id = p_user_id AND job.job_type = 'reflection_synthesis'
    ORDER BY job.created_at DESC, job.id DESC LIMIT 1;

    SELECT snapshot.id, snapshot.basis_start, snapshot.basis_end, snapshot.source_version,
           pg_catalog.jsonb_build_object(
               'id', snapshot.id, 'version', snapshot.version,
               'source_version', snapshot.source_version,
               'basis_start', snapshot.basis_start, 'basis_end', snapshot.basis_end,
               'valid_entry_count', snapshot.valid_entry_count,
               'excluded_entry_count', snapshot.excluded_entry_count,
               'distinct_entry_dates', snapshot.distinct_entry_dates,
               'reflective_word_count', snapshot.reflective_word_count,
               'status', snapshot.status, 'created_at', snapshot.created_at,
               'excluded_reasons', COALESCE((
                   SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
                   FROM (
                       SELECT analysis.entry_kind, pg_catalog.count(*)::integer AS total
                       FROM public.entry_analyses AS analysis
                       JOIN public.entries AS entry
                         ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
                       WHERE analysis.user_id = p_user_id
                         AND analysis.eligibility <> 'accepted'
                         AND analysis.source_version <= snapshot.source_version
                         AND entry.entry_date BETWEEN snapshot.basis_start AND snapshot.basis_end
                       GROUP BY analysis.entry_kind ORDER BY analysis.entry_kind
                   ) AS summary
               ), '{}'::jsonb)
           )
    INTO selected_snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload
    FROM public.reflection_snapshots AS snapshot
    LEFT JOIN public.reflection_user_state AS state ON state.user_id = snapshot.user_id
    WHERE snapshot.user_id = p_user_id
    ORDER BY (snapshot.id = state.last_successful_snapshot_id) DESC,
             snapshot.version DESC, snapshot.id DESC LIMIT 1;

    SELECT COALESCE(pg_catalog.max(entry.entry_date),
                    (pg_catalog.now() AT TIME ZONE owner_timezone)::date)
    INTO current_end
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id;
    current_start := current_end - 89;

    SELECT pg_catalog.jsonb_build_object(
        'basis_start', current_start, 'basis_end', current_end,
        'valid_entry_count', pg_catalog.count(*) FILTER (WHERE analysis.eligibility = 'accepted')::integer,
        'excluded_entry_count', pg_catalog.count(*) FILTER (WHERE analysis.eligibility <> 'accepted')::integer,
        'distinct_entry_dates', pg_catalog.count(DISTINCT entry.entry_date)::integer,
        'reflective_word_count', COALESCE(pg_catalog.sum(analysis.reflective_word_count)
            FILTER (WHERE analysis.eligibility = 'accepted'), 0)::integer,
        'excluded_reasons', COALESCE((
            SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
            FROM (
                SELECT excluded.entry_kind, pg_catalog.count(*)::integer AS total
                FROM public.entry_analyses AS excluded
                JOIN public.entries AS excluded_entry
                  ON excluded_entry.id = excluded.entry_id AND excluded_entry.user_id = excluded.user_id
                WHERE excluded.user_id = p_user_id
                  AND excluded.eligibility <> 'accepted'
                  AND excluded_entry.entry_date BETWEEN current_start AND current_end
                GROUP BY excluded.entry_kind ORDER BY excluded.entry_kind
            ) AS summary
        ), '{}'::jsonb)
    ) INTO current_basis
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND entry.entry_date BETWEEN current_start AND current_end;

    IF selected_snapshot_id IS NOT NULL THEN
        WITH evidence_counts AS (
            SELECT evidence.insight_id,
                   pg_catalog.count(DISTINCT evidence.entry_id)::integer AS entry_count
            FROM public.reflection_snapshot_evidence AS evidence
            JOIN public.reflection_snapshot_insights AS counted_insight
              ON counted_insight.id = evidence.insight_id
             AND counted_insight.user_id = evidence.user_id
            WHERE evidence.user_id = p_user_id
              AND evidence.evidence_role = 'supporting'
              AND counted_insight.snapshot_id = selected_snapshot_id
            GROUP BY evidence.insight_id
        )
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
                'id', insight.id, 'pattern_type', insight.pattern_type,
                'ordinal', insight.ordinal, 'status', insight.status,
                'reason_code', insight.reason_code,
                'payload_envelope', insight.payload_envelope,
                'confidence_label', insight.confidence_label, 'score', insight.score,
                'evidence_entry_count', CASE WHEN insight.status = 'available'
                    THEN COALESCE(evidence_counts.entry_count, 0) END
            )) ORDER BY insight.pattern_type, insight.ordinal
        ), '[]'::jsonb) INTO insight_payload
        FROM public.reflection_snapshot_insights AS insight
        LEFT JOIN evidence_counts ON evidence_counts.insight_id = insight.id
        WHERE insight.user_id = p_user_id
          AND insight.snapshot_id = selected_snapshot_id;

        WITH ranked AS (
            SELECT evidence.*,
                   pg_catalog.row_number() OVER (
                       PARTITION BY evidence.insight_id
                       ORDER BY CASE evidence.evidence_role WHEN 'supporting' THEN 0 ELSE 1 END,
                                evidence.ordinal, evidence.signal_id
                   ) AS evidence_rank
            FROM public.reflection_snapshot_evidence AS evidence
            JOIN public.reflection_snapshot_insights AS insight
              ON insight.id = evidence.insight_id AND insight.user_id = evidence.user_id
            WHERE evidence.user_id = p_user_id
              AND insight.snapshot_id = selected_snapshot_id
        )
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', ranked.insight_id, 'signal_id', ranked.signal_id,
                'entry_id', ranked.entry_id, 'evidence_role', ranked.evidence_role,
                'ordinal', ranked.ordinal, 'source_start', ranked.source_start,
                'source_end', ranked.source_end, 'entry_date', entry.entry_date,
                'input_type', entry.input_type,
                'entry_content_envelope', entry.content_envelope,
                'signal_payload_envelope', signal.payload_envelope,
                'themes', signal.themes
            ) ORDER BY ranked.insight_id, ranked.evidence_rank
        ), '[]'::jsonb) INTO evidence_payload
        FROM ranked
        JOIN public.entry_signals AS signal
          ON signal.id = ranked.signal_id AND signal.user_id = ranked.user_id
        JOIN public.entries AS entry
          ON entry.id = ranked.entry_id AND entry.user_id = ranked.user_id
        WHERE ranked.evidence_rank <= p_evidence_limit;

        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', feedback.insight_id, 'response', feedback.response,
                'updated_at', feedback.updated_at
            ) ORDER BY feedback.insight_id
        ), '[]'::jsonb) INTO feedback_payload
        FROM public.reflection_feedback AS feedback
        WHERE feedback.user_id = p_user_id
          AND feedback.snapshot_id = selected_snapshot_id;
    END IF;

    RETURN pg_catalog.jsonb_build_object(
        'state', state_payload, 'job', job_payload, 'snapshot', snapshot_payload,
        'current_basis', current_basis, 'insights', insight_payload,
        'evidence', evidence_payload, 'feedback', feedback_payload
    );
END
$function$;

REVOKE ALL ON FUNCTION public.find_signal_semantic_neighbors(
    uuid, uuid[], bigint, text, integer, numeric
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_signal_embedding_backfill_status(text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.claim_signal_embedding_backfill_batch(integer, text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.store_signal_embedding_backfill_batch(uuid, jsonb, text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.release_signal_embedding_backfill_batch(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.find_signal_semantic_neighbors(
    uuid, uuid[], bigint, text, integer, numeric
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_signal_embedding_backfill_status(text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.claim_signal_embedding_backfill_batch(integer, text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.store_signal_embedding_backfill_batch(uuid, jsonb, text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.release_signal_embedding_backfill_batch(uuid)
    TO orion_worker;
