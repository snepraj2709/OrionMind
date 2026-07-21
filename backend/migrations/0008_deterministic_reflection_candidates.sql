ALTER TABLE public.pattern_candidates
    ADD COLUMN last_source_version bigint NOT NULL DEFAULT 0,
    ADD CONSTRAINT pattern_candidates_source_version_check
        CHECK (last_source_version >= 0);

CREATE INDEX pattern_candidates_owner_source_idx
    ON public.pattern_candidates (user_id, last_source_version DESC, id);

CREATE FUNCTION public.get_reflection_candidate_basis(
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
      AND analysis.source_version <= p_source_version;

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
      AND entry.entry_date BETWEEN basis_start AND latest_date;

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
            'confidence', signal.confidence,
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
            'payload_envelope', candidate.payload_envelope
        ) ORDER BY candidate.pattern_type, candidate.canonical_key
    ), '[]'::jsonb)
    INTO candidates
    FROM public.pattern_candidates AS candidate
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

CREATE FUNCTION public.apply_deterministic_reflection_candidates(
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
DECLARE
    state public.reflection_user_state%ROWTYPE;
    item jsonb;
    existing public.pattern_candidates%ROWTYPE;
    candidate_id uuid;
    changed_ids uuid[] := '{}'::uuid[];
    inserted_count integer;
    new_entry_count integer;
    new_date_count integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_source_version < 0
       OR pg_catalog.jsonb_typeof(p_candidates) <> 'array'
       OR pg_catalog.jsonb_typeof(p_candidate_evidence) <> 'array'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'id' IS NULL
           OR value ->> 'pattern_type' IS NULL
           OR value ->> 'canonical_key' IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        GROUP BY value ->> 'id'
        HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidates) AS row(value)
        GROUP BY value ->> 'pattern_type', value ->> 'canonical_key'
        HAVING pg_catalog.count(*) > 1
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS row(value)
        WHERE pg_catalog.jsonb_typeof(value) <> 'object'
           OR value ->> 'candidate_id' IS NULL
           OR value ->> 'signal_id' IS NULL
           OR value ->> 'evidence_role' IS NULL
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS row(value)
        GROUP BY value ->> 'candidate_id', value ->> 'signal_id', value ->> 'evidence_role'
        HAVING pg_catalog.count(*) > 1
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid candidate payload';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || p_user_id::text, 0)
    );
    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id
    FOR UPDATE;
    IF state.user_id IS NULL
       OR state.latest_accepted_source_version <> p_source_version
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate basis';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
        WHERE NOT EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(p_candidates) AS candidate(value)
            WHERE candidate.value ->> 'id' = evidence.value ->> 'candidate_id'
        )
    ) OR EXISTS (
        SELECT 1
        FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
        LEFT JOIN public.entry_signals AS signal
          ON signal.id = (evidence.value ->> 'signal_id')::uuid
         AND signal.user_id = p_user_id
        LEFT JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        WHERE signal.id IS NULL
           OR analysis.eligibility IS DISTINCT FROM 'accepted'
           OR analysis.source_version > p_source_version
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid candidate evidence';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_candidates)
    LOOP
        candidate_id := (item ->> 'id')::uuid;
        existing := NULL;
        SELECT * INTO existing
        FROM public.pattern_candidates AS candidate
        WHERE candidate.user_id = p_user_id
          AND candidate.pattern_type = item ->> 'pattern_type'
          AND candidate.canonical_key = item ->> 'canonical_key'
        FOR UPDATE;

        IF existing.id IS NOT NULL AND existing.id IS DISTINCT FROM candidate_id THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'candidate identity mismatch';
        END IF;
        IF existing.id IS NOT NULL AND existing.last_source_version > p_source_version THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate basis';
        END IF;
        IF existing.id IS NOT NULL AND existing.last_source_version = p_source_version THEN
            CONTINUE;
        END IF;

        IF existing.status = 'rejected' AND item ->> 'status' <> 'rejected' THEN
            SELECT pg_catalog.count(DISTINCT signal.entry_id)::integer,
                   pg_catalog.count(DISTINCT entry.entry_date)::integer
            INTO new_entry_count, new_date_count
            FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
            JOIN public.entry_signals AS signal
              ON signal.id = (evidence.value ->> 'signal_id')::uuid
             AND signal.user_id = p_user_id
            JOIN public.entry_analyses AS analysis
              ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
            JOIN public.entries AS entry
              ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
            WHERE evidence.value ->> 'candidate_id' = candidate_id::text
              AND evidence.value ->> 'evidence_role' = 'supporting'
              AND analysis.eligibility = 'accepted'
              AND analysis.source_version > existing.rejected_source_version;
            IF COALESCE((item ->> 'publication_gate_passed')::boolean, false) IS NOT TRUE
               OR new_entry_count < 3 OR new_date_count < 2
            THEN
                RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'rejected candidate suppressed';
            END IF;
        END IF;

        INSERT INTO public.pattern_candidates (
            id, user_id, pattern_type, canonical_key, status, score,
            score_components, payload_envelope, first_seen_at, last_seen_at,
            version, rejected_at, rejected_source_version, last_source_version
        ) VALUES (
            candidate_id, p_user_id, item ->> 'pattern_type',
            item ->> 'canonical_key', item ->> 'status',
            (item ->> 'score')::numeric, item -> 'score_components',
            item -> 'payload_envelope', (item ->> 'first_seen_at')::timestamptz,
            (item ->> 'last_seen_at')::timestamptz,
            (item ->> 'version')::integer,
            (item ->> 'rejected_at')::timestamptz,
            (item ->> 'rejected_source_version')::bigint,
            p_source_version
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
            last_source_version = EXCLUDED.last_source_version
        WHERE public.pattern_candidates.user_id = p_user_id
          AND public.pattern_candidates.last_source_version < p_source_version;
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale candidate basis';
        END IF;
        changed_ids := pg_catalog.array_append(changed_ids, candidate_id);
    END LOOP;

    DELETE FROM public.pattern_candidate_evidence AS evidence
    WHERE evidence.user_id = p_user_id
      AND evidence.candidate_id = ANY(changed_ids);

    INSERT INTO public.pattern_candidate_evidence (
        candidate_id, signal_id, user_id, evidence_role, evidence_weight
    )
    SELECT (evidence.value ->> 'candidate_id')::uuid,
           (evidence.value ->> 'signal_id')::uuid,
           p_user_id,
           evidence.value ->> 'evidence_role',
           (evidence.value ->> 'evidence_weight')::numeric
    FROM pg_catalog.jsonb_array_elements(p_candidate_evidence) AS evidence(value)
    WHERE (evidence.value ->> 'candidate_id')::uuid = ANY(changed_ids);

    RETURN pg_catalog.cardinality(changed_ids);
END
$function$;

REVOKE ALL ON FUNCTION public.get_reflection_candidate_basis(uuid, bigint, integer)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_reflection_candidate_basis(uuid, bigint, integer)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) TO orion_worker;
