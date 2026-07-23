-- Review-weighted reflection synthesis and atomic Pattern Review materialization.

ALTER TABLE public.reflection_snapshots
    ADD COLUMN model_name text,
    ADD COLUMN prompt_version text,
    ADD COLUMN generated_at timestamptz;

UPDATE public.reflection_snapshots
SET model_name = 'gpt-5.6-terra',
    prompt_version = 'reflection-synthesis-v1',
    generated_at = created_at;

ALTER TABLE public.reflection_snapshots
    ALTER COLUMN model_name SET DEFAULT 'gpt-5.6-terra',
    ALTER COLUMN model_name SET NOT NULL,
    ALTER COLUMN prompt_version SET DEFAULT 'reflection-synthesis-v1',
    ALTER COLUMN prompt_version SET NOT NULL,
    ALTER COLUMN generated_at SET DEFAULT pg_catalog.now(),
    ALTER COLUMN generated_at SET NOT NULL,
    ADD CONSTRAINT reflection_snapshots_model_name_check
        CHECK (pg_catalog.btrim(model_name) <> ''),
    ADD CONSTRAINT reflection_snapshots_prompt_version_check
        CHECK (pg_catalog.btrim(prompt_version) <> '');

CREATE OR REPLACE FUNCTION public.get_reflection_candidate_basis(
    p_user_id uuid,
    p_source_version bigint,
    p_basis_days integer DEFAULT 90
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    latest_date date;
    basis_start date;
    valid_entry_count integer;
    distinct_entry_dates integer;
    reflective_word_count integer;
    signals jsonb;
    candidates jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_source_version < 0
       OR p_basis_days <> 90
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
      AND analysis.source_version <= p_source_version
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

    basis_start := latest_date - (p_basis_days - 1);

    SELECT pg_catalog.count(*)::integer,
           pg_catalog.count(DISTINCT entry.entry_date)::integer,
           COALESCE(pg_catalog.sum(analysis.reflective_word_count), 0)::integer
    INTO valid_entry_count, distinct_entry_dates, reflective_word_count
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.eligibility = 'accepted'
      AND analysis.source_version <= p_source_version
      AND entry.entry_date BETWEEN basis_start AND latest_date
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

    SELECT COALESCE(pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
            'id', signal.id,
            'user_id', signal.user_id,
            'entry_id', signal.entry_id,
            'entry_user_id', entry.user_id,
            'analysis_id', analysis.id,
            'analysis_user_id', analysis.user_id,
            'analysis_entry_id', analysis.entry_id,
            'analysis_source_version', analysis.source_version,
            'analysis_eligibility', analysis.eligibility,
            'entry_date', entry.entry_date,
            'signal_type', signal.signal_type,
            'normalized_label_fingerprint', signal.normalized_label_fingerprint,
            'payload_envelope', signal.payload_envelope,
            'entry_content_envelope', entry.content_envelope,
            'themes', signal.themes,
            'need_tags', signal.need_tags,
            'loop_role', signal.loop_role,
            'confidence', signal.confidence * review.evidence_weight,
            'model_confidence', signal.confidence,
            'evidence_weight', review.evidence_weight,
            'source_start', signal.source_start,
            'source_end', signal.source_end,
            'occurred_on', signal.occurred_on,
            'duplicate_cluster_key', signal.duplicate_cluster_key
        ) ORDER BY entry.entry_date, signal.entry_id, signal.source_start, signal.id
    ), '[]'::jsonb)
    INTO signals
    FROM public.entry_signals AS signal
    JOIN public.entry_analyses AS analysis
      ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
     AND analysis.entry_id = signal.entry_id
    JOIN public.entries AS entry
      ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
    JOIN public.review_items AS review
      ON review.entry_signal_id = signal.id
     AND review.user_id = signal.user_id
     AND review.scope = 'entry_insight'
     AND review.reflection_eligible
     AND review.evidence_weight > 0
    WHERE signal.user_id = p_user_id
      AND analysis.eligibility = 'accepted'
      AND analysis.source_version <= p_source_version
      AND entry.entry_date BETWEEN basis_start AND latest_date;

    SELECT COALESCE(pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
            'id', candidate.id,
            'pattern_type', candidate.pattern_type,
            'canonical_key', candidate.canonical_key,
            'status', candidate.status,
            'score', candidate.score,
            'version', candidate.version,
            'first_seen_at', candidate.first_seen_at,
            'last_seen_at', candidate.last_seen_at,
            'last_source_version', candidate.last_source_version,
            'rejected_at', candidate.rejected_at,
            'rejected_source_version', candidate.rejected_source_version,
            'review_weight', CASE
                WHEN review.id IS NULL THEN 1.0
                WHEN review.reflection_eligible THEN review.evidence_weight
                ELSE 0.0
            END,
            'review_item_id', review.id,
            'payload_envelope', candidate.payload_envelope
        ) ORDER BY candidate.pattern_type, candidate.canonical_key
    ), '[]'::jsonb)
    INTO candidates
    FROM public.pattern_candidates AS candidate
    LEFT JOIN public.review_items AS review
      ON review.pattern_candidate_id = candidate.id
     AND review.user_id = candidate.user_id
     AND review.scope = 'pattern'
    WHERE candidate.user_id = p_user_id;

    RETURN pg_catalog.jsonb_build_object(
        'source_version', p_source_version,
        'basis_start', basis_start,
        'basis_end', latest_date,
        'valid_entry_count', valid_entry_count,
        'distinct_entry_dates', distinct_entry_dates,
        'reflective_word_count', reflective_word_count,
        'signals', signals,
        'candidates', candidates
    );
END
$function$;

CREATE OR REPLACE FUNCTION public.get_reflection_synthesis_basis(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_basis_days integer DEFAULT 90
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    basis jsonb;
    excluded_count integer;
    next_version integer;
    qualifications jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_basis_days <> 90
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;
    IF NOT FOUND
       OR job.job_type <> 'reflection_synthesis'
       OR job.entry_id IS NOT NULL
       OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
       OR job.source_version !~ '^[1-9][0-9]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    basis := public.get_reflection_candidate_basis(
        job.user_id,
        job.source_version::bigint,
        p_basis_days
    );

    SELECT pg_catalog.count(*)::integer
    INTO excluded_count
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = job.user_id
      AND analysis.eligibility <> 'accepted'
      AND analysis.source_version <= job.source_version::bigint
      AND entry.entry_date BETWEEN (basis ->> 'basis_start')::date
                               AND (basis ->> 'basis_end')::date;

    SELECT COALESCE(pg_catalog.max(snapshot.version), 0) + 1
    INTO next_version
    FROM public.reflection_snapshots AS snapshot
    WHERE snapshot.user_id = job.user_id;

    SELECT COALESCE(
        pg_catalog.jsonb_object_agg(
            review.pattern_candidate_id::text,
            'partly'
        ),
        '{}'::jsonb
    )
    INTO qualifications
    FROM public.review_items AS review
    WHERE review.user_id = job.user_id
      AND review.scope = 'pattern'
      AND review.reflection_eligible
      AND review.user_feedback ->> 'verdict' = 'partly_true';

    RETURN basis || pg_catalog.jsonb_build_object(
        'excluded_entry_count', excluded_count,
        'next_snapshot_version', next_version,
        'feedback_qualifications', qualifications
    );
END
$function$;

CREATE OR REPLACE FUNCTION public.is_reflection_recalculation_eligible(
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
      AND analysis.source_version > state.last_snapshot_source_version
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

    IF pending_valid_entries = 0 THEN
        RETURN false;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
        JOIN public.review_items AS review
          ON review.entry_signal_id = signal.id
         AND review.user_id = signal.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted'
          AND analysis.source_version > state.last_snapshot_source_version
          AND review.scope = 'entry_insight'
          AND review.reflection_eligible
          AND review.evidence_weight > 0
    ) INTO has_pending_signal;
    IF NOT has_pending_signal THEN
        RETURN false;
    END IF;

    IF state.last_successful_snapshot_id IS NULL
       OR state.last_snapshot_source_version = 0
    THEN
        SELECT pg_catalog.max(entry.entry_date)
        INTO current_end
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted'
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
          AND entry.entry_date BETWEEN current_start AND current_end
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
        RETURN basis_valid_entries >= 3
           AND basis_distinct_dates >= 2
           AND basis_reflective_words >= 150;
    END IF;

    RETURN pending_valid_entries >= 3
       OR pending_reflective_words >= 500
       OR (
           pending_valid_entries >= 1
           AND oldest_pending_valid_entry_at <= p_now - INTERVAL '3 days'
       );
END
$function$;

CREATE FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    p_user_id uuid,
    p_source_version bigint,
    p_candidates jsonb,
    p_candidate_evidence jsonb
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_candidate_evidence) <> 'array'
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
           JOIN public.entry_signals AS signal
             ON signal.id = (evidence.value ->> 'signal_id')::uuid
            AND signal.user_id = p_user_id
           LEFT JOIN public.review_items AS entry_review
             ON entry_review.entry_signal_id = signal.id
            AND entry_review.user_id = signal.user_id
            AND entry_review.scope = 'entry_insight'
           LEFT JOIN public.review_items AS pattern_review
             ON pattern_review.pattern_candidate_id =
                    (evidence.value ->> 'candidate_id')::uuid
            AND pattern_review.user_id = p_user_id
            AND pattern_review.scope = 'pattern'
           WHERE entry_review.id IS NULL
              OR entry_review.reflection_eligible IS NOT TRUE
              OR entry_review.evidence_weight <= 0
              OR pg_catalog.abs(
                    (evidence.value ->> 'evidence_weight')::numeric
                    - signal.confidence * entry_review.evidence_weight
                      * CASE
                          WHEN pattern_review.id IS NULL THEN 1.0
                          WHEN pattern_review.reflection_eligible
                              THEN pattern_review.evidence_weight
                          ELSE 0.0
                        END
                 ) > 0.00001
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
           WHERE NOT EXISTS (
               SELECT 1
               FROM public.entry_signals AS signal
               WHERE signal.id = (evidence.value ->> 'signal_id')::uuid
                 AND signal.user_id = p_user_id
           )
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'invalid weighted candidate evidence';
    END IF;

    RETURN public.apply_deterministic_reflection_candidates(
        p_user_id,
        p_source_version,
        p_candidates,
        p_candidate_evidence
    );
END
$function$;

CREATE FUNCTION public.apply_weighted_reflection_snapshot(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_snapshot jsonb,
    p_candidates jsonb,
    p_candidate_evidence jsonb,
    p_insights jsonb,
    p_snapshot_evidence jsonb,
    p_pattern_review_items jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    snapshot_id uuid;
    item jsonb;
    expected_entry_ids uuid[];
    expected_dates date[];
    persisted_review_count integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_snapshot) <> 'object'
       OR pg_catalog.jsonb_typeof(p_candidates) <> 'array'
       OR pg_catalog.jsonb_typeof(p_candidate_evidence) <> 'array'
       OR pg_catalog.jsonb_typeof(p_insights) <> 'array'
       OR pg_catalog.jsonb_typeof(p_snapshot_evidence) <> 'array'
       OR pg_catalog.jsonb_typeof(p_pattern_review_items) <> 'array'
       OR p_snapshot ->> 'model_name' IS NULL
       OR pg_catalog.btrim(p_snapshot ->> 'model_name') = ''
       OR p_snapshot ->> 'prompt_version' IS NULL
       OR pg_catalog.btrim(p_snapshot ->> 'prompt_version') = ''
       OR p_snapshot ->> 'generated_at' IS NULL
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_pattern_review_items) AS review(value)
           WHERE pg_catalog.jsonb_typeof(review.value) <> 'object'
              OR NOT review.value ?& ARRAY[
                    'id', 'pattern_candidate_id', 'item_type', 'category',
                    'statement_envelope', 'source_entry_ids', 'source_dates',
                    'inference_level', 'model_confidence', 'metadata'
              ]
              OR review.value - ARRAY[
                    'id', 'pattern_candidate_id', 'item_type', 'category',
                    'statement_envelope', 'source_entry_ids', 'source_dates',
                    'inference_level', 'model_confidence', 'metadata'
              ] <> '{}'::jsonb
              OR review.value ->> 'item_type'
                    NOT IN ('hidden_driver', 'recurring_loop', 'inner_tension')
              OR review.value ->> 'category'
                    IS DISTINCT FROM review.value ->> 'item_type'
              OR review.value ->> 'inference_level'
                    IS DISTINCT FROM 'synthesized'
              OR public.is_valid_encrypted_envelope_v1(
                    review.value -> 'statement_envelope'
                 ) IS NOT TRUE
              OR (review.value ->> 'model_confidence')::numeric NOT BETWEEN 0 AND 1
              OR pg_catalog.jsonb_typeof(review.value -> 'source_entry_ids') <> 'array'
              OR pg_catalog.jsonb_typeof(review.value -> 'source_dates') <> 'array'
              OR pg_catalog.jsonb_typeof(review.value -> 'metadata') <> 'object'
              OR pg_catalog.jsonb_array_length(
                    review.value -> 'source_entry_ids'
                 ) NOT BETWEEN 1 AND 100
              OR pg_catalog.jsonb_array_length(
                    review.value -> 'source_dates'
                 ) NOT BETWEEN 1 AND 100
              OR NOT (review.value -> 'metadata') ?& ARRAY[
                    'model_id', 'prompt_version', 'source',
                    'source_version', 'candidate_version'
              ]
              OR (review.value -> 'metadata') - ARRAY[
                    'model_id', 'prompt_version', 'source',
                    'source_version', 'candidate_version'
              ] <> '{}'::jsonb
              OR review.value #>> '{metadata,model_id}'
                    IS DISTINCT FROM p_snapshot ->> 'model_name'
              OR review.value #>> '{metadata,prompt_version}'
                    IS DISTINCT FROM p_snapshot ->> 'prompt_version'
              OR review.value #>> '{metadata,source}'
                    IS DISTINCT FROM 'reflection_synthesis'
              OR review.value #>> '{metadata,source_version}'
                    IS DISTINCT FROM p_snapshot ->> 'source_version'
              OR NOT EXISTS (
                  SELECT 1
                  FROM pg_catalog.jsonb_array_elements(p_candidates)
                       AS candidate(value)
                  WHERE candidate.value ->> 'id'
                            = review.value ->> 'pattern_candidate_id'
                    AND candidate.value ->> 'pattern_type'
                            = review.value ->> 'item_type'
                    AND candidate.value ->> 'version'
                            = review.value #>> '{metadata,candidate_version}'
                    AND (candidate.value ->> 'score')::numeric
                            = (review.value ->> 'model_confidence')::numeric
              )
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_pattern_review_items) AS review(value)
           GROUP BY review.value ->> 'id'
           HAVING pg_catalog.count(*) > 1
       )
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_pattern_review_items) AS review(value)
           GROUP BY review.value ->> 'pattern_candidate_id'
           HAVING pg_catalog.count(*) > 1
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'invalid weighted snapshot payload';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id;
    IF NOT FOUND OR job.user_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    IF job.status = 'completed'
       AND job.job_type = 'reflection_synthesis'
       AND job.claim_token IS NOT DISTINCT FROM p_claim_token
    THEN
        SELECT snapshot.id INTO snapshot_id
        FROM public.reflection_snapshots AS snapshot
        WHERE snapshot.user_id = job.user_id
          AND snapshot.source_version = job.source_version::bigint;
        IF snapshot_id IS NULL THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
        END IF;
        RETURN snapshot_id;
    END IF;

    IF (
        SELECT pg_catalog.count(*)
        FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
        WHERE insight.value ->> 'status' = 'available'
    ) <> pg_catalog.jsonb_array_length(p_pattern_review_items)
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
           WHERE insight.value ->> 'status' = 'available'
             AND NOT EXISTS (
                 SELECT 1
                 FROM pg_catalog.jsonb_array_elements(
                     p_pattern_review_items
                 ) AS review(value)
                 WHERE review.value ->> 'pattern_candidate_id'
                        = insight.value ->> 'candidate_id'
                   AND review.value ->> 'item_type'
                        = insight.value ->> 'pattern_type'
             )
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'pattern review mapping is incomplete';
    END IF;

    PERFORM public.apply_weighted_deterministic_reflection_candidates(
        job.user_id,
        (p_snapshot ->> 'source_version')::bigint,
        p_candidates,
        p_candidate_evidence
    );

    FOR item IN
        SELECT value
        FROM pg_catalog.jsonb_array_elements(p_pattern_review_items)
    LOOP
        SELECT pg_catalog.array_agg(source.entry_id ORDER BY source.entry_id),
               pg_catalog.array_agg(
                   DISTINCT source.entry_date ORDER BY source.entry_date
               )
        INTO expected_entry_ids, expected_dates
        FROM (
            SELECT DISTINCT signal.entry_id, entry.entry_date
            FROM pg_catalog.jsonb_array_elements(
                p_candidate_evidence
            ) AS evidence(value)
            JOIN public.entry_signals AS signal
              ON signal.id = (evidence.value ->> 'signal_id')::uuid
             AND signal.user_id = job.user_id
            JOIN public.entries AS entry
              ON entry.id = signal.entry_id
             AND entry.user_id = signal.user_id
            WHERE evidence.value ->> 'candidate_id'
                    = item ->> 'pattern_candidate_id'
              AND evidence.value ->> 'evidence_role' = 'supporting'
            ORDER BY entry.entry_date, signal.entry_id
            LIMIT 100
        ) AS source;

        IF expected_entry_ids IS NULL
           OR expected_dates IS NULL
           OR expected_entry_ids <> ARRAY(
                SELECT value::uuid
                FROM pg_catalog.jsonb_array_elements_text(
                    item -> 'source_entry_ids'
                ) AS source(value)
                ORDER BY value::uuid
           )
           OR expected_dates <> ARRAY(
                SELECT value::date
                FROM pg_catalog.jsonb_array_elements_text(
                    item -> 'source_dates'
                ) AS source(value)
                ORDER BY value::date
           )
        THEN
            RAISE EXCEPTION USING
                ERRCODE = '22023', MESSAGE = 'pattern review evidence is invalid';
        END IF;
    END LOOP;

    snapshot_id := public.apply_reflection_snapshot(
        p_job_id,
        p_worker_id,
        p_claim_token,
        p_snapshot,
        p_candidates,
        p_candidate_evidence,
        p_insights,
        p_snapshot_evidence
    );

    UPDATE public.reflection_snapshots
    SET model_name = p_snapshot ->> 'model_name',
        prompt_version = p_snapshot ->> 'prompt_version',
        generated_at = (p_snapshot ->> 'generated_at')::timestamptz
    WHERE id = snapshot_id AND user_id = job.user_id;

    INSERT INTO public.review_items (
        id, user_id, pattern_candidate_id, scope, item_type, category,
        statement_envelope, source_entry_ids, source_dates, inference_level,
        model_confidence, review_status, evidence_weight,
        reflection_eligible, metadata
    )
    SELECT (review.value ->> 'id')::uuid,
           job.user_id,
           (review.value ->> 'pattern_candidate_id')::uuid,
           'pattern',
           review.value ->> 'item_type',
           review.value ->> 'category',
           review.value -> 'statement_envelope',
           ARRAY(
               SELECT value::uuid
               FROM pg_catalog.jsonb_array_elements_text(
                   review.value -> 'source_entry_ids'
               ) AS source(value)
           ),
           ARRAY(
               SELECT value::date
               FROM pg_catalog.jsonb_array_elements_text(
                   review.value -> 'source_dates'
               ) AS source(value)
           ),
           'synthesized',
           (review.value ->> 'model_confidence')::numeric,
           'pending',
           1.0,
           true,
           review.value -> 'metadata'
    FROM pg_catalog.jsonb_array_elements(p_pattern_review_items) AS review(value)
    ON CONFLICT (pattern_candidate_id)
        WHERE pattern_candidate_id IS NOT NULL
    DO UPDATE SET
        item_type = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.item_type
            ELSE public.review_items.item_type
        END,
        category = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.category
            ELSE public.review_items.category
        END,
        statement_envelope = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.statement_envelope
            ELSE public.review_items.statement_envelope
        END,
        source_entry_ids = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.source_entry_ids
            ELSE public.review_items.source_entry_ids
        END,
        source_dates = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.source_dates
            ELSE public.review_items.source_dates
        END,
        inference_level = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.inference_level
            ELSE public.review_items.inference_level
        END,
        model_confidence = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN EXCLUDED.model_confidence
            ELSE public.review_items.model_confidence
        END,
        reflection_eligible = true,
        metadata = CASE
            WHEN public.review_items.user_feedback IS NULL
                THEN public.review_items.metadata || EXCLUDED.metadata
            ELSE public.review_items.metadata
        END
    WHERE public.review_items.id = EXCLUDED.id;
    GET DIAGNOSTICS persisted_review_count = ROW_COUNT;
    IF persisted_review_count <> pg_catalog.jsonb_array_length(
        p_pattern_review_items
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'pattern review identity mismatch';
    END IF;

    UPDATE public.pattern_candidates AS candidate
    SET status = CASE
            WHEN review.evidence_weight = 0.5 THEN 'weakened'
            WHEN review.evidence_weight = 0.0 THEN 'rejected'
            ELSE candidate.status
        END
    FROM public.review_items AS review
    WHERE review.pattern_candidate_id = candidate.id
      AND review.user_id = candidate.user_id
      AND candidate.user_id = job.user_id
      AND candidate.id IN (
          SELECT (value ->> 'id')::uuid
          FROM pg_catalog.jsonb_array_elements(p_candidates)
      );

    RETURN snapshot_id;
END
$function$;

REVOKE ALL ON FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.apply_weighted_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_weighted_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
REVOKE ALL ON FUNCTION public.apply_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.apply_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

COMMENT ON FUNCTION public.apply_weighted_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb
) IS
    'Atomically persists a review-weighted snapshot and idempotent encrypted Pattern Review rows without replacing prior feedback.';
