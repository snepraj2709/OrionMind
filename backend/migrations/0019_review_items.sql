-- Owner-scoped encrypted Review-item persistence.
-- Producers and feedback functions are added by later migrations.

CREATE TABLE public.review_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid,
    entry_signal_id uuid,
    pattern_candidate_id uuid,
    scope text NOT NULL,
    item_type text NOT NULL,
    category text NOT NULL,
    statement_envelope jsonb NOT NULL,
    source_quote_envelope jsonb,
    source_entry_ids uuid[] NOT NULL,
    source_dates date[] NOT NULL,
    inference_level text NOT NULL,
    model_confidence numeric(6,5) NOT NULL,
    review_status text NOT NULL DEFAULT 'pending',
    user_feedback jsonb,
    corrected_statement_envelope jsonb,
    feedback_note_envelope jsonb,
    evidence_weight numeric(2,1) NOT NULL DEFAULT 1.0,
    reflection_eligible boolean NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (id, user_id),
    CONSTRAINT review_items_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT review_items_entry_signal_owner_fk
        FOREIGN KEY (entry_signal_id, user_id)
        REFERENCES public.entry_signals(id, user_id) ON DELETE CASCADE,
    CONSTRAINT review_items_pattern_candidate_owner_fk
        FOREIGN KEY (pattern_candidate_id, user_id)
        REFERENCES public.pattern_candidates(id, user_id) ON DELETE CASCADE,
    CONSTRAINT review_items_scope_check CHECK (
        scope IN ('entry_insight', 'pattern')
    ),
    CONSTRAINT review_items_type_category_check CHECK (
        (item_type IN ('energy_gain', 'energy_loss') AND category = 'energy')
        OR (
            item_type IN ('self_knowledge', 'realization', 'explicit_preference')
            AND category = 'self_knowledge'
        )
        OR (
            item_type IN (
                'need', 'belief', 'avoidance', 'protective_strategy',
                'conflict', 'causal_relationship'
            )
            AND category = 'needs_beliefs'
        )
        OR (item_type = 'hidden_driver' AND category = 'hidden_driver')
        OR (item_type = 'recurring_loop' AND category = 'recurring_loop')
        OR (item_type = 'inner_tension' AND category = 'inner_tension')
    ),
    CONSTRAINT review_items_scope_source_check CHECK (
        (
            scope = 'entry_insight'
            AND entry_id IS NOT NULL
            AND entry_signal_id IS NOT NULL
            AND pattern_candidate_id IS NULL
            AND item_type IN (
                'energy_gain', 'energy_loss', 'self_knowledge', 'realization',
                'explicit_preference', 'need', 'belief', 'avoidance',
                'protective_strategy', 'conflict', 'causal_relationship'
            )
            AND inference_level IN ('direct', 'inferred')
            AND source_entry_ids = ARRAY[entry_id]
            AND pg_catalog.cardinality(source_dates) = 1
        )
        OR (
            scope = 'pattern'
            AND entry_id IS NULL
            AND entry_signal_id IS NULL
            AND pattern_candidate_id IS NOT NULL
            AND item_type IN ('hidden_driver', 'recurring_loop', 'inner_tension')
            AND inference_level = 'synthesized'
            AND source_quote_envelope IS NULL
        )
    ),
    CONSTRAINT review_items_single_source_check CHECK (
        pg_catalog.num_nonnulls(entry_signal_id, pattern_candidate_id) = 1
    ),
    CONSTRAINT review_items_statement_envelope_check CHECK (
        public.is_valid_encrypted_envelope_v1(statement_envelope)
    ),
    CONSTRAINT review_items_optional_envelopes_check CHECK (
        (
            source_quote_envelope IS NULL
            OR public.is_valid_encrypted_envelope_v1(source_quote_envelope)
        )
        AND (
            corrected_statement_envelope IS NULL
            OR public.is_valid_encrypted_envelope_v1(corrected_statement_envelope)
        )
        AND (
            feedback_note_envelope IS NULL
            OR public.is_valid_encrypted_envelope_v1(feedback_note_envelope)
        )
    ),
    CONSTRAINT review_items_sources_check CHECK (
        pg_catalog.cardinality(source_entry_ids) BETWEEN 1 AND 100
        AND pg_catalog.array_position(source_entry_ids, NULL) IS NULL
        AND pg_catalog.cardinality(source_dates) BETWEEN 1 AND 100
        AND pg_catalog.array_position(source_dates, NULL) IS NULL
    ),
    CONSTRAINT review_items_inference_check CHECK (
        inference_level IN ('direct', 'inferred', 'synthesized')
    ),
    CONSTRAINT review_items_confidence_check CHECK (
        model_confidence BETWEEN 0 AND 1
    ),
    CONSTRAINT review_items_status_check CHECK (
        review_status IN ('pending', 'confirmed', 'partially_confirmed', 'rejected')
    ),
    CONSTRAINT review_items_feedback_shape_check CHECK (
        user_feedback IS NULL
        OR (
            pg_catalog.jsonb_typeof(user_feedback) = 'object'
            AND user_feedback ?& ARRAY['verdict', 'updated_at']
            AND user_feedback - ARRAY['verdict', 'updated_at'] = '{}'::jsonb
            AND pg_catalog.jsonb_typeof(user_feedback -> 'verdict') = 'string'
            AND pg_catalog.jsonb_typeof(user_feedback -> 'updated_at') = 'string'
            AND (
                (
                    scope = 'entry_insight'
                    AND user_feedback ->> 'verdict'
                        IN ('accurate', 'partly_accurate', 'not_accurate')
                )
                OR (
                    scope = 'pattern'
                    AND user_feedback ->> 'verdict'
                        IN ('resonates', 'partly_true', 'not_true')
                )
            )
        )
    ),
    CONSTRAINT review_items_feedback_status_weight_check CHECK (
        (
            review_status = 'pending'
            AND evidence_weight = 1.0
            AND user_feedback IS NULL
            AND corrected_statement_envelope IS NULL
            AND feedback_note_envelope IS NULL
        )
        OR (
            review_status = 'confirmed'
            AND evidence_weight = 1.0
            AND user_feedback IS NOT NULL
        )
        OR (
            review_status = 'partially_confirmed'
            AND evidence_weight = 0.5
            AND user_feedback IS NOT NULL
        )
        OR (
            review_status = 'rejected'
            AND evidence_weight = 0.0
            AND user_feedback IS NOT NULL
        )
    ),
    CONSTRAINT review_items_feedback_verdict_weight_check CHECK (
        user_feedback IS NULL
        OR (
            user_feedback ->> 'verdict' IN ('accurate', 'resonates')
            AND review_status = 'confirmed'
            AND evidence_weight = 1.0
        )
        OR (
            user_feedback ->> 'verdict' IN ('partly_accurate', 'partly_true')
            AND review_status = 'partially_confirmed'
            AND evidence_weight = 0.5
        )
        OR (
            user_feedback ->> 'verdict' IN ('not_accurate', 'not_true')
            AND review_status = 'rejected'
            AND evidence_weight = 0.0
        )
    ),
    CONSTRAINT review_items_metadata_check CHECK (
        pg_catalog.jsonb_typeof(metadata) = 'object'
        AND pg_catalog.pg_column_size(metadata) <= 16384
    )
);

CREATE INDEX review_items_owner_list_idx
    ON public.review_items (
        user_id, scope, category, review_status, created_at DESC, id DESC
    );
CREATE INDEX review_items_owner_status_updated_idx
    ON public.review_items (user_id, review_status, updated_at DESC);
CREATE UNIQUE INDEX review_items_entry_signal_unique_idx
    ON public.review_items (entry_signal_id)
    WHERE entry_signal_id IS NOT NULL;
CREATE UNIQUE INDEX review_items_pattern_candidate_unique_idx
    ON public.review_items (pattern_candidate_id)
    WHERE pattern_candidate_id IS NOT NULL;

CREATE TRIGGER review_items_set_updated_at
BEFORE UPDATE ON public.review_items
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.review_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review_items FORCE ROW LEVEL SECURITY;

CREATE POLICY review_items_select_owner ON public.review_items
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY review_items_insert_worker ON public.review_items
    FOR INSERT TO orion_worker WITH CHECK (
        pg_catalog.current_setting('role', true) = 'orion_worker'
    );

REVOKE ALL ON public.review_items
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT SELECT ON public.review_items TO authenticated;
GRANT INSERT ON public.review_items TO orion_worker;
GRANT EXECUTE ON FUNCTION public.is_valid_encrypted_envelope_v1(jsonb)
    TO orion_worker;

COMMENT ON TABLE public.review_items IS
    'Encrypted owner-scoped review evidence; sensitive text is never stored in plaintext.';
COMMENT ON COLUMN public.review_items.statement_envelope IS
    'Encrypted JSON string using purpose review_item_statement.';
COMMENT ON COLUMN public.review_items.source_quote_envelope IS
    'Encrypted exact validated quote using purpose review_item_source_quote.';
COMMENT ON COLUMN public.review_items.corrected_statement_envelope IS
    'Encrypted user correction using purpose review_item_corrected_statement.';
COMMENT ON COLUMN public.review_items.feedback_note_envelope IS
    'Encrypted user note using purpose review_item_feedback_note.';
