-- Entry deletion is a new reflection source event. Review feedback introduced
-- synthetic source versions that can be newer than every surviving analysis,
-- so deriving state from max(entry_analyses.source_version) can move a user's
-- source state backwards and make stale work appear current.
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
    next_source bigint;
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
        WHERE user_id = p_user_id
          AND id = ANY(affected_candidates)
          AND status <> 'rejected';
    END IF;
    IF accepted IS TRUE THEN
        next_source := pg_catalog.nextval(
            'public.entry_analyses_source_version_seq'::pg_catalog.regclass
        );
        UPDATE public.reflection_snapshots
        SET status = 'stale'
        WHERE id = (
            SELECT last_successful_snapshot_id FROM public.reflection_user_state
            WHERE user_id = p_user_id
        );
        UPDATE public.reflection_user_state
        SET latest_accepted_source_version = next_source,
            last_schedule_local_date = NULL,
            new_valid_entries = (
                SELECT pg_catalog.count(*)::integer
                FROM public.entry_analyses
                WHERE user_id = p_user_id
                  AND eligibility = 'accepted'
                  AND source_version >
                      public.reflection_user_state.last_snapshot_source_version
            ),
            new_accepted_signals = (
                SELECT pg_catalog.count(*)::integer
                FROM public.entry_signals AS signal
                JOIN public.entry_analyses AS analysis
                  ON analysis.id = signal.analysis_id
                 AND analysis.user_id = signal.user_id
                WHERE signal.user_id = p_user_id
                  AND analysis.eligibility = 'accepted'
                  AND analysis.source_version >
                      public.reflection_user_state.last_snapshot_source_version
            ),
            pending_local_dates = COALESCE((
                SELECT pg_catalog.array_agg(
                    DISTINCT entry.entry_date ORDER BY entry.entry_date
                )
                FROM public.entry_analyses AS analysis
                JOIN public.entries AS entry
                  ON entry.id = analysis.entry_id
                 AND entry.user_id = analysis.user_id
                WHERE analysis.user_id = p_user_id
                  AND analysis.eligibility = 'accepted'
                  AND analysis.source_version >
                      public.reflection_user_state.last_snapshot_source_version
            ), '{}'::date[])
        WHERE user_id = p_user_id;
    END IF;
    RETURN true;
END
$function$;

COMMENT ON FUNCTION public.delete_entry_with_reflection_for_owner(uuid, uuid) IS
'Owner-only entry deletion that cascades Review evidence and advances reflection source state monotonically.';
