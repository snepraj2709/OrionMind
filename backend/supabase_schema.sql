-- Orion profile/entry fresh-install schema.
-- Supabase owns auth.users, auth.uid(), and the authenticated/anon/service_role roles.

DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'orion_app') THEN
        CREATE ROLE orion_app NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'orion_worker') THEN
        CREATE ROLE orion_worker NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$roles$;

GRANT authenticated TO orion_app;

CREATE FUNCTION public.is_valid_entry_envelope_v2(envelope jsonb)
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
       OR NOT envelope ?& ARRAY['version', 'algorithm', 'key_id', 'kdf', 'salt', 'nonce', 'ciphertext', 'tag']
       OR pg_catalog.jsonb_typeof(envelope -> 'version') <> 'number'
       OR pg_catalog.jsonb_typeof(envelope -> 'algorithm') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'key_id') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'kdf') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'salt') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'nonce') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'ciphertext') <> 'string'
       OR pg_catalog.jsonb_typeof(envelope -> 'tag') <> 'string'
       OR envelope ->> 'version' <> '2'
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

CREATE TABLE public.theme_configs (
    id uuid PRIMARY KEY,
    config_key text NOT NULL UNIQUE,
    name text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    CONSTRAINT theme_configs_key_check CHECK (config_key ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT theme_configs_name_check CHECK (pg_catalog.length(pg_catalog.btrim(name)) BETWEEN 1 AND 100)
);

CREATE TABLE public.themes (
    id uuid PRIMARY KEY,
    theme_config_id uuid NOT NULL REFERENCES public.theme_configs(id) ON DELETE RESTRICT,
    theme_key text NOT NULL,
    name text NOT NULL,
    color_hex text NOT NULL,
    sort_order smallint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (theme_config_id, theme_key),
    UNIQUE (theme_config_id, name),
    UNIQUE (theme_config_id, sort_order),
    UNIQUE (id, theme_config_id),
    CONSTRAINT themes_key_check CHECK (theme_key ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT themes_name_check CHECK (pg_catalog.length(pg_catalog.btrim(name)) BETWEEN 1 AND 100),
    CONSTRAINT themes_color_check CHECK (color_hex ~ '^#[0-9A-F]{6}$'),
    CONSTRAINT themes_sort_order_check CHECK (sort_order BETWEEN 1 AND 8)
);

INSERT INTO public.theme_configs (id, config_key, name)
VALUES ('00000000-0000-0000-0000-000000000801', 'default_8', 'Default 8 Theme Buckets');

INSERT INTO public.themes (id, theme_config_id, theme_key, name, color_hex, sort_order)
VALUES
    ('00000000-0000-0000-0000-000000000811', '00000000-0000-0000-0000-000000000801', 'career', 'Career', '#2563EB', 1),
    ('00000000-0000-0000-0000-000000000812', '00000000-0000-0000-0000-000000000801', 'money', 'Money', '#D97706', 2),
    ('00000000-0000-0000-0000-000000000813', '00000000-0000-0000-0000-000000000801', 'health', 'Health', '#16A34A', 3),
    ('00000000-0000-0000-0000-000000000814', '00000000-0000-0000-0000-000000000801', 'love_life', 'Love Life', '#DB2777', 4),
    ('00000000-0000-0000-0000-000000000815', '00000000-0000-0000-0000-000000000801', 'family_friends', 'Family & Friends', '#0F766E', 5),
    ('00000000-0000-0000-0000-000000000816', '00000000-0000-0000-0000-000000000801', 'personal_growth', 'Personal Growth', '#7C3AED', 6),
    ('00000000-0000-0000-0000-000000000817', '00000000-0000-0000-0000-000000000801', 'fun_recreation', 'Fun & Recreation', '#EA580C', 7),
    ('00000000-0000-0000-0000-000000000818', '00000000-0000-0000-0000-000000000801', 'home_lifestyle', 'Home & Lifestyle', '#4B5563', 8);

CREATE TABLE public.user_profiles (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name text NOT NULL DEFAULT '',
    timezone text NOT NULL DEFAULT 'UTC',
    voice_request_timestamps timestamptz[] NOT NULL DEFAULT '{}'::timestamptz[],
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    CONSTRAINT user_profiles_display_name_check CHECK (
        display_name = pg_catalog.btrim(display_name)
        AND pg_catalog.length(display_name) <= 100
    ),
    CONSTRAINT user_profiles_voice_window_check CHECK (
        pg_catalog.cardinality(voice_request_timestamps) <= 10
    )
);

CREATE TABLE public.entry_drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    content_envelope jsonb,
    fingerprint_key_id text NOT NULL,
    content_fingerprint text NOT NULL,
    status text NOT NULL DEFAULT 'active',
    submitted_entry_id uuid,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    submitted_at timestamptz,
    UNIQUE (id, user_id),
    CONSTRAINT entry_drafts_status_check CHECK (status IN ('active', 'submitted')),
    CONSTRAINT entry_drafts_fingerprint_check CHECK (
        pg_catalog.length(fingerprint_key_id) BETWEEN 1 AND 100
        AND content_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT entry_drafts_lifecycle_check CHECK (
        (status = 'active' AND public.is_valid_entry_envelope_v2(content_envelope) AND submitted_entry_id IS NULL AND submitted_at IS NULL)
        OR (status = 'submitted' AND content_envelope IS NULL AND submitted_entry_id IS NOT NULL AND submitted_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX entry_drafts_one_active_per_owner_idx
    ON public.entry_drafts (user_id) WHERE status = 'active';
CREATE INDEX entry_drafts_submitted_replay_idx
    ON public.entry_drafts (user_id, submitted_at DESC, id DESC) WHERE status = 'submitted';
CREATE INDEX entry_drafts_envelope_key_idx
    ON public.entry_drafts ((content_envelope ->> 'key_id')) WHERE content_envelope IS NOT NULL;

CREATE TABLE public.entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    content_envelope jsonb NOT NULL CONSTRAINT entries_envelope_check
        CHECK (public.is_valid_entry_envelope_v2(content_envelope)),
    input_type text NOT NULL,
    entry_date date NOT NULL,
    original_theme_config_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000801'
        REFERENCES public.theme_configs(id) ON DELETE RESTRICT,
    processing_status text NOT NULL DEFAULT 'pending',
    processing_token uuid,
    processing_error_code text,
    idempotency_key text,
    source_draft_id uuid,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    processing_started_at timestamptz,
    completed_at timestamptz,
    UNIQUE (id, user_id),
    CONSTRAINT entries_input_type_check CHECK (input_type IN ('text', 'audio')),
    CONSTRAINT entries_idempotency_check CHECK (
        idempotency_key IS NULL
        OR (
            pg_catalog.length(idempotency_key) BETWEEN 1 AND 128
            AND idempotency_key = pg_catalog.btrim(idempotency_key)
        )
    ),
    CONSTRAINT entries_processing_check CHECK (
        (processing_status = 'pending' AND processing_token IS NULL AND processing_error_code IS NULL AND completed_at IS NULL)
        OR (processing_status = 'processing' AND processing_token IS NOT NULL AND processing_error_code IS NULL AND processing_started_at IS NOT NULL AND completed_at IS NULL)
        OR (processing_status = 'completed' AND processing_token IS NULL AND processing_error_code IS NULL AND completed_at IS NOT NULL)
        OR (processing_status = 'failed' AND processing_token IS NULL AND processing_error_code IS NOT NULL AND completed_at IS NULL)
    ),
    CONSTRAINT entries_error_code_check CHECK (
        processing_error_code IS NULL OR processing_error_code ~ '^[A-Z][A-Z0-9_]*$'
    ),
    CONSTRAINT entries_source_draft_owner_fk FOREIGN KEY (source_draft_id, user_id)
        REFERENCES public.entry_drafts(id, user_id) ON DELETE RESTRICT
);

ALTER TABLE public.entry_drafts
    ADD CONSTRAINT entry_drafts_submitted_entry_owner_fk
    FOREIGN KEY (submitted_entry_id, user_id)
    REFERENCES public.entries(id, user_id) ON DELETE CASCADE;

CREATE UNIQUE INDEX entries_owner_idempotency_idx
    ON public.entries (user_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE UNIQUE INDEX entries_source_draft_idx
    ON public.entries (source_draft_id) WHERE source_draft_id IS NOT NULL;
CREATE INDEX entries_history_idx
    ON public.entries (user_id, entry_date DESC, created_at DESC, id DESC);
CREATE INDEX entries_owner_processing_idx
    ON public.entries (user_id, processing_status, updated_at, id);
CREATE INDEX entries_stale_unfinished_idx
    ON public.entries (updated_at, id) WHERE processing_status IN ('pending', 'processing');
CREATE INDEX entries_config_idx ON public.entries (original_theme_config_id, id);
CREATE INDEX entries_envelope_key_idx ON public.entries ((content_envelope ->> 'key_id'));

CREATE TABLE public.entry_classifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    theme_config_id uuid NOT NULL REFERENCES public.theme_configs(id) ON DELETE RESTRICT,
    source text NOT NULL DEFAULT 'initial',
    mode text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (id, user_id),
    UNIQUE (id, user_id, theme_config_id),
    UNIQUE (entry_id, theme_config_id),
    CONSTRAINT entry_classifications_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT entry_classifications_source_check CHECK (source IN ('initial', 'backfill')),
    CONSTRAINT entry_classifications_mode_check CHECK (mode IS NULL OR mode IN ('dominant', 'balanced'))
);

CREATE INDEX entry_classifications_owner_entry_idx
    ON public.entry_classifications (user_id, entry_id, created_at, id);
CREATE INDEX entry_classifications_config_idx
    ON public.entry_classifications (theme_config_id, entry_id);

CREATE TABLE public.entry_themes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    classification_id uuid NOT NULL,
    theme_config_id uuid NOT NULL,
    theme_id uuid NOT NULL,
    tier text NOT NULL,
    score numeric(6,5) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    CONSTRAINT entry_themes_classification_owner_fk
        FOREIGN KEY (classification_id, user_id, theme_config_id)
        REFERENCES public.entry_classifications(id, user_id, theme_config_id) ON DELETE CASCADE,
    CONSTRAINT entry_themes_theme_config_fk FOREIGN KEY (theme_id, theme_config_id)
        REFERENCES public.themes(id, theme_config_id) ON DELETE RESTRICT,
    CONSTRAINT entry_themes_tier_check CHECK (tier IN ('primary', 'secondary', 'tertiary')),
    CONSTRAINT entry_themes_score_check CHECK (score > 0 AND score <= 1),
    UNIQUE (classification_id, tier),
    UNIQUE (classification_id, theme_id)
);

CREATE INDEX entry_themes_owner_classification_idx
    ON public.entry_themes (user_id, classification_id, tier);

CREATE TABLE public.ideas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    content text NOT NULL,
    status text NOT NULL DEFAULT 'pending_approval',
    decision_source text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    decided_at timestamptz,
    CONSTRAINT ideas_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT ideas_content_check CHECK (
        content = pg_catalog.btrim(content) AND pg_catalog.length(content) BETWEEN 1 AND 4000
    ),
    CONSTRAINT ideas_status_check CHECK (status IN ('pending_approval', 'approved', 'rejected')),
    CONSTRAINT ideas_decision_check CHECK (
        (status = 'pending_approval' AND decision_source IS NULL AND decided_at IS NULL)
        OR (status IN ('approved', 'rejected') AND decision_source IN ('user', 'past_import_auto') AND decided_at IS NOT NULL)
    )
);

CREATE TABLE public.extracted_memories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    content text NOT NULL,
    status text NOT NULL DEFAULT 'pending_approval',
    decision_source text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    decided_at timestamptz,
    CONSTRAINT extracted_memories_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT extracted_memories_content_check CHECK (
        content = pg_catalog.btrim(content) AND pg_catalog.length(content) BETWEEN 1 AND 4000
    ),
    CONSTRAINT extracted_memories_status_check CHECK (status IN ('pending_approval', 'approved', 'rejected')),
    CONSTRAINT extracted_memories_decision_check CHECK (
        (status = 'pending_approval' AND decision_source IS NULL AND decided_at IS NULL)
        OR (status IN ('approved', 'rejected') AND decision_source IN ('user', 'past_import_auto') AND decided_at IS NOT NULL)
    )
);

CREATE TABLE public.reflections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    reflection_type text NOT NULL,
    activity text NOT NULL,
    confidence_score numeric(6,5) NOT NULL,
    status text NOT NULL DEFAULT 'pending_approval',
    decision_source text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    decided_at timestamptz,
    CONSTRAINT reflections_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflections_type_check CHECK (
        reflection_type IN ('filled_energy', 'drained_energy', 'learned_about_self')
    ),
    CONSTRAINT reflections_activity_check CHECK (
        activity = pg_catalog.btrim(activity) AND pg_catalog.length(activity) BETWEEN 1 AND 1000
    ),
    CONSTRAINT reflections_confidence_check CHECK (confidence_score BETWEEN 0 AND 1),
    CONSTRAINT reflections_status_check CHECK (status IN ('pending_approval', 'approved', 'rejected')),
    CONSTRAINT reflections_decision_check CHECK (
        (status = 'pending_approval' AND decision_source IS NULL AND decided_at IS NULL)
        OR (status IN ('approved', 'rejected') AND decision_source IN ('user', 'past_import_auto') AND decided_at IS NOT NULL)
    ),
    UNIQUE (entry_id, reflection_type)
);

CREATE INDEX ideas_owner_entry_idx ON public.ideas (user_id, entry_id, created_at, id);
CREATE INDEX ideas_owner_status_idx ON public.ideas (user_id, status, created_at, id);
CREATE INDEX extracted_memories_owner_entry_idx
    ON public.extracted_memories (user_id, entry_id, created_at, id);
CREATE INDEX extracted_memories_owner_status_idx
    ON public.extracted_memories (user_id, status, created_at, id);
CREATE INDEX reflections_owner_entry_idx
    ON public.reflections (user_id, entry_id, created_at, id);
CREATE INDEX reflections_owner_status_idx
    ON public.reflections (user_id, status, created_at, id);

CREATE TABLE public.past_entry_imports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    entry_id uuid NOT NULL,
    fingerprint_key_id text NOT NULL,
    request_fingerprint text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts smallint NOT NULL DEFAULT 0,
    worker_id text,
    processing_token uuid,
    heartbeat_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    completed_at timestamptz,
    CONSTRAINT past_entry_imports_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE,
    CONSTRAINT past_entry_imports_fingerprint_check CHECK (
        pg_catalog.length(fingerprint_key_id) BETWEEN 1 AND 100
        AND request_fingerprint ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT past_entry_imports_status_check CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT past_entry_imports_attempts_check CHECK (attempts BETWEEN 0 AND 3),
    CONSTRAINT past_entry_imports_error_check CHECK (
        last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]*$'
    ),
    CONSTRAINT past_entry_imports_lifecycle_check CHECK (
        (status = 'pending' AND worker_id IS NULL AND processing_token IS NULL AND heartbeat_at IS NULL AND completed_at IS NULL)
        OR (status = 'running' AND worker_id IS NOT NULL AND processing_token IS NOT NULL AND heartbeat_at IS NOT NULL AND completed_at IS NULL)
        OR (status IN ('completed', 'failed') AND worker_id IS NULL AND processing_token IS NULL AND heartbeat_at IS NULL AND completed_at IS NOT NULL)
    ),
    UNIQUE (entry_id),
    UNIQUE (user_id, fingerprint_key_id, request_fingerprint)
);

CREATE INDEX past_entry_imports_claim_idx
    ON public.past_entry_imports (created_at, id) WHERE status = 'pending';
CREATE INDEX past_entry_imports_stale_idx
    ON public.past_entry_imports (heartbeat_at, id) WHERE status = 'running';
CREATE INDEX past_entry_imports_owner_status_idx
    ON public.past_entry_imports (user_id, status, created_at, id);

CREATE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $function$
BEGIN
    NEW.updated_at := pg_catalog.now();
    RETURN NEW;
END
$function$;

CREATE FUNCTION public.validate_profile_timezone()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $function$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name = NEW.timezone
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'unsupported timezone';
    END IF;
    RETURN NEW;
END
$function$;

CREATE FUNCTION public.bootstrap_user_profile()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    INSERT INTO public.user_profiles (user_id, display_name, timezone)
    VALUES (
        NEW.id,
        pg_catalog.left(pg_catalog.btrim(COALESCE(NEW.raw_user_meta_data ->> 'display_name', '')), 100),
        'UTC'
    )
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END
$function$;

CREATE TRIGGER user_profiles_validate_timezone
BEFORE INSERT OR UPDATE OF timezone ON public.user_profiles
FOR EACH ROW EXECUTE FUNCTION public.validate_profile_timezone();

CREATE TRIGGER user_profiles_set_updated_at
BEFORE UPDATE ON public.user_profiles
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER entry_drafts_set_updated_at
BEFORE UPDATE ON public.entry_drafts
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER entries_set_updated_at
BEFORE UPDATE ON public.entries
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER past_entry_imports_set_updated_at
BEFORE UPDATE ON public.past_entry_imports
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

INSERT INTO public.user_profiles (user_id)
SELECT id FROM auth.users
ON CONFLICT (user_id) DO NOTHING;

CREATE TRIGGER auth_user_profile_bootstrap
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.bootstrap_user_profile();

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE public.entry_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entry_drafts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entries FORCE ROW LEVEL SECURITY;
ALTER TABLE public.entry_classifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entry_classifications FORCE ROW LEVEL SECURITY;
ALTER TABLE public.entry_themes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.entry_themes FORCE ROW LEVEL SECURITY;
ALTER TABLE public.ideas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ideas FORCE ROW LEVEL SECURITY;
ALTER TABLE public.extracted_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.extracted_memories FORCE ROW LEVEL SECURITY;
ALTER TABLE public.reflections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflections FORCE ROW LEVEL SECURITY;
ALTER TABLE public.past_entry_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.past_entry_imports FORCE ROW LEVEL SECURITY;

CREATE POLICY user_profiles_select_owner ON public.user_profiles
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY user_profiles_update_owner ON public.user_profiles
    FOR UPDATE TO authenticated USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY entry_drafts_select_active_owner ON public.entry_drafts
    FOR SELECT TO authenticated USING (user_id = auth.uid() AND status = 'active');
CREATE POLICY entry_drafts_insert_active_owner ON public.entry_drafts
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid() AND status = 'active');
CREATE POLICY entry_drafts_update_active_owner ON public.entry_drafts
    FOR UPDATE TO authenticated USING (user_id = auth.uid() AND status = 'active')
    WITH CHECK (user_id = auth.uid() AND status = 'active');
CREATE POLICY entry_drafts_delete_active_owner ON public.entry_drafts
    FOR DELETE TO authenticated USING (user_id = auth.uid() AND status = 'active');

CREATE POLICY entries_select_owner ON public.entries
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY entries_insert_owner ON public.entries
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
CREATE POLICY entry_classifications_select_owner ON public.entry_classifications
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY entry_themes_select_owner ON public.entry_themes
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY ideas_select_owner ON public.ideas
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY extracted_memories_select_owner ON public.extracted_memories
    FOR SELECT TO authenticated USING (user_id = auth.uid());
CREATE POLICY reflections_select_owner ON public.reflections
    FOR SELECT TO authenticated USING (user_id = auth.uid());

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, anon;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon;

GRANT USAGE ON SCHEMA public TO authenticated, orion_worker;
GRANT SELECT ON public.theme_configs, public.themes TO authenticated;
GRANT SELECT, UPDATE ON public.user_profiles TO authenticated;
GRANT SELECT, INSERT ON public.entries TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.entry_drafts TO authenticated;
GRANT SELECT ON public.entry_classifications, public.entry_themes, public.ideas,
    public.extracted_memories, public.reflections TO authenticated;
REVOKE ALL ON FUNCTION public.bootstrap_user_profile() FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.is_valid_entry_envelope_v2(jsonb) FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.is_valid_entry_envelope_v2(jsonb) TO authenticated;
REVOKE ALL ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.validate_profile_timezone() FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

CREATE FUNCTION public.mark_entry_processing_failed_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_processing_token uuid,
    p_error_code text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_error_code !~ '^[A-Z][A-Z0-9_]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entries
    SET processing_status = 'failed',
        processing_token = NULL,
        processing_error_code = p_error_code,
        completed_at = NULL
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.claim_failed_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    token uuid := gen_random_uuid();
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entries
    SET processing_status = 'processing',
        processing_token = token,
        processing_error_code = NULL,
        processing_started_at = pg_catalog.now(),
        completed_at = NULL
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'failed';
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;
    RETURN token;
END
$function$;

CREATE FUNCTION public.apply_entry_extraction_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_processing_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb,
    p_past_import boolean DEFAULT false
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    theme_count integer;
    classification_id uuid;
    item jsonb;
    item_index integer;
    selected_theme_id uuid;
    expected_tier text;
    selected_score numeric(6,5);
    candidate_status text := 'pending_approval';
    candidate_source text := NULL;
    candidate_decided_at timestamptz := NULL;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_past_import
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
       OR pg_catalog.jsonb_array_length(p_ideas) > 10
       OR pg_catalog.jsonb_array_length(p_memories) > 10
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid extraction payload';
    END IF;

    PERFORM 1
    FROM public.entries
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND original_theme_config_id = p_theme_config_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    IF EXISTS (SELECT 1 FROM public.entry_classifications WHERE entry_id = p_entry_id) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
    END IF;

    theme_count := pg_catalog.jsonb_array_length(p_themes);
    IF theme_count > 3
       OR (theme_count = 0 AND p_mode IS NOT NULL)
       OR (theme_count = 1 AND p_mode IS DISTINCT FROM 'dominant')
       OR (theme_count >= 2 AND p_mode NOT IN ('dominant', 'balanced'))
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid classification shape';
    END IF;

    INSERT INTO public.entry_classifications (user_id, entry_id, theme_config_id, source, mode)
    VALUES (p_user_id, p_entry_id, p_theme_config_id, 'initial', p_mode)
    RETURNING id INTO classification_id;

    item_index := 0;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_themes)
    LOOP
        item_index := item_index + 1;
        expected_tier := (ARRAY['primary', 'secondary', 'tertiary'])[item_index];
        IF item ->> 'tier' IS DISTINCT FROM expected_tier
           OR item ->> 'key' IS NULL
        THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid theme assignment';
        END IF;
        SELECT id INTO selected_theme_id
        FROM public.themes
        WHERE theme_config_id = p_theme_config_id AND theme_key = item ->> 'key';
        IF selected_theme_id IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'unknown theme';
        END IF;
        selected_score := CASE
            WHEN theme_count = 1 THEN 1.00000
            WHEN theme_count = 2 AND p_mode = 'dominant' AND item_index = 1 THEN 0.62650
            WHEN theme_count = 2 AND p_mode = 'dominant' THEN 0.37350
            WHEN theme_count = 2 AND p_mode = 'balanced' AND item_index = 1 THEN 0.53330
            WHEN theme_count = 2 AND p_mode = 'balanced' THEN 0.46670
            WHEN theme_count = 3 AND p_mode = 'dominant' AND item_index = 1 THEN 0.52000
            WHEN theme_count = 3 AND p_mode = 'dominant' AND item_index = 2 THEN 0.31000
            WHEN theme_count = 3 AND p_mode = 'dominant' THEN 0.17000
            WHEN theme_count = 3 AND p_mode = 'balanced' AND item_index = 1 THEN 0.40000
            WHEN theme_count = 3 AND p_mode = 'balanced' AND item_index = 2 THEN 0.35000
            ELSE 0.25000
        END;
        INSERT INTO public.entry_themes (
            user_id, classification_id, theme_config_id, theme_id, tier, score
        ) VALUES (
            p_user_id, classification_id, p_theme_config_id, selected_theme_id,
            expected_tier, selected_score
        );
    END LOOP;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_ideas)
    LOOP
        INSERT INTO public.ideas (
            user_id, entry_id, content, status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'content', candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_memories)
    LOOP
        INSERT INTO public.extracted_memories (
            user_id, entry_id, content, status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'content', candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;
    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_reflections)
    LOOP
        INSERT INTO public.reflections (
            user_id, entry_id, reflection_type, activity, confidence_score,
            status, decision_source, decided_at
        ) VALUES (
            p_user_id, p_entry_id, item ->> 'reflection_type', item ->> 'activity',
            (item ->> 'confidence_score')::numeric, candidate_status,
            candidate_source, candidate_decided_at
        );
    END LOOP;

    UPDATE public.entries
    SET processing_status = 'completed',
        processing_token = NULL,
        processing_error_code = NULL,
        completed_at = pg_catalog.now()
    WHERE id = p_entry_id
      AND user_id = p_user_id
      AND processing_status = 'processing'
      AND processing_token = p_processing_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.mark_entry_processing_failed_for_owner(uuid, uuid, uuid, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.claim_failed_entry_for_owner(uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.apply_entry_extraction_for_owner(
    uuid, uuid, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, boolean
) FROM PUBLIC, anon, orion_app, orion_worker;

GRANT EXECUTE ON FUNCTION public.mark_entry_processing_failed_for_owner(uuid, uuid, uuid, text)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.claim_failed_entry_for_owner(uuid, uuid)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.apply_entry_extraction_for_owner(
    uuid, uuid, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, boolean
) TO authenticated;

CREATE FUNCTION public.save_entry_draft_for_owner(
    p_user_id uuid,
    p_draft_id uuid,
    p_content_envelope jsonb,
    p_fingerprint_key_id text,
    p_content_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    active_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_fingerprint_key_id IS NULL
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid draft request';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    SELECT id INTO active_id
    FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active'
    FOR UPDATE;
    IF active_id IS NULL THEN
        INSERT INTO public.entry_drafts (
            id, user_id, content_envelope, fingerprint_key_id, content_fingerprint, status
        ) VALUES (
            p_draft_id, p_user_id, p_content_envelope, p_fingerprint_key_id,
            p_content_fingerprint, 'active'
        );
        RETURN p_draft_id;
    END IF;
    IF active_id IS DISTINCT FROM p_draft_id THEN
        RAISE EXCEPTION USING ERRCODE = '40001', MESSAGE = 'draft changed concurrently';
    END IF;
    UPDATE public.entry_drafts
    SET content_envelope = p_content_envelope,
        fingerprint_key_id = p_fingerprint_key_id,
        content_fingerprint = p_content_fingerprint
    WHERE id = active_id AND user_id = p_user_id AND status = 'active';
    RETURN active_id;
END
$function$;

CREATE FUNCTION public.discard_entry_draft_for_owner(p_user_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    DELETE FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active';
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.submit_text_entry_from_draft_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_fingerprint_key_id text,
    p_content_fingerprint text,
    p_entry_date date,
    p_theme_config_id uuid,
    p_processing_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    draft_row public.entry_drafts%ROWTYPE;
    existing_entry public.entries%ROWTYPE;
    retry_token uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid text submission';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-draft:' || p_user_id::text, 0)
    );
    SELECT * INTO draft_row
    FROM public.entry_drafts
    WHERE user_id = p_user_id AND status = 'active'
    FOR UPDATE;
    IF FOUND THEN
        IF draft_row.fingerprint_key_id IS DISTINCT FROM p_fingerprint_key_id
           OR draft_row.content_fingerprint IS DISTINCT FROM p_content_fingerprint
        THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'draft content mismatch';
        END IF;
        INSERT INTO public.entries (
            id, user_id, content_envelope, input_type, entry_date,
            original_theme_config_id, processing_status, processing_token,
            processing_started_at, source_draft_id
        ) VALUES (
            p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
            p_theme_config_id, 'processing', p_processing_token,
            pg_catalog.now(), draft_row.id
        );
        UPDATE public.entry_drafts
        SET status = 'submitted',
            content_envelope = NULL,
            submitted_entry_id = p_entry_id,
            submitted_at = pg_catalog.now()
        WHERE id = draft_row.id AND user_id = p_user_id;
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', p_entry_id,
            'processing_token', p_processing_token,
            'processing_status', 'processing',
            'created', true,
            'reclaimed', false
        );
    END IF;

    SELECT entry.* INTO existing_entry
    FROM public.entry_drafts AS draft
    JOIN public.entries AS entry ON entry.id = draft.submitted_entry_id
    WHERE draft.user_id = p_user_id
      AND draft.status = 'submitted'
      AND draft.fingerprint_key_id = p_fingerprint_key_id
      AND draft.content_fingerprint = p_content_fingerprint
    ORDER BY draft.submitted_at DESC, draft.id DESC
    LIMIT 1
    FOR UPDATE OF entry;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'matching draft is required';
    END IF;
    IF existing_entry.processing_status = 'failed' THEN
        retry_token := gen_random_uuid();
        UPDATE public.entries
        SET processing_status = 'processing',
            processing_token = retry_token,
            processing_error_code = NULL,
            processing_started_at = pg_catalog.now(),
            completed_at = NULL
        WHERE id = existing_entry.id
          AND user_id = p_user_id
          AND processing_status = 'failed';
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', existing_entry.id,
            'processing_token', retry_token,
            'processing_status', 'processing',
            'created', false,
            'reclaimed', true
        );
    END IF;
    RETURN pg_catalog.jsonb_build_object(
        'entry_id', existing_entry.id,
        'processing_token', NULL,
        'processing_status', existing_entry.processing_status,
        'created', false,
        'reclaimed', false
    );
END
$function$;

REVOKE ALL ON FUNCTION public.save_entry_draft_for_owner(uuid, uuid, jsonb, text, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.discard_entry_draft_for_owner(uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.submit_text_entry_from_draft_for_owner(
    uuid, uuid, jsonb, text, text, date, uuid, uuid
) FROM PUBLIC, anon, orion_app, orion_worker;

GRANT EXECUTE ON FUNCTION public.save_entry_draft_for_owner(uuid, uuid, jsonb, text, text)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.discard_entry_draft_for_owner(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.submit_text_entry_from_draft_for_owner(
    uuid, uuid, jsonb, text, text, date, uuid, uuid
) TO authenticated;
