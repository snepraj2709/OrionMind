-- Owner-scoped, replaceable Review feedback with idempotent source-version
-- invalidation. Correction and note plaintext never enter this function.

CREATE FUNCTION public.put_review_feedback_for_owner(
    p_user_id uuid,
    p_item_id uuid,
    p_verdict text,
    p_corrected_statement_envelope jsonb,
    p_corrected_statement_fingerprint text,
    p_corrected_statement_compatible_fingerprints text[],
    p_feedback_note_envelope jsonb,
    p_feedback_note_fingerprint text,
    p_feedback_note_compatible_fingerprints text[]
)
RETURNS TABLE (
    item_id uuid,
    changed boolean,
    source_version bigint,
    updated_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.review_items%ROWTYPE;
    state public.reflection_user_state%ROWTYPE;
    candidate public.pattern_candidates%ROWTYPE;
    next_status text;
    next_weight numeric(2,1);
    next_source_version bigint;
    feedback_at timestamptz := pg_catalog.now();
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_item_id IS NULL
       OR p_verdict IS NULL
       OR p_corrected_statement_fingerprint IS NULL
       OR p_corrected_statement_compatible_fingerprints IS NULL
       OR p_feedback_note_fingerprint IS NULL
       OR p_feedback_note_compatible_fingerprints IS NULL
       OR p_corrected_statement_fingerprint
            !~ '^(|[a-z0-9][a-z0-9._-]{0,63}:[0-9a-f]{64})$'
       OR p_feedback_note_fingerprint
            !~ '^(|[a-z0-9][a-z0-9._-]{0,63}:[0-9a-f]{64})$'
       OR pg_catalog.cardinality(
            p_corrected_statement_compatible_fingerprints
       ) < 1
       OR pg_catalog.array_position(
            p_corrected_statement_compatible_fingerprints, NULL
       ) IS NOT NULL
       OR NOT (
            p_corrected_statement_fingerprint
            = ANY(p_corrected_statement_compatible_fingerprints)
       )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(
                p_corrected_statement_compatible_fingerprints
            ) AS compatible(fingerprint)
            WHERE compatible.fingerprint
                !~ '^(|[a-z0-9][a-z0-9._-]{0,63}:[0-9a-f]{64})$'
       )
       OR pg_catalog.cardinality(
            p_feedback_note_compatible_fingerprints
       ) < 1
       OR pg_catalog.array_position(
            p_feedback_note_compatible_fingerprints, NULL
       ) IS NOT NULL
       OR NOT (
            p_feedback_note_fingerprint
            = ANY(p_feedback_note_compatible_fingerprints)
       )
       OR EXISTS (
            SELECT 1
            FROM pg_catalog.unnest(
                p_feedback_note_compatible_fingerprints
            ) AS compatible(fingerprint)
            WHERE compatible.fingerprint
                !~ '^(|[a-z0-9][a-z0-9._-]{0,63}:[0-9a-f]{64})$'
       )
       OR (
            p_corrected_statement_envelope IS NULL
       ) IS DISTINCT FROM (
            p_corrected_statement_fingerprint = ''
       )
       OR (
            p_feedback_note_envelope IS NULL
       ) IS DISTINCT FROM (
            p_feedback_note_fingerprint = ''
       )
       OR (
            p_corrected_statement_envelope IS NOT NULL
            AND public.is_valid_encrypted_envelope_v1(
                p_corrected_statement_envelope
            ) IS NOT TRUE
       )
       OR (
            p_feedback_note_envelope IS NOT NULL
            AND public.is_valid_encrypted_envelope_v1(
                p_feedback_note_envelope
            ) IS NOT TRUE
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'invalid review feedback';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'orion-reflection:' || p_user_id::text,
            0
        )
    );
    SELECT * INTO item
    FROM public.review_items
    WHERE id = p_item_id AND user_id = p_user_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0002', MESSAGE = 'review item not found';
    END IF;
    IF item.reflection_eligible IS NOT TRUE THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0003', MESSAGE = 'review item is stale';
    END IF;

    IF item.scope = 'entry_insight' THEN
        IF p_verdict = 'accurate' THEN
            next_status := 'confirmed';
            next_weight := 1.0;
        ELSIF p_verdict = 'partly_accurate' THEN
            next_status := 'partially_confirmed';
            next_weight := 0.5;
        ELSIF p_verdict = 'not_accurate' THEN
            next_status := 'rejected';
            next_weight := 0.0;
        ELSE
            RAISE EXCEPTION USING
                ERRCODE = '22023', MESSAGE = 'invalid review feedback';
        END IF;
    ELSIF item.scope = 'pattern' THEN
        SELECT * INTO candidate
        FROM public.pattern_candidates
        WHERE id = item.pattern_candidate_id AND user_id = p_user_id
        FOR UPDATE;
        IF NOT FOUND OR candidate.status = 'superseded' THEN
            RAISE EXCEPTION USING
                ERRCODE = 'P0003', MESSAGE = 'review item is stale';
        END IF;
        IF p_verdict = 'resonates' THEN
            next_status := 'confirmed';
            next_weight := 1.0;
        ELSIF p_verdict = 'partly_true' THEN
            next_status := 'partially_confirmed';
            next_weight := 0.5;
        ELSIF p_verdict = 'not_true' THEN
            next_status := 'rejected';
            next_weight := 0.0;
        ELSE
            RAISE EXCEPTION USING
                ERRCODE = '22023', MESSAGE = 'invalid review feedback';
        END IF;
    ELSE
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'invalid review feedback';
    END IF;

    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0003', MESSAGE = 'review item is stale';
    END IF;

    IF item.user_feedback ->> 'verdict' IS NOT DISTINCT FROM p_verdict
       AND item.metadata ->> 'feedback_correction_fingerprint'
            = ANY(p_corrected_statement_compatible_fingerprints)
       AND item.metadata ->> 'feedback_note_fingerprint'
            = ANY(p_feedback_note_compatible_fingerprints)
    THEN
        RETURN QUERY SELECT
            item.id,
            false,
            state.latest_accepted_source_version,
            item.updated_at;
        RETURN;
    END IF;

    next_source_version := pg_catalog.nextval(
        'public.entry_analyses_source_version_seq'::pg_catalog.regclass
    );
    UPDATE public.review_items
    SET review_status = next_status,
        user_feedback = pg_catalog.jsonb_build_object(
            'verdict', p_verdict,
            'updated_at', feedback_at
        ),
        corrected_statement_envelope = p_corrected_statement_envelope,
        feedback_note_envelope = p_feedback_note_envelope,
        evidence_weight = next_weight,
        metadata = metadata || pg_catalog.jsonb_build_object(
            'feedback_correction_fingerprint',
            p_corrected_statement_fingerprint,
            'feedback_note_fingerprint',
            p_feedback_note_fingerprint
        )
    WHERE id = item.id AND user_id = p_user_id
    RETURNING * INTO item;

    IF item.scope = 'pattern' THEN
        UPDATE public.pattern_candidates
        SET status = CASE
                WHEN p_verdict = 'resonates' THEN 'published'
                WHEN p_verdict = 'partly_true' THEN 'weakened'
                ELSE 'rejected'
            END,
            rejected_at = CASE
                WHEN p_verdict = 'not_true' THEN feedback_at
                ELSE NULL
            END,
            rejected_source_version = CASE
                WHEN p_verdict = 'not_true' THEN next_source_version
                ELSE NULL
            END,
            version = version + 1
        WHERE id = item.pattern_candidate_id AND user_id = p_user_id;
    END IF;

    UPDATE public.reflection_user_state
    SET latest_accepted_source_version = next_source_version,
        last_processing_error_code = NULL
    WHERE user_id = p_user_id;
    UPDATE public.reflection_snapshots
    SET status = 'stale'
    WHERE id = state.last_successful_snapshot_id
      AND user_id = p_user_id
      AND status = 'available';

    RETURN QUERY SELECT
        item.id,
        true,
        next_source_version,
        item.updated_at;
END
$function$;

REVOKE ALL ON FUNCTION public.put_review_feedback_for_owner(
    uuid, uuid, text, jsonb, text, text[], jsonb, text, text[]
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.put_review_feedback_for_owner(
    uuid, uuid, text, jsonb, text, text[], jsonb, text, text[]
) TO authenticated;

COMMENT ON FUNCTION public.put_review_feedback_for_owner(
    uuid, uuid, text, jsonb, text, text[], jsonb, text, text[]
) IS
    'Atomically replaces owner Review feedback, preserves idempotent replay, and invalidates the cached reflection source version.';
