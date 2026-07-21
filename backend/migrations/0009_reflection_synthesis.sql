CREATE FUNCTION public.get_reflection_synthesis_basis(
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
        pg_catalog.jsonb_object_agg(latest.candidate_id::text, latest.response),
        '{}'::jsonb
    )
    INTO qualifications
    FROM (
        SELECT current.candidate_id, current.response
        FROM (
            SELECT DISTINCT ON (feedback.candidate_id)
                feedback.candidate_id,
                feedback.response
            FROM public.reflection_feedback AS feedback
            WHERE feedback.user_id = job.user_id
            ORDER BY feedback.candidate_id, feedback.updated_at DESC, feedback.id DESC
        ) AS current
        WHERE current.response = 'partly'
    ) AS latest;

    RETURN basis || pg_catalog.jsonb_build_object(
        'excluded_entry_count', excluded_count,
        'next_snapshot_version', next_version,
        'feedback_qualifications', qualifications
    );
END
$function$;

CREATE OR REPLACE FUNCTION public.apply_reflection_snapshot(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_snapshot jsonb,
    p_candidates jsonb,
    p_candidate_evidence jsonb,
    p_insights jsonb,
    p_snapshot_evidence jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    state public.reflection_user_state%ROWTYPE;
    existing public.pattern_candidates%ROWTYPE;
    basis jsonb;
    snapshot_id uuid;
    snapshot_source bigint;
    snapshot_version integer;
    item jsonb;
    candidate_id uuid;
    changed_ids uuid[] := '{}'::uuid[];
    inserted_count integer;
    expected_version integer;
    new_entry_count integer;
    new_date_count integer;
    inner_count integer;
    inner_available integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_snapshot) <> 'object'
       OR pg_catalog.jsonb_typeof(p_candidates) <> 'array'
       OR pg_catalog.jsonb_typeof(p_candidate_evidence) <> 'array'
       OR pg_catalog.jsonb_typeof(p_insights) <> 'array'
       OR pg_catalog.jsonb_typeof(p_snapshot_evidence) <> 'array'
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
       AND job.job_type = 'reflection_synthesis'
       AND job.claim_token IS NOT DISTINCT FROM p_claim_token
    THEN
        SELECT snapshot.id INTO snapshot_id
        FROM public.reflection_snapshots AS snapshot
        WHERE snapshot.user_id = job.user_id
          AND snapshot.source_version = job.source_version::bigint;
        IF snapshot_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
        END IF;
        RETURN snapshot_id;
    END IF;
    IF job.job_type <> 'reflection_synthesis'
       OR job.entry_id IS NOT NULL
       OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
       OR job.source_version !~ '^[1-9][0-9]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = job.user_id
    FOR UPDATE;

    snapshot_id := (p_snapshot ->> 'id')::uuid;
    snapshot_source := (p_snapshot ->> 'source_version')::bigint;
    snapshot_version := (p_snapshot ->> 'version')::integer;
    IF state.user_id IS NULL
       OR snapshot_id IS NULL
       OR snapshot_source::text <> job.source_version
       OR snapshot_source <= state.last_snapshot_source_version
       OR snapshot_source > state.latest_accepted_source_version
       OR EXISTS (
            SELECT 1 FROM public.reflection_snapshots AS snapshot
            WHERE snapshot.user_id = job.user_id
              AND (snapshot.source_version = snapshot_source
                   OR snapshot.version = snapshot_version
                   OR snapshot.id = snapshot_id)
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale snapshot source';
    END IF;

    basis := public.get_reflection_synthesis_basis(
        p_job_id,
        p_worker_id,
        p_claim_token,
        90
    );
    IF snapshot_version <> (basis ->> 'next_snapshot_version')::integer
       OR (p_snapshot ->> 'basis_start')::date
            IS DISTINCT FROM (basis ->> 'basis_start')::date
       OR (p_snapshot ->> 'basis_end')::date
            IS DISTINCT FROM (basis ->> 'basis_end')::date
       OR (p_snapshot ->> 'valid_entry_count')::integer
            IS DISTINCT FROM (basis ->> 'valid_entry_count')::integer
       OR (p_snapshot ->> 'excluded_entry_count')::integer
            IS DISTINCT FROM (basis ->> 'excluded_entry_count')::integer
       OR (p_snapshot ->> 'distinct_entry_dates')::integer
            IS DISTINCT FROM (basis ->> 'distinct_entry_dates')::integer
       OR (p_snapshot ->> 'reflective_word_count')::integer
            IS DISTINCT FROM (basis ->> 'reflective_word_count')::integer
       OR p_snapshot ->> 'status' IS DISTINCT FROM 'available'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot basis';
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'id' IS NULL
           OR value ->> 'pattern_type' IS NULL
           OR value ->> 'canonical_key' IS NULL
           OR value ->> 'version' IS NULL
           OR value ->> 'publication_gate_passed' IS NULL
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        GROUP BY value ->> 'id' HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        GROUP BY value ->> 'pattern_type', value ->> 'canonical_key'
        HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'candidate_id' IS NULL
           OR value ->> 'signal_id' IS NULL
           OR value ->> 'evidence_role' IS NULL
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS row(value)
        GROUP BY value ->> 'candidate_id', value ->> 'signal_id', value ->> 'evidence_role'
        HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'id' IS NULL
           OR value ->> 'pattern_type' IS NULL
           OR value ->> 'ordinal' IS NULL
           OR value ->> 'status' IS NULL
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS row(value)
        GROUP BY value ->> 'id' HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS row(value)
        GROUP BY value ->> 'pattern_type', value ->> 'ordinal'
        HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'insight_id' IS NULL
           OR value ->> 'signal_id' IS NULL
           OR value ->> 'evidence_role' IS NULL
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS row(value)
        GROUP BY value ->> 'insight_id', value ->> 'signal_id', value ->> 'evidence_role'
        HAVING pg_catalog.count(*) > 1
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot payload';
    END IF;

    SELECT pg_catalog.count(*)::integer INTO inner_count
    FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
    WHERE value ->> 'pattern_type' = 'inner_tension';
    SELECT pg_catalog.count(*)::integer INTO inner_available
    FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
    WHERE value ->> 'pattern_type' = 'inner_tension'
      AND value ->> 'status' = 'available';
    IF (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
        WHERE value ->> 'pattern_type' = 'hidden_driver') <> 1
       OR (SELECT pg_catalog.count(*) FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
           WHERE value ->> 'pattern_type' = 'recurring_loop') <> 1
       OR inner_count < 1
       OR EXISTS (
            SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
            WHERE value ->> 'pattern_type' IN ('hidden_driver', 'recurring_loop')
              AND (value ->> 'ordinal')::integer <> 0
       )
       OR (inner_available = 0 AND (
            inner_count <> 1
            OR EXISTS (
                SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
                WHERE value ->> 'pattern_type' = 'inner_tension'
                  AND ((value ->> 'ordinal')::integer <> 0
                       OR value ->> 'status' <> 'insufficient_evidence')
            )
       ))
       OR (inner_available > 0 AND (
            inner_available <> inner_count
            OR (SELECT pg_catalog.min((value ->> 'ordinal')::integer)
                FROM pg_catalog.jsonb_array_elements(p_insights)
                WHERE value ->> 'pattern_type' = 'inner_tension') <> 0
            OR (SELECT pg_catalog.max((value ->> 'ordinal')::integer)
                FROM pg_catalog.jsonb_array_elements(p_insights)
                WHERE value ->> 'pattern_type' = 'inner_tension') <> inner_count - 1
       ))
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot sections';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
        WHERE value ->> 'status' = 'available'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidates) AS candidate(value)
              WHERE candidate.value ->> 'id' = insight.value ->> 'candidate_id'
                AND candidate.value ->> 'pattern_type' = insight.value ->> 'pattern_type'
                AND candidate.value ->> 'status' = 'published'
                AND (candidate.value ->> 'publication_gate_passed')::boolean
          )
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidates) AS candidate(value)
        WHERE value ->> 'status' = 'published'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
              WHERE insight.value ->> 'status' = 'available'
                AND insight.value ->> 'candidate_id' = candidate.value ->> 'id'
          )
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
        WHERE value ->> 'status' = 'available'
          AND NOT EXISTS (
              SELECT 1 FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS evidence(value)
              WHERE evidence.value ->> 'insight_id' = insight.value ->> 'id'
                AND evidence.value ->> 'evidence_role' = 'supporting'
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid published insight';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
        LEFT JOIN public.entry_signals AS signal
          ON signal.id = (evidence.value ->> 'signal_id')::uuid
         AND signal.user_id = job.user_id
        LEFT JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        LEFT JOIN public.entries AS entry
          ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
        WHERE NOT EXISTS (
                  SELECT 1 FROM pg_catalog.jsonb_array_elements(p_candidates) AS candidate(value)
                  WHERE candidate.value ->> 'id' = evidence.value ->> 'candidate_id'
              )
           OR signal.id IS NULL
           OR analysis.eligibility IS DISTINCT FROM 'accepted'
           OR analysis.source_version > snapshot_source
           OR entry.entry_date NOT BETWEEN (basis ->> 'basis_start')::date
                                       AND (basis ->> 'basis_end')::date
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS evidence(value)
        LEFT JOIN pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
          ON insight.value ->> 'id' = evidence.value ->> 'insight_id'
         AND insight.value ->> 'status' = 'available'
        LEFT JOIN public.entry_signals AS signal
          ON signal.id = (evidence.value ->> 'signal_id')::uuid
         AND signal.user_id = job.user_id
        LEFT JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        LEFT JOIN public.entries AS entry
          ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
        WHERE insight.value IS NULL
           OR signal.id IS NULL
           OR signal.entry_id IS DISTINCT FROM (evidence.value ->> 'entry_id')::uuid
           OR signal.source_start IS DISTINCT FROM (evidence.value ->> 'source_start')::integer
           OR signal.source_end IS DISTINCT FROM (evidence.value ->> 'source_end')::integer
           OR analysis.eligibility IS DISTINCT FROM 'accepted'
           OR analysis.source_version > snapshot_source
           OR entry.entry_date NOT BETWEEN (basis ->> 'basis_start')::date
                                       AND (basis ->> 'basis_end')::date
           OR NOT EXISTS (
                SELECT 1
                FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS candidate_evidence(value)
                WHERE candidate_evidence.value ->> 'candidate_id' = insight.value ->> 'candidate_id'
                  AND candidate_evidence.value ->> 'signal_id' = evidence.value ->> 'signal_id'
                  AND candidate_evidence.value ->> 'evidence_role' = evidence.value ->> 'evidence_role'
           )
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_insights) AS insight(value)
        JOIN pg_catalog.jsonb_array_elements(p_candidate_evidence) AS candidate_evidence(value)
          ON candidate_evidence.value ->> 'candidate_id' = insight.value ->> 'candidate_id'
        WHERE insight.value ->> 'status' = 'available'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS evidence(value)
              WHERE evidence.value ->> 'insight_id' = insight.value ->> 'id'
                AND evidence.value ->> 'signal_id' = candidate_evidence.value ->> 'signal_id'
                AND evidence.value ->> 'evidence_role' = candidate_evidence.value ->> 'evidence_role'
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot evidence';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_candidates)
    LOOP
        candidate_id := (item ->> 'id')::uuid;
        existing := NULL;
        SELECT * INTO existing
        FROM public.pattern_candidates AS candidate
        WHERE candidate.user_id = job.user_id
          AND candidate.pattern_type = item ->> 'pattern_type'
          AND candidate.canonical_key = item ->> 'canonical_key'
        FOR UPDATE;
        IF existing.id IS NOT NULL AND existing.id IS DISTINCT FROM candidate_id THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'candidate identity mismatch';
        END IF;
        IF existing.id IS NOT NULL AND existing.last_source_version > snapshot_source THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate source';
        END IF;
        expected_version := CASE
            WHEN existing.id IS NULL THEN 1
            WHEN existing.last_source_version = snapshot_source THEN existing.version
            ELSE existing.version + 1
        END;
        IF (item ->> 'version')::integer <> expected_version THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate version';
        END IF;
        IF existing.status = 'rejected' AND item ->> 'status' <> 'rejected' THEN
            IF item ->> 'status' <> 'candidate' THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'rejected candidate suppressed';
            END IF;
            SELECT pg_catalog.count(DISTINCT signal.entry_id)::integer,
                   pg_catalog.count(DISTINCT entry.entry_date)::integer
            INTO new_entry_count, new_date_count
            FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
            JOIN public.entry_signals AS signal
              ON signal.id = (evidence.value ->> 'signal_id')::uuid
             AND signal.user_id = job.user_id
            JOIN public.entry_analyses AS analysis
              ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
            JOIN public.entries AS entry
              ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
            WHERE evidence.value ->> 'candidate_id' = candidate_id::text
              AND evidence.value ->> 'evidence_role' = 'supporting'
              AND analysis.source_version > existing.rejected_source_version;
            IF (item ->> 'publication_gate_passed')::boolean IS NOT TRUE
               OR new_entry_count < 3
               OR new_date_count < 2
            THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'rejected candidate suppressed';
            END IF;
        END IF;

        INSERT INTO public.pattern_candidates (
            id, user_id, pattern_type, canonical_key, status, score,
            score_components, payload_envelope, first_seen_at, last_seen_at,
            version, rejected_at, rejected_source_version, last_source_version
        ) VALUES (
            candidate_id, job.user_id, item ->> 'pattern_type',
            item ->> 'canonical_key', item ->> 'status',
            (item ->> 'score')::numeric, item -> 'score_components',
            item -> 'payload_envelope', (item ->> 'first_seen_at')::timestamptz,
            (item ->> 'last_seen_at')::timestamptz,
            (item ->> 'version')::integer,
            (item ->> 'rejected_at')::timestamptz,
            (item ->> 'rejected_source_version')::bigint,
            snapshot_source
        )
        ON CONFLICT (id) DO UPDATE SET
            pattern_type = EXCLUDED.pattern_type,
            canonical_key = EXCLUDED.canonical_key,
            status = EXCLUDED.status,
            score = EXCLUDED.score,
            score_components = EXCLUDED.score_components,
            payload_envelope = EXCLUDED.payload_envelope,
            first_seen_at = EXCLUDED.first_seen_at,
            last_seen_at = EXCLUDED.last_seen_at,
            version = EXCLUDED.version,
            rejected_at = EXCLUDED.rejected_at,
            rejected_source_version = EXCLUDED.rejected_source_version,
            last_source_version = EXCLUDED.last_source_version,
            updated_at = pg_catalog.now()
        WHERE public.pattern_candidates.user_id = job.user_id
          AND public.pattern_candidates.last_source_version <= snapshot_source;
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate source';
        END IF;
        changed_ids := pg_catalog.array_append(changed_ids, candidate_id);
    END LOOP;

    DELETE FROM public.pattern_candidate_evidence AS evidence
    WHERE evidence.user_id = job.user_id
      AND evidence.candidate_id = ANY(changed_ids);
    INSERT INTO public.pattern_candidate_evidence (
        candidate_id, signal_id, user_id, evidence_role, evidence_weight
    )
    SELECT (evidence.value ->> 'candidate_id')::uuid,
           (evidence.value ->> 'signal_id')::uuid,
           job.user_id,
           evidence.value ->> 'evidence_role',
           (evidence.value ->> 'evidence_weight')::numeric
    FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value);

    INSERT INTO public.reflection_snapshots (
        id, user_id, version, source_version, basis_start, basis_end,
        valid_entry_count, excluded_entry_count, distinct_entry_dates,
        reflective_word_count, status
    ) VALUES (
        snapshot_id, job.user_id, snapshot_version, snapshot_source,
        (p_snapshot ->> 'basis_start')::date,
        (p_snapshot ->> 'basis_end')::date,
        (p_snapshot ->> 'valid_entry_count')::integer,
        (p_snapshot ->> 'excluded_entry_count')::integer,
        (p_snapshot ->> 'distinct_entry_dates')::integer,
        (p_snapshot ->> 'reflective_word_count')::integer,
        'available'
    );

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_insights)
    LOOP
        INSERT INTO public.reflection_snapshot_insights (
            id, user_id, snapshot_id, candidate_id, pattern_type, ordinal,
            status, reason_code, payload_envelope, confidence_label, score
        ) VALUES (
            (item ->> 'id')::uuid, job.user_id, snapshot_id,
            (item ->> 'candidate_id')::uuid, item ->> 'pattern_type',
            (item ->> 'ordinal')::smallint, item ->> 'status',
            item ->> 'reason_code', item -> 'payload_envelope',
            item ->> 'confidence_label', (item ->> 'score')::numeric
        );
    END LOOP;

    INSERT INTO public.reflection_snapshot_evidence (
        insight_id, signal_id, entry_id, user_id, evidence_role, ordinal,
        source_start, source_end
    )
    SELECT (evidence.value ->> 'insight_id')::uuid,
           signal.id,
           signal.entry_id,
           job.user_id,
           evidence.value ->> 'evidence_role',
           (evidence.value ->> 'ordinal')::smallint,
           signal.source_start,
           signal.source_end
    FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence) AS evidence(value)
    JOIN public.entry_signals AS signal
      ON signal.id = (evidence.value ->> 'signal_id')::uuid
     AND signal.user_id = job.user_id;

    UPDATE public.reflection_user_state
    SET last_snapshot_source_version = snapshot_source,
        last_successful_snapshot_id = snapshot_id,
        new_valid_entries = (
            SELECT pg_catalog.count(*)::integer
            FROM public.entry_analyses
            WHERE user_id = job.user_id
              AND eligibility = 'accepted'
              AND source_version > snapshot_source
        ),
        new_accepted_signals = (
            SELECT pg_catalog.count(*)::integer
            FROM public.entry_signals AS signal
            JOIN public.entry_analyses AS analysis
              ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
            WHERE signal.user_id = job.user_id
              AND analysis.eligibility = 'accepted'
              AND analysis.source_version > snapshot_source
        ),
        pending_local_dates = COALESCE((
            SELECT pg_catalog.array_agg(DISTINCT entry.entry_date ORDER BY entry.entry_date)
            FROM public.entry_analyses AS analysis
            JOIN public.entries AS entry
              ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
            WHERE analysis.user_id = job.user_id
              AND analysis.eligibility = 'accepted'
              AND analysis.source_version > snapshot_source
        ), '{}'::date[]),
        last_processing_error_code = NULL,
        updated_at = pg_catalog.now()
    WHERE user_id = job.user_id;

    UPDATE public.processing_jobs
    SET status = 'completed',
        worker_id = NULL,
        heartbeat_at = NULL,
        completed_at = pg_catalog.now(),
        last_error_code = NULL,
        updated_at = pg_catalog.now()
    WHERE id = job.id
      AND status = 'running'
      AND worker_id = p_worker_id
      AND claim_token = p_claim_token;
    GET DIAGNOSTICS inserted_count = ROW_COUNT;
    IF inserted_count <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    RETURN snapshot_id;
END
$function$;

REVOKE ALL ON FUNCTION public.get_reflection_synthesis_basis(uuid, text, uuid, integer)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_reflection_synthesis_basis(uuid, text, uuid, integer)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
