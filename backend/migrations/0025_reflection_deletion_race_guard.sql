-- A source can be deleted after synthesis loads its encrypted basis but before
-- persistence. Take the same owner lock as deletion and reject a stale source
-- version before validating evidence that may already have cascaded away.
CREATE OR REPLACE FUNCTION public.apply_weighted_deterministic_reflection_candidates(
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
    current_source_version bigint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    IF p_user_id IS NULL
       OR p_source_version IS NULL
       OR p_source_version < 0
       OR p_candidates IS NULL
       OR p_candidate_evidence IS NULL
       OR pg_catalog.jsonb_typeof(p_candidates) <> 'array'
       OR pg_catalog.jsonb_typeof(p_candidate_evidence) <> 'array'
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'invalid weighted candidate input';
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'orion-reflection:' || p_user_id::text,
            0
        )
    );
    SELECT state.latest_accepted_source_version
    INTO current_source_version
    FROM public.reflection_user_state AS state
    WHERE state.user_id = p_user_id
    FOR UPDATE;
    IF current_source_version IS DISTINCT FROM p_source_version THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001', MESSAGE = 'stale candidate basis';
    END IF;

    IF EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(
               p_candidate_evidence
           ) AS evidence(value)
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
           FROM pg_catalog.jsonb_array_elements(
               p_candidate_evidence
           ) AS evidence(value)
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

REVOKE ALL ON FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) TO orion_worker;

COMMENT ON FUNCTION public.apply_weighted_deterministic_reflection_candidates(
    uuid, bigint, jsonb, jsonb
) IS
    'Applies weighted candidates only while the locked owner source version remains current.';
