-- P0-07: bounded, owner-checked aggregate read for the Reflection API.

CREATE FUNCTION public.get_reflections_for_owner(
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
    snapshot_id uuid;
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

    SELECT profile.timezone
    INTO owner_timezone
    FROM public.user_profiles AS profile
    WHERE profile.user_id = p_user_id;
    IF owner_timezone IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'profile not found';
    END IF;

    SELECT pg_catalog.jsonb_build_object(
        'latest_accepted_source_version', state.latest_accepted_source_version,
        'last_snapshot_source_version', state.last_snapshot_source_version,
        'last_processing_error_code', state.last_processing_error_code
    )
    INTO state_payload
    FROM public.reflection_user_state AS state
    WHERE state.user_id = p_user_id;

    SELECT pg_catalog.jsonb_build_object(
        'status', job.status,
        'source_version', job.source_version,
        'created_at', job.created_at
    )
    INTO job_payload
    FROM public.processing_jobs AS job
    WHERE job.user_id = p_user_id
      AND job.job_type = 'reflection_synthesis'
    ORDER BY job.created_at DESC, job.id DESC
    LIMIT 1;

    SELECT snapshot.id, snapshot.basis_start, snapshot.basis_end,
           snapshot.source_version,
           pg_catalog.jsonb_build_object(
               'id', snapshot.id,
               'version', snapshot.version,
               'source_version', snapshot.source_version,
               'basis_start', snapshot.basis_start,
               'basis_end', snapshot.basis_end,
               'valid_entry_count', snapshot.valid_entry_count,
               'excluded_entry_count', snapshot.excluded_entry_count,
               'distinct_entry_dates', snapshot.distinct_entry_dates,
               'reflective_word_count', snapshot.reflective_word_count,
               'status', snapshot.status,
               'created_at', snapshot.created_at,
               'excluded_reasons', COALESCE((
                   SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
                   FROM (
                       SELECT analysis.entry_kind,
                              pg_catalog.count(*)::integer AS total
                       FROM public.entry_analyses AS analysis
                       JOIN public.entries AS entry
                         ON entry.id = analysis.entry_id
                        AND entry.user_id = analysis.user_id
                       WHERE analysis.user_id = p_user_id
                         AND analysis.eligibility <> 'accepted'
                         AND analysis.source_version <= snapshot.source_version
                         AND entry.entry_date BETWEEN snapshot.basis_start AND snapshot.basis_end
                       GROUP BY analysis.entry_kind
                       ORDER BY analysis.entry_kind
                   ) AS summary
               ), '{}'::jsonb)
           )
    INTO snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload
    FROM public.reflection_snapshots AS snapshot
    LEFT JOIN public.reflection_user_state AS state
      ON state.user_id = snapshot.user_id
    WHERE snapshot.user_id = p_user_id
    ORDER BY (snapshot.id = state.last_successful_snapshot_id) DESC,
             snapshot.version DESC, snapshot.id DESC
    LIMIT 1;

    SELECT COALESCE(pg_catalog.max(entry.entry_date),
                    (pg_catalog.now() AT TIME ZONE owner_timezone)::date)
    INTO current_end
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id;
    current_start := current_end - 89;

    SELECT pg_catalog.jsonb_build_object(
        'basis_start', current_start,
        'basis_end', current_end,
        'valid_entry_count', pg_catalog.count(*) FILTER (
            WHERE analysis.eligibility = 'accepted'
        )::integer,
        'excluded_entry_count', pg_catalog.count(*) FILTER (
            WHERE analysis.eligibility <> 'accepted'
        )::integer,
        'distinct_entry_dates', pg_catalog.count(DISTINCT entry.entry_date)::integer,
        'reflective_word_count', COALESCE(pg_catalog.sum(analysis.reflective_word_count)
            FILTER (WHERE analysis.eligibility = 'accepted'), 0)::integer,
        'excluded_reasons', COALESCE((
            SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
            FROM (
                SELECT excluded.entry_kind, pg_catalog.count(*)::integer AS total
                FROM public.entry_analyses AS excluded
                JOIN public.entries AS excluded_entry
                  ON excluded_entry.id = excluded.entry_id
                 AND excluded_entry.user_id = excluded.user_id
                WHERE excluded.user_id = p_user_id
                  AND excluded.eligibility <> 'accepted'
                  AND excluded_entry.entry_date BETWEEN current_start AND current_end
                GROUP BY excluded.entry_kind
                ORDER BY excluded.entry_kind
            ) AS summary
        ), '{}'::jsonb)
    )
    INTO current_basis
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND entry.entry_date BETWEEN current_start AND current_end;

    IF snapshot_id IS NOT NULL THEN
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
                'id', insight.id,
                'pattern_type', insight.pattern_type,
                'ordinal', insight.ordinal,
                'status', insight.status,
                'reason_code', insight.reason_code,
                'payload_envelope', insight.payload_envelope,
                'confidence_label', insight.confidence_label,
                'score', insight.score
            )) ORDER BY insight.pattern_type, insight.ordinal
        ), '[]'::jsonb)
        INTO insight_payload
        FROM public.reflection_snapshot_insights AS insight
        WHERE insight.user_id = p_user_id
          AND insight.snapshot_id = snapshot_id;

        WITH ranked AS (
            SELECT evidence.*,
                   pg_catalog.row_number() OVER (
                       PARTITION BY evidence.insight_id
                       ORDER BY CASE evidence.evidence_role
                           WHEN 'supporting' THEN 0 ELSE 1 END,
                           evidence.ordinal, evidence.signal_id
                   ) AS evidence_rank
            FROM public.reflection_snapshot_evidence AS evidence
            JOIN public.reflection_snapshot_insights AS insight
              ON insight.id = evidence.insight_id
             AND insight.user_id = evidence.user_id
            WHERE evidence.user_id = p_user_id
              AND insight.snapshot_id = snapshot_id
        )
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', ranked.insight_id,
                'signal_id', ranked.signal_id,
                'entry_id', ranked.entry_id,
                'evidence_role', ranked.evidence_role,
                'ordinal', ranked.ordinal,
                'source_start', ranked.source_start,
                'source_end', ranked.source_end,
                'entry_date', entry.entry_date,
                'input_type', entry.input_type,
                'entry_content_envelope', entry.content_envelope,
                'signal_payload_envelope', signal.payload_envelope,
                'themes', signal.themes
            ) ORDER BY ranked.insight_id, ranked.evidence_rank
        ), '[]'::jsonb)
        INTO evidence_payload
        FROM ranked
        JOIN public.entry_signals AS signal
          ON signal.id = ranked.signal_id AND signal.user_id = ranked.user_id
        JOIN public.entries AS entry
          ON entry.id = ranked.entry_id AND entry.user_id = ranked.user_id
        WHERE ranked.evidence_rank <= p_evidence_limit;

        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', feedback.insight_id,
                'response', feedback.response,
                'updated_at', feedback.updated_at
            ) ORDER BY feedback.insight_id
        ), '[]'::jsonb)
        INTO feedback_payload
        FROM public.reflection_feedback AS feedback
        WHERE feedback.user_id = p_user_id
          AND feedback.snapshot_id = snapshot_id;
    END IF;

    RETURN pg_catalog.jsonb_build_object(
        'state', state_payload,
        'job', job_payload,
        'snapshot', snapshot_payload,
        'current_basis', current_basis,
        'insights', insight_payload,
        'evidence', evidence_payload,
        'feedback', feedback_payload
    );
END
$function$;

REVOKE ALL ON FUNCTION public.get_reflections_for_owner(uuid, integer)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.get_reflections_for_owner(uuid, integer)
    TO authenticated;
