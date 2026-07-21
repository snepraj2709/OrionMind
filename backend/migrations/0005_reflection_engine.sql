-- MVP Reflection Engine database foundation.
-- This migration is additive. public.reflections remains the entry-level extraction table.

CREATE FUNCTION public.is_valid_encrypted_envelope_v1(envelope jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = ''
AS $function$
DECLARE
    key_count integer;
    salt_bytes bytea;
    nonce_bytes bytea;
    ciphertext_bytes bytea;
    tag_bytes bytea;
BEGIN
    IF pg_catalog.jsonb_typeof(envelope) <> 'object' THEN
        RETURN false;
    END IF;
    SELECT pg_catalog.count(*) INTO key_count
    FROM pg_catalog.jsonb_object_keys(envelope);
    IF key_count <> 8
       OR NOT envelope ?& ARRAY[
           'version', 'algorithm', 'key_id', 'kdf', 'salt', 'nonce', 'ciphertext', 'tag'
       ]
       OR pg_catalog.jsonb_typeof(envelope -> 'version') <> 'number'
       OR pg_catalog.jsonb_typeof(envelope -> 'algorithm') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'key_id') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'kdf') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'salt') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'nonce') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'ciphertext') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'tag') <> 'string'
       OR envelope ->> 'version' <> '1'
       OR envelope ->> 'algorithm' <> 'AES-256-GCM'
       OR envelope ->> 'kdf' <> 'HKDF-SHA256'
       OR envelope ->> 'key_id' !~ '^[a-z0-9][a-z0-9._-]{0,63}$'
       OR pg_catalog.length(envelope ->> 'ciphertext') = 0
       OR pg_catalog.length(envelope ->> 'ciphertext') > 1000000
       OR pg_catalog.pg_column_size(envelope) > 1100000
    THEN
        RETURN false;
    END IF;
    salt_bytes := pg_catalog.decode(envelope ->> 'salt', 'base64');
    nonce_bytes := pg_catalog.decode(envelope ->> 'nonce', 'base64');
    ciphertext_bytes := pg_catalog.decode(envelope ->> 'ciphertext', 'base64');
    tag_bytes := pg_catalog.decode(envelope ->> 'tag', 'base64');
    RETURN pg_catalog.octet_length(salt_bytes) = 32
       AND pg_catalog.octet_length(nonce_bytes) = 12
       AND pg_catalog.octet_length(ciphertext_bytes) > 0
       AND pg_catalog.octet_length(tag_bytes) = 16
       AND pg_catalog.replace(pg_catalog.encode(salt_bytes, 'base64'), E'\n', '') = envelope ->> 'salt'
       AND pg_catalog.replace(pg_catalog.encode(nonce_bytes, 'base64'), E'\n', '') = envelope ->> 'nonce'
       AND pg_catalog.replace(pg_catalog.encode(ciphertext_bytes, 'base64'), E'\n', '') = envelope ->> 'ciphertext'
       AND pg_catalog.replace(pg_catalog.encode(tag_bytes, 'base64'), E'\n', '') = envelope ->> 'tag';
EXCEPTION WHEN OTHERS THEN
    RETURN false;
END
$function$;

CREATE FUNCTION public.is_unit_interval_json_object(payload jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = ''
AS $function$
DECLARE
    pair record;
    numeric_value numeric;
BEGIN
    IF pg_catalog.jsonb_typeof(payload) <> 'object' THEN
        RETURN false;
    END IF;
    FOR pair IN
        SELECT object_item.key AS item_key, object_item.value AS item_value
        FROM pg_catalog.jsonb_each(payload) AS object_item
    LOOP
        IF pg_catalog.jsonb_typeof(pair.item_value) <> 'number' THEN
            RETURN false;
        END IF;
        numeric_value := (pair.item_value #>> '{}')::numeric;
        IF numeric_value < 0 OR numeric_value > 1 OR numeric_value = 'NaN'::numeric THEN
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
EXCEPTION WHEN OTHERS THEN
    RETURN false;
END
$function$;

CREATE TABLE public.entry_analyses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_version bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    entry_kind text NOT NULL,
    model_eligibility text NOT NULL,
    eligibility text NOT NULL,
    deterministic_features jsonb NOT NULL,
    semantic_scores jsonb NOT NULL,
    exclusion_reason_codes text[] NOT NULL DEFAULT '{}'::text[],
    ngram_sketch text[] NOT NULL DEFAULT '{}'::text[],
    redacted_text_envelope jsonb NOT NULL,
    offset_map_envelope jsonb NOT NULL,
    reflective_word_count integer NOT NULL,
    duplicate_cluster_key text,
    model_id text NOT NULL,
    prompt_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (entry_id),
    UNIQUE (id, user_id),
    UNIQUE (user_id, source_version),
    CONSTRAINT entry_analyses_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT entry_analyses_kind_check CHECK (entry_kind IN (
        'personal_reflection', 'personal_event', 'personal_observation',
        'task_or_note', 'informational_text', 'creative_writing',
        'test_or_noise', 'copied_or_quoted_text', 'unclear'
    )),
    CONSTRAINT entry_analyses_model_eligibility_check CHECK (
        model_eligibility IN ('accepted', 'uncertain', 'excluded')
    ),
    CONSTRAINT entry_analyses_eligibility_check CHECK (
        eligibility IN ('accepted', 'uncertain', 'excluded')
    ),
    CONSTRAINT entry_analyses_features_check CHECK (
        pg_catalog.jsonb_typeof(deterministic_features) = 'object'
        AND public.is_unit_interval_json_object(semantic_scores)
    ),
    CONSTRAINT entry_analyses_reason_codes_check CHECK (
        pg_catalog.cardinality(exclusion_reason_codes) <= 10
        AND (
            pg_catalog.cardinality(exclusion_reason_codes) = 0
            OR pg_catalog.array_to_string(exclusion_reason_codes, ',')
                ~ '^[A-Z][A-Z0-9_]*(,[A-Z][A-Z0-9_]*)*$'
        )
    ),
    CONSTRAINT entry_analyses_ngram_sketch_check CHECK (
        pg_catalog.cardinality(ngram_sketch) <= 128
        AND (
            pg_catalog.cardinality(ngram_sketch) = 0
            OR pg_catalog.array_to_string(ngram_sketch, ',')
                ~ '^[0-9a-f]{16}(,[0-9a-f]{16})*$'
        )
    ),
    CONSTRAINT entry_analyses_envelopes_check CHECK (
        public.is_valid_encrypted_envelope_v1(redacted_text_envelope)
        AND public.is_valid_encrypted_envelope_v1(offset_map_envelope)
    ),
    CONSTRAINT entry_analyses_words_check CHECK (reflective_word_count >= 0),
    CONSTRAINT entry_analyses_duplicate_key_check CHECK (
        duplicate_cluster_key IS NULL OR duplicate_cluster_key ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT entry_analyses_model_check CHECK (
        model_id = pg_catalog.btrim(model_id) AND pg_catalog.length(model_id) BETWEEN 1 AND 100
        AND prompt_version = pg_catalog.btrim(prompt_version)
        AND pg_catalog.length(prompt_version) BETWEEN 1 AND 100
    )
);

CREATE INDEX entry_analyses_owner_source_idx
    ON public.entry_analyses (user_id, source_version DESC);
CREATE INDEX entry_analyses_owner_eligibility_idx
    ON public.entry_analyses (user_id, eligibility, source_version DESC);
CREATE INDEX entry_analyses_owner_duplicate_idx
    ON public.entry_analyses (user_id, duplicate_cluster_key)
    WHERE duplicate_cluster_key IS NOT NULL;

CREATE TABLE public.entry_signals (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    analysis_id uuid NOT NULL,
    signal_type text NOT NULL,
    normalized_label_fingerprint text NOT NULL,
    payload_envelope jsonb NOT NULL,
    themes text[] NOT NULL DEFAULT '{}'::text[],
    need_tags text[] NOT NULL DEFAULT '{}'::text[],
    loop_role text,
    confidence numeric(6,5) NOT NULL,
    source_start integer NOT NULL,
    source_end integer NOT NULL,
    occurred_on date NOT NULL,
    duplicate_cluster_key text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (id, user_id),
    CONSTRAINT entry_signals_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT entry_signals_analysis_owner_fk FOREIGN KEY (analysis_id, user_id)
        REFERENCES public.entry_analyses(id, user_id) ON DELETE CASCADE,
    CONSTRAINT entry_signals_type_check CHECK (signal_type IN (
        'event', 'emotion', 'energy_gain', 'energy_loss', 'desire',
        'avoidance', 'belief', 'self_statement', 'action', 'outcome',
        'conflict', 'protective_strategy', 'realization'
    )),
    CONSTRAINT entry_signals_fingerprint_check CHECK (
        normalized_label_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT entry_signals_payload_check CHECK (
        public.is_valid_encrypted_envelope_v1(payload_envelope)
    ),
    CONSTRAINT entry_signals_themes_check CHECK (
        pg_catalog.cardinality(themes) <= 3
        AND themes <@ ARRAY[
            'career', 'money', 'health', 'love_life', 'family_friends',
            'personal_growth', 'fun_recreation', 'home_lifestyle'
        ]::text[]
    ),
    CONSTRAINT entry_signals_needs_check CHECK (
        pg_catalog.cardinality(need_tags) <= 4
        AND need_tags <@ ARRAY[
            'autonomy', 'competence', 'mastery', 'belonging', 'recognition',
            'security', 'stability', 'novelty', 'exploration', 'meaning',
            'contribution', 'creative_expression', 'rest', 'physical_vitality',
            'clarity', 'control'
        ]::text[]
    ),
    CONSTRAINT entry_signals_loop_role_check CHECK (
        loop_role IS NULL OR loop_role IN (
            'trigger', 'initial_reward', 'interpretation', 'emotional_response',
            'action', 'avoidance', 'short_term_protection', 'long_term_cost',
            'recovery', 'reinforcement'
        )
    ),
    CONSTRAINT entry_signals_confidence_check CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT entry_signals_offsets_check CHECK (
        source_start >= 0 AND source_start < source_end
    ),
    CONSTRAINT entry_signals_duplicate_key_check CHECK (
        duplicate_cluster_key IS NULL OR duplicate_cluster_key ~ '^[0-9a-f]{64}$'
    )
);

CREATE INDEX entry_signals_owner_date_idx
    ON public.entry_signals (user_id, occurred_on DESC, id);
CREATE INDEX entry_signals_owner_type_date_idx
    ON public.entry_signals (user_id, signal_type, occurred_on DESC);
CREATE INDEX entry_signals_owner_label_date_idx
    ON public.entry_signals (user_id, normalized_label_fingerprint, occurred_on DESC);
CREATE INDEX entry_signals_need_tags_idx ON public.entry_signals USING gin (need_tags);
CREATE INDEX entry_signals_themes_idx ON public.entry_signals USING gin (themes);

CREATE TABLE public.user_pii_vaults (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    mapping_envelope jsonb NOT NULL CONSTRAINT user_pii_vaults_envelope_check
        CHECK (public.is_valid_encrypted_envelope_v1(mapping_envelope)),
    mapping_version integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    CONSTRAINT user_pii_vaults_version_check CHECK (mapping_version >= 1)
);

CREATE TABLE public.processing_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid,
    job_type text NOT NULL,
    source_version text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    run_after timestamptz NOT NULL DEFAULT pg_catalog.now(),
    attempts smallint NOT NULL DEFAULT 0,
    worker_id text,
    claim_token uuid,
    heartbeat_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    completed_at timestamptz,
    UNIQUE (user_id, job_type, source_version),
    UNIQUE (id, user_id),
    CONSTRAINT processing_jobs_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT processing_jobs_type_check CHECK (
        job_type IN ('entry_processing', 'reflection_synthesis')
    ),
    CONSTRAINT processing_jobs_entry_type_check CHECK (
        (job_type = 'entry_processing' AND entry_id IS NOT NULL)
        OR (job_type = 'reflection_synthesis' AND entry_id IS NULL)
    ),
    CONSTRAINT processing_jobs_source_check CHECK (
        source_version = pg_catalog.btrim(source_version)
        AND pg_catalog.length(source_version) BETWEEN 1 AND 200
        AND (
            (job_type = 'entry_processing' AND source_version = entry_id::text)
            OR (job_type = 'reflection_synthesis' AND source_version ~ '^[1-9][0-9]*$')
        )
    ),
    CONSTRAINT processing_jobs_status_check CHECK (
        status IN ('pending', 'running', 'completed', 'failed')
    ),
    CONSTRAINT processing_jobs_attempts_check CHECK (attempts BETWEEN 0 AND 3),
    CONSTRAINT processing_jobs_worker_check CHECK (
        worker_id IS NULL OR (
            worker_id = pg_catalog.btrim(worker_id)
            AND pg_catalog.length(worker_id) BETWEEN 1 AND 100
        )
    ),
    CONSTRAINT processing_jobs_error_check CHECK (
        last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]*$'
    ),
    CONSTRAINT processing_jobs_lifecycle_check CHECK (
        (status = 'pending' AND worker_id IS NULL AND claim_token IS NULL
            AND heartbeat_at IS NULL AND completed_at IS NULL)
        OR (status = 'running' AND worker_id IS NOT NULL AND claim_token IS NOT NULL
            AND heartbeat_at IS NOT NULL AND completed_at IS NULL)
        OR (status IN ('completed', 'failed') AND worker_id IS NULL
            AND claim_token IS NOT NULL AND heartbeat_at IS NULL AND completed_at IS NOT NULL)
    )
);

CREATE INDEX processing_jobs_claim_idx
    ON public.processing_jobs (run_after, created_at, id)
    WHERE status = 'pending' AND attempts < 3;
CREATE INDEX processing_jobs_stale_idx
    ON public.processing_jobs (heartbeat_at, id) WHERE status = 'running';
CREATE INDEX processing_jobs_owner_type_status_idx
    ON public.processing_jobs (user_id, job_type, status, created_at DESC);

CREATE TABLE public.reflection_user_state (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    latest_accepted_source_version bigint NOT NULL DEFAULT 0,
    last_snapshot_source_version bigint NOT NULL DEFAULT 0,
    new_valid_entries integer NOT NULL DEFAULT 0,
    new_accepted_signals integer NOT NULL DEFAULT 0,
    pending_local_dates date[] NOT NULL DEFAULT '{}'::date[],
    last_schedule_local_date date,
    last_successful_snapshot_id uuid,
    last_processing_error_code text,
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    CONSTRAINT reflection_user_state_versions_check CHECK (
        latest_accepted_source_version >= 0
        AND last_snapshot_source_version >= 0
        AND last_snapshot_source_version <= latest_accepted_source_version
    ),
    CONSTRAINT reflection_user_state_counters_check CHECK (
        new_valid_entries >= 0 AND new_accepted_signals >= 0
        AND pg_catalog.cardinality(pending_local_dates) <= new_valid_entries
    ),
    CONSTRAINT reflection_user_state_error_check CHECK (
        last_processing_error_code IS NULL
        OR last_processing_error_code ~ '^[A-Z][A-Z0-9_]*$'
    )
);

CREATE TABLE public.pattern_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pattern_type text NOT NULL,
    canonical_key text NOT NULL,
    status text NOT NULL,
    score numeric(6,5) NOT NULL,
    score_components jsonb NOT NULL,
    payload_envelope jsonb NOT NULL,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    version integer NOT NULL DEFAULT 1,
    rejected_at timestamptz,
    rejected_source_version bigint,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (user_id, pattern_type, canonical_key),
    UNIQUE (id, user_id),
    CONSTRAINT pattern_candidates_type_check CHECK (
        pattern_type IN ('hidden_driver', 'recurring_loop', 'inner_tension')
    ),
    CONSTRAINT pattern_candidates_key_check CHECK (canonical_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT pattern_candidates_status_check CHECK (
        status IN ('candidate', 'published', 'weakened', 'superseded', 'rejected')
    ),
    CONSTRAINT pattern_candidates_score_check CHECK (score BETWEEN 0 AND 1),
    CONSTRAINT pattern_candidates_components_check CHECK (
        public.is_unit_interval_json_object(score_components)
    ),
    CONSTRAINT pattern_candidates_payload_check CHECK (
        public.is_valid_encrypted_envelope_v1(payload_envelope)
    ),
    CONSTRAINT pattern_candidates_time_check CHECK (first_seen_at <= last_seen_at),
    CONSTRAINT pattern_candidates_version_check CHECK (version >= 1),
    CONSTRAINT pattern_candidates_rejection_check CHECK (
        (status = 'rejected' AND rejected_at IS NOT NULL AND rejected_source_version IS NOT NULL)
        OR (status <> 'rejected' AND rejected_at IS NULL AND rejected_source_version IS NULL)
    )
);

CREATE INDEX pattern_candidates_owner_status_idx
    ON public.pattern_candidates (user_id, pattern_type, status, updated_at DESC, id);

CREATE TABLE public.pattern_candidate_evidence (
    candidate_id uuid NOT NULL,
    signal_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    evidence_role text NOT NULL,
    evidence_weight numeric(6,5) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    PRIMARY KEY (candidate_id, signal_id, evidence_role),
    CONSTRAINT pattern_candidate_evidence_candidate_owner_fk
        FOREIGN KEY (candidate_id, user_id)
        REFERENCES public.pattern_candidates(id, user_id) ON DELETE CASCADE,
    CONSTRAINT pattern_candidate_evidence_signal_owner_fk
        FOREIGN KEY (signal_id, user_id)
        REFERENCES public.entry_signals(id, user_id) ON DELETE CASCADE,
    CONSTRAINT pattern_candidate_evidence_role_check CHECK (
        evidence_role IN ('supporting', 'counter')
    ),
    CONSTRAINT pattern_candidate_evidence_weight_check CHECK (
        evidence_weight BETWEEN 0 AND 1
    )
);

CREATE INDEX pattern_candidate_evidence_owner_candidate_idx
    ON public.pattern_candidate_evidence (user_id, candidate_id, evidence_role);
CREATE INDEX pattern_candidate_evidence_owner_signal_idx
    ON public.pattern_candidate_evidence (user_id, signal_id);

CREATE TABLE public.reflection_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    version integer NOT NULL,
    source_version bigint NOT NULL,
    basis_start date NOT NULL,
    basis_end date NOT NULL,
    valid_entry_count integer NOT NULL,
    excluded_entry_count integer NOT NULL,
    distinct_entry_dates integer NOT NULL,
    reflective_word_count integer NOT NULL,
    status text NOT NULL DEFAULT 'available',
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (user_id, version),
    UNIQUE (user_id, source_version),
    UNIQUE (id, user_id),
    CONSTRAINT reflection_snapshots_version_check CHECK (version >= 1 AND source_version >= 1),
    CONSTRAINT reflection_snapshots_basis_check CHECK (basis_start <= basis_end),
    CONSTRAINT reflection_snapshots_counts_check CHECK (
        valid_entry_count >= 0 AND excluded_entry_count >= 0
        AND distinct_entry_dates >= 0 AND distinct_entry_dates <= valid_entry_count
        AND reflective_word_count >= 0
    ),
    CONSTRAINT reflection_snapshots_status_check CHECK (status IN ('available', 'stale'))
);

ALTER TABLE public.reflection_user_state
    ADD CONSTRAINT reflection_user_state_last_snapshot_fk
    FOREIGN KEY (last_successful_snapshot_id)
    REFERENCES public.reflection_snapshots(id) ON DELETE SET NULL;

CREATE INDEX reflection_snapshots_owner_latest_idx
    ON public.reflection_snapshots (user_id, version DESC, id);

CREATE TABLE public.reflection_snapshot_insights (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    candidate_id uuid,
    pattern_type text NOT NULL,
    ordinal smallint NOT NULL,
    status text NOT NULL,
    reason_code text,
    payload_envelope jsonb,
    confidence_label text,
    score numeric(6,5),
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (snapshot_id, pattern_type, ordinal),
    UNIQUE (id, user_id),
    CONSTRAINT reflection_snapshot_insights_snapshot_owner_fk
        FOREIGN KEY (snapshot_id, user_id)
        REFERENCES public.reflection_snapshots(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_snapshot_insights_candidate_owner_fk
        FOREIGN KEY (candidate_id, user_id)
        REFERENCES public.pattern_candidates(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_snapshot_insights_type_check CHECK (
        pattern_type IN ('hidden_driver', 'recurring_loop', 'inner_tension')
    ),
    CONSTRAINT reflection_snapshot_insights_ordinal_check CHECK (
        ordinal >= 0
        AND (pattern_type = 'inner_tension' OR ordinal = 0)
    ),
    CONSTRAINT reflection_snapshot_insights_status_check CHECK (
        status IN ('available', 'insufficient_evidence')
    ),
    CONSTRAINT reflection_snapshot_insights_reason_check CHECK (
        reason_code IS NULL OR reason_code IN (
            'NOT_ENOUGH_REFLECTIVE_CONTENT', 'DRIVER_NOT_REPEATED',
            'LOOP_NOT_REPEATED', 'BOTH_SIDES_NOT_SUPPORTED',
            'INSUFFICIENT_EVIDENCE'
        )
    ),
    CONSTRAINT reflection_snapshot_insights_confidence_check CHECK (
        confidence_label IS NULL OR confidence_label IN ('preliminary', 'emerging', 'recurring')
    ),
    CONSTRAINT reflection_snapshot_insights_score_check CHECK (
        score IS NULL OR score BETWEEN 0 AND 1
    ),
    CONSTRAINT reflection_snapshot_insights_payload_check CHECK (
        payload_envelope IS NULL OR public.is_valid_encrypted_envelope_v1(payload_envelope)
    ),
    CONSTRAINT reflection_snapshot_insights_state_check CHECK (
        (status = 'available' AND candidate_id IS NOT NULL AND reason_code IS NULL
            AND payload_envelope IS NOT NULL AND confidence_label IS NOT NULL AND score IS NOT NULL)
        OR (status = 'insufficient_evidence' AND candidate_id IS NULL AND reason_code IS NOT NULL
            AND payload_envelope IS NULL AND confidence_label IS NULL AND score IS NULL)
    )
);

CREATE INDEX reflection_snapshot_insights_owner_snapshot_idx
    ON public.reflection_snapshot_insights (user_id, snapshot_id, pattern_type, ordinal);

CREATE TABLE public.reflection_snapshot_evidence (
    insight_id uuid NOT NULL,
    signal_id uuid NOT NULL,
    entry_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    evidence_role text NOT NULL,
    ordinal smallint NOT NULL,
    source_start integer NOT NULL,
    source_end integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    PRIMARY KEY (insight_id, signal_id, evidence_role),
    CONSTRAINT reflection_snapshot_evidence_insight_owner_fk
        FOREIGN KEY (insight_id, user_id)
        REFERENCES public.reflection_snapshot_insights(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_snapshot_evidence_signal_owner_fk
        FOREIGN KEY (signal_id, user_id)
        REFERENCES public.entry_signals(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_snapshot_evidence_entry_owner_fk
        FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_snapshot_evidence_role_check CHECK (
        evidence_role IN ('supporting', 'counter')
    ),
    CONSTRAINT reflection_snapshot_evidence_ordinal_check CHECK (ordinal >= 0),
    CONSTRAINT reflection_snapshot_evidence_offsets_check CHECK (
        source_start >= 0 AND source_start < source_end
    ),
    UNIQUE (insight_id, evidence_role, ordinal)
);

CREATE INDEX reflection_snapshot_evidence_owner_insight_idx
    ON public.reflection_snapshot_evidence (user_id, insight_id, evidence_role, ordinal);
CREATE INDEX reflection_snapshot_evidence_owner_entry_idx
    ON public.reflection_snapshot_evidence (user_id, entry_id);

CREATE TABLE public.reflection_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    insight_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    response text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (user_id, snapshot_id, insight_id),
    CONSTRAINT reflection_feedback_snapshot_owner_fk FOREIGN KEY (snapshot_id, user_id)
        REFERENCES public.reflection_snapshots(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_feedback_insight_owner_fk FOREIGN KEY (insight_id, user_id)
        REFERENCES public.reflection_snapshot_insights(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_feedback_candidate_owner_fk FOREIGN KEY (candidate_id, user_id)
        REFERENCES public.pattern_candidates(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_feedback_response_check CHECK (
        response IN ('resonates', 'partly', 'rejected')
    )
);

CREATE INDEX reflection_feedback_owner_snapshot_idx
    ON public.reflection_feedback (user_id, snapshot_id, insight_id);

CREATE TRIGGER user_pii_vaults_set_updated_at
BEFORE UPDATE ON public.user_pii_vaults
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER processing_jobs_set_updated_at
BEFORE UPDATE ON public.processing_jobs
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER reflection_user_state_set_updated_at
BEFORE UPDATE ON public.reflection_user_state
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER pattern_candidates_set_updated_at
BEFORE UPDATE ON public.pattern_candidates
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER reflection_feedback_set_updated_at
BEFORE UPDATE ON public.reflection_feedback
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.entry_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entry_analyses FORCE ROW LEVEL SECURITY;
ALTER TABLE public.entry_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entry_signals FORCE ROW LEVEL SECURITY;
ALTER TABLE public.user_pii_vaults ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_pii_vaults FORCE ROW LEVEL SECURITY;
ALTER TABLE public.processing_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_user_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_user_state FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pattern_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pattern_candidates FORCE ROW LEVEL SECURITY;
ALTER TABLE public.pattern_candidate_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pattern_candidate_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshot_insights ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshot_insights FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshot_evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_snapshot_evidence FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_feedback FORCE ROW LEVEL SECURITY;

CREATE POLICY reflection_snapshots_select_owner ON public.reflection_snapshots
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY reflection_snapshot_insights_select_owner ON public.reflection_snapshot_insights
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY reflection_snapshot_evidence_select_owner ON public.reflection_snapshot_evidence
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY reflection_feedback_select_owner ON public.reflection_feedback
    FOR SELECT TO authenticated USING (user_id = auth.uid());

REVOKE ALL ON public.entry_analyses, public.entry_signals, public.user_pii_vaults,
    public.processing_jobs, public.reflection_user_state, public.pattern_candidates,
    public.pattern_candidate_evidence, public.reflection_snapshots,
    public.reflection_snapshot_insights, public.reflection_snapshot_evidence,
    public.reflection_feedback
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON SEQUENCE public.entry_analyses_source_version_seq
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT SELECT ON public.reflection_snapshots, public.reflection_snapshot_insights,
    public.reflection_snapshot_evidence, public.reflection_feedback TO authenticated;

CREATE FUNCTION public.enqueue_processing_job_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_source_version text,
    p_run_after timestamptz DEFAULT pg_catalog.now()
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_source_version IS DISTINCT FROM p_entry_id::text
       OR p_run_after IS NULL
       OR NOT EXISTS (
           SELECT 1 FROM public.entries
           WHERE id = p_entry_id AND user_id = p_user_id
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid processing job';
    END IF;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, 'entry_processing', p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

CREATE FUNCTION public.enqueue_processing_job(
    p_user_id uuid,
    p_entry_id uuid,
    p_job_type text,
    p_source_version text,
    p_run_after timestamptz DEFAULT pg_catalog.now()
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_job_type NOT IN ('entry_processing', 'reflection_synthesis')
       OR p_run_after IS NULL
       OR (
           p_job_type = 'entry_processing'
           AND (
               p_entry_id IS NULL
               OR p_source_version IS DISTINCT FROM p_entry_id::text
               OR NOT EXISTS (
                   SELECT 1 FROM public.entries
                   WHERE id = p_entry_id AND user_id = p_user_id
               )
           )
       )
       OR (
           p_job_type = 'reflection_synthesis'
           AND (p_entry_id IS NOT NULL OR p_source_version !~ '^[1-9][0-9]*$')
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, p_job_type, p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

CREATE FUNCTION public.claim_processing_job(p_worker_id text)
RETURNS TABLE (
    job_id uuid,
    user_id uuid,
    entry_id uuid,
    job_type text,
    source_version text,
    claim_token uuid,
    attempts smallint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    claimed public.processing_jobs%ROWTYPE;
    token uuid := gen_random_uuid();
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.length(pg_catalog.btrim(p_worker_id)) NOT BETWEEN 1 AND 100
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT queued.* INTO claimed
    FROM public.processing_jobs AS queued
    WHERE queued.status = 'pending' AND queued.attempts < 3
      AND queued.run_after <= pg_catalog.now()
    ORDER BY queued.run_after, queued.created_at, queued.id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.processing_jobs AS target
    SET status = 'running', attempts = target.attempts + 1, worker_id = p_worker_id,
        claim_token = token, heartbeat_at = pg_catalog.now(),
        last_error_code = NULL, completed_at = NULL
    WHERE target.id = claimed.id
    RETURNING target.* INTO claimed;
    IF claimed.job_type = 'entry_processing' THEN
        UPDATE public.entries AS target_entry
        SET processing_status = 'processing', processing_token = token,
            processing_error_code = NULL, processing_started_at = pg_catalog.now(),
            completed_at = NULL
        WHERE target_entry.id = claimed.entry_id
          AND target_entry.user_id = claimed.user_id;
    END IF;
    RETURN QUERY SELECT claimed.id, claimed.user_id, claimed.entry_id,
        claimed.job_type, claimed.source_version, token, claimed.attempts;
END
$function$;

CREATE FUNCTION public.renew_processing_job(
    p_job_id uuid, p_worker_id text, p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.processing_jobs
    SET heartbeat_at = pg_catalog.now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
      AND claim_token = p_claim_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.complete_processing_job(
    p_job_id uuid, p_worker_id text, p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO item FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF item.status = 'completed' AND item.claim_token = p_claim_token THEN
        RETURN true;
    END IF;
    IF item.status <> 'running' OR item.worker_id IS DISTINCT FROM p_worker_id
       OR item.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RETURN false;
    END IF;
    IF item.job_type = 'entry_processing' AND NOT EXISTS (
        SELECT 1 FROM public.entries
        WHERE id = item.entry_id AND user_id = item.user_id
          AND processing_status = 'completed'
    ) THEN
        RETURN false;
    END IF;
    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = p_job_id;
    RETURN true;
END
$function$;

CREATE FUNCTION public.fail_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_error_code text,
    p_retryable boolean
)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
    terminal boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_error_code !~ '^[A-Z][A-Z0-9_]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO item FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND OR item.status <> 'running'
       OR item.worker_id IS DISTINCT FROM p_worker_id
       OR item.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RETURN 'stale';
    END IF;
    terminal := NOT p_retryable OR item.attempts >= 3;
    IF terminal THEN
        UPDATE public.processing_jobs
        SET status = 'failed', worker_id = NULL, heartbeat_at = NULL,
            completed_at = pg_catalog.now(), last_error_code = p_error_code
        WHERE id = item.id;
        IF item.job_type = 'entry_processing' THEN
            UPDATE public.entries
            SET processing_status = 'failed', processing_token = NULL,
                processing_error_code = 'PROCESSING_FAILED', completed_at = NULL
            WHERE id = item.entry_id AND user_id = item.user_id;
        ELSE
            INSERT INTO public.reflection_user_state (user_id, last_processing_error_code)
            VALUES (item.user_id, p_error_code)
            ON CONFLICT (user_id) DO UPDATE
                SET last_processing_error_code = EXCLUDED.last_processing_error_code;
        END IF;
        RETURN 'failed';
    END IF;
    UPDATE public.processing_jobs
    SET status = 'pending', worker_id = NULL, claim_token = NULL,
        heartbeat_at = NULL, last_error_code = p_error_code,
        run_after = pg_catalog.now() + CASE item.attempts
            WHEN 1 THEN pg_catalog.make_interval(secs => 30)
            ELSE pg_catalog.make_interval(mins => 2)
        END
    WHERE id = item.id;
    IF item.job_type = 'entry_processing' THEN
        UPDATE public.entries
        SET processing_status = 'pending', processing_token = NULL,
            processing_error_code = NULL, processing_started_at = NULL,
            completed_at = NULL
        WHERE id = item.entry_id AND user_id = item.user_id;
    END IF;
    RETURN 'pending';
END
$function$;

CREATE FUNCTION public.recover_stale_processing_jobs(p_stale_before timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item public.processing_jobs%ROWTYPE;
    recovered integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_stale_before IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    FOR item IN
        SELECT * FROM public.processing_jobs
        WHERE status = 'running' AND heartbeat_at < p_stale_before
        ORDER BY heartbeat_at, id
        FOR UPDATE SKIP LOCKED
    LOOP
        IF item.attempts >= 3 THEN
            UPDATE public.processing_jobs
            SET status = 'failed', worker_id = NULL, heartbeat_at = NULL,
                completed_at = pg_catalog.now(), last_error_code = 'WORKER_RETRIES_EXHAUSTED'
            WHERE id = item.id;
            IF item.job_type = 'entry_processing' THEN
                UPDATE public.entries
                SET processing_status = 'failed', processing_token = NULL,
                    processing_error_code = 'PROCESSING_FAILED', completed_at = NULL
                WHERE id = item.entry_id AND user_id = item.user_id;
            ELSE
                INSERT INTO public.reflection_user_state (user_id, last_processing_error_code)
                VALUES (item.user_id, 'WORKER_RETRIES_EXHAUSTED')
                ON CONFLICT (user_id) DO UPDATE SET
                    last_processing_error_code = EXCLUDED.last_processing_error_code;
            END IF;
        ELSE
            UPDATE public.processing_jobs
            SET status = 'pending', worker_id = NULL, claim_token = NULL,
                heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED',
                run_after = pg_catalog.now() + CASE item.attempts
                    WHEN 1 THEN pg_catalog.make_interval(secs => 30)
                    ELSE pg_catalog.make_interval(mins => 2)
                END
            WHERE id = item.id;
            IF item.job_type = 'entry_processing' THEN
                UPDATE public.entries
                SET processing_status = 'pending', processing_token = NULL,
                    processing_error_code = NULL, processing_started_at = NULL,
                    completed_at = NULL
                WHERE id = item.entry_id AND user_id = item.user_id;
            END IF;
        END IF;
        recovered := recovered + 1;
    END LOOP;
    RETURN recovered;
END
$function$;

CREATE FUNCTION public.get_user_pii_vault_for_update(p_user_id uuid)
RETURNS TABLE(mapping_envelope jsonb, mapping_version integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT vault.mapping_envelope, vault.mapping_version
    FROM public.user_pii_vaults AS vault
    WHERE vault.user_id = p_user_id
    FOR UPDATE;
END
$function$;

CREATE FUNCTION public.save_user_pii_vault(
    p_user_id uuid, p_mapping_envelope jsonb, p_expected_version integer
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    next_version integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR public.is_valid_encrypted_envelope_v1(p_mapping_envelope) IS NOT TRUE
       OR p_expected_version < 0
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    IF p_expected_version = 0 THEN
        INSERT INTO public.user_pii_vaults (user_id, mapping_envelope, mapping_version)
        VALUES (p_user_id, p_mapping_envelope, 1)
        ON CONFLICT (user_id) DO NOTHING
        RETURNING mapping_version INTO next_version;
    ELSE
        UPDATE public.user_pii_vaults
        SET mapping_envelope = p_mapping_envelope,
            mapping_version = mapping_version + 1
        WHERE user_id = p_user_id AND mapping_version = p_expected_version
        RETURNING mapping_version INTO next_version;
    END IF;
    IF next_version IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'stale vault version';
    END IF;
    RETURN next_version;
END
$function$;

CREATE FUNCTION public.apply_entry_analysis(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_analysis jsonb,
    p_signals jsonb
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    analysis_id uuid;
    analysis_source_version bigint;
    signal jsonb;
    signal_count integer := 0;
    entry_local_date date;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_analysis) <> 'object'
       OR pg_catalog.jsonb_typeof(p_signals) <> 'array'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO job FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    IF job.job_type = 'entry_processing' AND job.status = 'completed'
       AND job.claim_token = p_claim_token
    THEN
        SELECT source_version INTO analysis_source_version
        FROM public.entry_analyses
        WHERE entry_id = job.entry_id AND user_id = job.user_id;
        IF analysis_source_version IS NOT NULL THEN
            RETURN analysis_source_version;
        END IF;
    END IF;
    IF job.job_type <> 'entry_processing' OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    IF (p_analysis ->> 'eligibility') <> 'accepted'
       AND pg_catalog.jsonb_array_length(p_signals) <> 0
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'ineligible analysis has signals';
    END IF;
    analysis_id := COALESCE((p_analysis ->> 'id')::uuid, gen_random_uuid());
    INSERT INTO public.entry_analyses (
        id, user_id, entry_id, entry_kind, model_eligibility, eligibility,
        deterministic_features, semantic_scores, exclusion_reason_codes,
        ngram_sketch, redacted_text_envelope, offset_map_envelope,
        reflective_word_count, duplicate_cluster_key, model_id, prompt_version
    ) VALUES (
        analysis_id, job.user_id, job.entry_id, p_analysis ->> 'entry_kind',
        p_analysis ->> 'model_eligibility', p_analysis ->> 'eligibility',
        p_analysis -> 'deterministic_features', p_analysis -> 'semantic_scores',
        COALESCE(ARRAY(SELECT pg_catalog.jsonb_array_elements_text(
            COALESCE(p_analysis -> 'exclusion_reason_codes', '[]'::jsonb)
        )), '{}'::text[]),
        COALESCE(ARRAY(SELECT pg_catalog.jsonb_array_elements_text(
            COALESCE(p_analysis -> 'ngram_sketch', '[]'::jsonb)
        )), '{}'::text[]),
        p_analysis -> 'redacted_text_envelope', p_analysis -> 'offset_map_envelope',
        (p_analysis ->> 'reflective_word_count')::integer,
        NULLIF(p_analysis ->> 'duplicate_cluster_key', ''),
        p_analysis ->> 'model_id', p_analysis ->> 'prompt_version'
    ) RETURNING source_version INTO analysis_source_version;
    FOR signal IN SELECT value FROM pg_catalog.jsonb_array_elements(p_signals)
    LOOP
        INSERT INTO public.entry_signals (
            id, user_id, entry_id, analysis_id, signal_type,
            normalized_label_fingerprint, payload_envelope, themes, need_tags,
            loop_role, confidence, source_start, source_end, occurred_on,
            duplicate_cluster_key
        ) VALUES (
            COALESCE((signal ->> 'id')::uuid, gen_random_uuid()),
            job.user_id, job.entry_id, analysis_id, signal ->> 'signal_type',
            signal ->> 'normalized_label_fingerprint', signal -> 'payload_envelope',
            COALESCE(ARRAY(SELECT pg_catalog.jsonb_array_elements_text(
                COALESCE(signal -> 'themes', '[]'::jsonb)
            )), '{}'::text[]),
            COALESCE(ARRAY(SELECT pg_catalog.jsonb_array_elements_text(
                COALESCE(signal -> 'need_tags', '[]'::jsonb)
            )), '{}'::text[]),
            NULLIF(signal ->> 'loop_role', ''), (signal ->> 'confidence')::numeric,
            (signal ->> 'source_start')::integer, (signal ->> 'source_end')::integer,
            (signal ->> 'occurred_on')::date,
            NULLIF(signal ->> 'duplicate_cluster_key', '')
        );
        signal_count := signal_count + 1;
    END LOOP;
    IF (p_analysis ->> 'eligibility') = 'accepted' THEN
        SELECT entry_date INTO entry_local_date
        FROM public.entries WHERE id = job.entry_id AND user_id = job.user_id;
        INSERT INTO public.reflection_user_state (
            user_id, latest_accepted_source_version, new_valid_entries,
            new_accepted_signals, pending_local_dates
        ) VALUES (
            job.user_id, analysis_source_version, 1, signal_count, ARRAY[entry_local_date]
        )
        ON CONFLICT (user_id) DO UPDATE SET
            latest_accepted_source_version = GREATEST(
                public.reflection_user_state.latest_accepted_source_version,
                EXCLUDED.latest_accepted_source_version
            ),
            new_valid_entries = public.reflection_user_state.new_valid_entries + 1,
            new_accepted_signals = public.reflection_user_state.new_accepted_signals + signal_count,
            pending_local_dates = CASE
                WHEN entry_local_date = ANY(public.reflection_user_state.pending_local_dates)
                    THEN public.reflection_user_state.pending_local_dates
                ELSE pg_catalog.array_append(
                    public.reflection_user_state.pending_local_dates, entry_local_date
                )
            END;
    END IF;
    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = job.id;
    RETURN analysis_source_version;
END
$function$;

CREATE FUNCTION public.schedule_reflection_jobs(p_now timestamptz DEFAULT pg_catalog.now())
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    profile record;
    state public.reflection_user_state%ROWTYPE;
    local_date date;
    enqueued integer := 0;
    changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_now IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    FOR profile IN
        SELECT user_id, timezone
        FROM public.user_profiles
        WHERE (p_now AT TIME ZONE timezone)::time >= TIME '18:00:00'
        ORDER BY user_id
    LOOP
        local_date := (p_now AT TIME ZONE profile.timezone)::date;
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('orion-reflection:' || profile.user_id::text, 0)
        );
        SELECT * INTO state FROM public.reflection_user_state
        WHERE user_id = profile.user_id FOR UPDATE;
        IF NOT FOUND OR state.last_schedule_local_date >= local_date THEN
            CONTINUE;
        END IF;
        UPDATE public.reflection_user_state
        SET last_schedule_local_date = local_date
        WHERE user_id = profile.user_id;
        IF (
            state.new_valid_entries >= 3
            OR (
                state.new_valid_entries >= 2
                AND pg_catalog.cardinality(state.pending_local_dates) >= 2
            )
        ) AND state.new_accepted_signals >= 1
        THEN
            INSERT INTO public.processing_jobs (
                user_id, entry_id, job_type, source_version, run_after
            ) VALUES (
                profile.user_id, NULL, 'reflection_synthesis',
                state.latest_accepted_source_version::text, p_now
            ) ON CONFLICT (user_id, job_type, source_version) DO NOTHING;
            GET DIAGNOSTICS changed = ROW_COUNT;
            enqueued := enqueued + changed;
        END IF;
    END LOOP;
    RETURN enqueued;
END
$function$;

CREATE FUNCTION public.apply_reflection_snapshot(
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
    snapshot_id uuid;
    snapshot_source bigint;
    snapshot_version integer;
    item jsonb;
    existing_id uuid;
    inserted_count integer;
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
    SELECT * INTO job FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    IF job.status = 'completed' AND job.claim_token = p_claim_token THEN
        SELECT id INTO snapshot_id FROM public.reflection_snapshots
        WHERE user_id = job.user_id AND source_version = job.source_version::bigint;
        RETURN snapshot_id;
    END IF;
    IF job.job_type <> 'reflection_synthesis' OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    SELECT * INTO state FROM public.reflection_user_state
    WHERE user_id = job.user_id FOR UPDATE;
    snapshot_id := COALESCE((p_snapshot ->> 'id')::uuid, gen_random_uuid());
    snapshot_source := (p_snapshot ->> 'source_version')::bigint;
    snapshot_version := (p_snapshot ->> 'version')::integer;
    IF snapshot_source::text <> job.source_version
       OR state.user_id IS NULL
       OR snapshot_source > state.latest_accepted_source_version
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot source';
    END IF;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_candidates)
    LOOP
        SELECT id INTO existing_id FROM public.pattern_candidates
        WHERE user_id = job.user_id
          AND pattern_type = item ->> 'pattern_type'
          AND canonical_key = item ->> 'canonical_key'
        FOR UPDATE;
        IF existing_id IS NOT NULL AND existing_id IS DISTINCT FROM (item ->> 'id')::uuid THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'candidate identity mismatch';
        END IF;
        INSERT INTO public.pattern_candidates (
            id, user_id, pattern_type, canonical_key, status, score,
            score_components, payload_envelope, first_seen_at, last_seen_at,
            version, rejected_at, rejected_source_version
        ) VALUES (
            (item ->> 'id')::uuid, job.user_id, item ->> 'pattern_type',
            item ->> 'canonical_key', item ->> 'status', (item ->> 'score')::numeric,
            item -> 'score_components', item -> 'payload_envelope',
            (item ->> 'first_seen_at')::timestamptz,
            (item ->> 'last_seen_at')::timestamptz,
            COALESCE((item ->> 'version')::integer, 1),
            (item ->> 'rejected_at')::timestamptz,
            (item ->> 'rejected_source_version')::bigint
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
            rejected_source_version = EXCLUDED.rejected_source_version
        WHERE public.pattern_candidates.user_id = job.user_id;
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_candidates)
    LOOP
        DELETE FROM public.pattern_candidate_evidence
        WHERE candidate_id = (item ->> 'id')::uuid AND user_id = job.user_id;
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_candidate_evidence)
    LOOP
        INSERT INTO public.pattern_candidate_evidence (
            candidate_id, signal_id, user_id, evidence_role, evidence_weight
        ) VALUES (
            (item ->> 'candidate_id')::uuid, (item ->> 'signal_id')::uuid,
            job.user_id, item ->> 'evidence_role', (item ->> 'evidence_weight')::numeric
        );
    END LOOP;
    INSERT INTO public.reflection_snapshots (
        id, user_id, version, source_version, basis_start, basis_end,
        valid_entry_count, excluded_entry_count, distinct_entry_dates,
        reflective_word_count, status
    ) VALUES (
        snapshot_id, job.user_id, snapshot_version, snapshot_source,
        (p_snapshot ->> 'basis_start')::date, (p_snapshot ->> 'basis_end')::date,
        (p_snapshot ->> 'valid_entry_count')::integer,
        (p_snapshot ->> 'excluded_entry_count')::integer,
        (p_snapshot ->> 'distinct_entry_dates')::integer,
        (p_snapshot ->> 'reflective_word_count')::integer,
        COALESCE(p_snapshot ->> 'status', 'available')
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
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_snapshot_evidence)
    LOOP
        INSERT INTO public.reflection_snapshot_evidence (
            insight_id, signal_id, entry_id, user_id, evidence_role, ordinal,
            source_start, source_end
        )
        SELECT (item ->> 'insight_id')::uuid, signal.id, signal.entry_id,
            job.user_id, item ->> 'evidence_role', (item ->> 'ordinal')::smallint,
            signal.source_start, signal.source_end
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
        WHERE signal.id = (item ->> 'signal_id')::uuid
          AND signal.user_id = job.user_id
          AND signal.entry_id = (item ->> 'entry_id')::uuid
          AND signal.source_start = (item ->> 'source_start')::integer
          AND signal.source_end = (item ->> 'source_end')::integer
          AND analysis.eligibility = 'accepted';
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid snapshot evidence';
        END IF;
    END LOOP;
    UPDATE public.reflection_user_state
    SET last_snapshot_source_version = snapshot_source,
        last_successful_snapshot_id = snapshot_id,
        new_valid_entries = (
            SELECT pg_catalog.count(*)::integer FROM public.entry_analyses
            WHERE user_id = job.user_id AND eligibility = 'accepted'
              AND source_version > snapshot_source
        ),
        new_accepted_signals = (
            SELECT pg_catalog.count(*)::integer
            FROM public.entry_signals AS signal
            JOIN public.entry_analyses AS analysis
              ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
            WHERE signal.user_id = job.user_id AND analysis.eligibility = 'accepted'
              AND analysis.source_version > snapshot_source
        ),
        pending_local_dates = COALESCE((
            SELECT pg_catalog.array_agg(DISTINCT entry.entry_date ORDER BY entry.entry_date)
            FROM public.entry_analyses AS analysis
            JOIN public.entries AS entry
              ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
            WHERE analysis.user_id = job.user_id AND analysis.eligibility = 'accepted'
              AND analysis.source_version > snapshot_source
        ), '{}'::date[]),
        last_processing_error_code = NULL
    WHERE user_id = job.user_id;
    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = job.id;
    RETURN snapshot_id;
END
$function$;

CREATE FUNCTION public.put_reflection_feedback_for_owner(
    p_user_id uuid,
    p_snapshot_id uuid,
    p_insight_id uuid,
    p_response text
)
RETURNS TABLE (
    snapshot_id uuid,
    insight_id uuid,
    response text,
    updated_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    insight public.reflection_snapshot_insights%ROWTYPE;
    result public.reflection_feedback%ROWTYPE;
    snapshot_source bigint;
    previous_response text;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_response NOT IN ('resonates', 'partly', 'rejected')
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid feedback';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || p_user_id::text, 0)
    );
    SELECT item.* INTO insight
    FROM public.reflection_snapshot_insights AS item
    WHERE item.id = p_insight_id AND item.user_id = p_user_id
      AND item.snapshot_id = p_snapshot_id AND item.status = 'available'
    FOR UPDATE;
    IF NOT FOUND OR insight.candidate_id IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'reflection insight not found';
    END IF;
    SELECT source_version INTO snapshot_source
    FROM public.reflection_snapshots
    WHERE id = p_snapshot_id AND user_id = p_user_id;
    SELECT feedback.response INTO previous_response
    FROM public.reflection_feedback AS feedback
    WHERE feedback.user_id = p_user_id AND feedback.snapshot_id = p_snapshot_id
      AND feedback.insight_id = p_insight_id;
    INSERT INTO public.reflection_feedback AS feedback (
        user_id, snapshot_id, insight_id, candidate_id, response
    ) VALUES (
        p_user_id, p_snapshot_id, p_insight_id, insight.candidate_id, p_response
    )
    ON CONFLICT ON CONSTRAINT reflection_feedback_user_id_snapshot_id_insight_id_key DO UPDATE
        SET response = EXCLUDED.response, candidate_id = EXCLUDED.candidate_id,
            updated_at = pg_catalog.now()
    RETURNING feedback.* INTO result;
    IF previous_response IS DISTINCT FROM p_response AND p_response = 'partly' THEN
        UPDATE public.pattern_candidates
        SET status = 'weakened', version = version + 1
        WHERE id = insight.candidate_id AND user_id = p_user_id AND status <> 'rejected';
    ELSIF previous_response IS DISTINCT FROM p_response AND p_response = 'rejected' THEN
        UPDATE public.pattern_candidates
        SET status = 'rejected', rejected_at = pg_catalog.now(),
            rejected_source_version = snapshot_source, version = version + 1
        WHERE id = insight.candidate_id AND user_id = p_user_id;
    END IF;
    RETURN QUERY SELECT result.snapshot_id, result.insight_id,
        result.response, result.updated_at;
END
$function$;

CREATE FUNCTION public.delete_entry_with_reflection_for_owner(
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
    latest_source bigint;
    remaining_signals integer;
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
        WHERE user_id = p_user_id AND id = ANY(affected_candidates) AND status <> 'rejected';
    END IF;
    IF accepted IS TRUE THEN
        UPDATE public.reflection_snapshots
        SET status = 'stale'
        WHERE id = (
            SELECT last_successful_snapshot_id FROM public.reflection_user_state
            WHERE user_id = p_user_id
        );
        SELECT COALESCE(pg_catalog.max(source_version), 0) INTO latest_source
        FROM public.entry_analyses
        WHERE user_id = p_user_id AND eligibility = 'accepted';
        SELECT pg_catalog.count(*)::integer INTO remaining_signals
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
        WHERE signal.user_id = p_user_id AND analysis.eligibility = 'accepted';
        IF remaining_signals > 0 THEN
            latest_source := pg_catalog.nextval(
                'public.entry_analyses_source_version_seq'::regclass
            );
        END IF;
        UPDATE public.reflection_user_state
        SET latest_accepted_source_version = latest_source,
            last_snapshot_source_version = LEAST(
                last_snapshot_source_version, latest_source
            ),
            new_valid_entries = (
                SELECT pg_catalog.count(*)::integer FROM public.entry_analyses
                WHERE user_id = p_user_id AND eligibility = 'accepted'
                  AND source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ),
            new_accepted_signals = (
                SELECT pg_catalog.count(*)::integer
                FROM public.entry_signals AS signal
                JOIN public.entry_analyses AS analysis
                  ON analysis.id = signal.analysis_id AND analysis.user_id = signal.user_id
                WHERE signal.user_id = p_user_id AND analysis.eligibility = 'accepted'
                  AND analysis.source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ),
            pending_local_dates = COALESCE((
                SELECT pg_catalog.array_agg(DISTINCT entry.entry_date ORDER BY entry.entry_date)
                FROM public.entry_analyses AS analysis
                JOIN public.entries AS entry
                  ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
                WHERE analysis.user_id = p_user_id AND analysis.eligibility = 'accepted'
                  AND analysis.source_version > LEAST(
                      public.reflection_user_state.last_snapshot_source_version, latest_source
                  )
            ), '{}'::date[])
        WHERE user_id = p_user_id;
        IF remaining_signals > 0 AND latest_source > 0 THEN
            INSERT INTO public.processing_jobs (
                user_id, entry_id, job_type, source_version, run_after
            ) VALUES (
                p_user_id, NULL, 'reflection_synthesis', latest_source::text, pg_catalog.now()
            ) ON CONFLICT (user_id, job_type, source_version) DO NOTHING;
        END IF;
    END IF;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.is_valid_encrypted_envelope_v1(jsonb)
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.is_unit_interval_json_object(jsonb)
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.enqueue_processing_job_for_owner(uuid, uuid, text, timestamptz)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.enqueue_processing_job_for_owner(uuid, uuid, text, timestamptz)
    TO authenticated;
REVOKE ALL ON FUNCTION public.put_reflection_feedback_for_owner(uuid, uuid, uuid, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.put_reflection_feedback_for_owner(uuid, uuid, uuid, text)
    TO authenticated;
REVOKE ALL ON FUNCTION public.delete_entry_with_reflection_for_owner(uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.delete_entry_with_reflection_for_owner(uuid, uuid)
    TO authenticated;

REVOKE ALL ON FUNCTION public.enqueue_processing_job(uuid, uuid, text, text, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.claim_processing_job(text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.renew_processing_job(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_processing_job(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.fail_processing_job(uuid, text, uuid, text, boolean)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.recover_stale_processing_jobs(timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_user_pii_vault_for_update(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.save_user_pii_vault(uuid, jsonb, integer)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_entry_analysis(uuid, text, uuid, jsonb, jsonb)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.schedule_reflection_jobs(timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.enqueue_processing_job(uuid, uuid, text, text, timestamptz)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.claim_processing_job(text) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.renew_processing_job(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_processing_job(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.fail_processing_job(uuid, text, uuid, text, boolean)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.recover_stale_processing_jobs(timestamptz)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_user_pii_vault_for_update(uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.save_user_pii_vault(uuid, jsonb, integer) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_entry_analysis(uuid, text, uuid, jsonb, jsonb)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs(timestamptz) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_reflection_snapshot(
    uuid, text, uuid, jsonb, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
