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

CREATE TABLE public.voice_entry_actions (
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    idempotency_key text NOT NULL,
    effective_date date NOT NULL,
    status text NOT NULL DEFAULT 'claimed',
    claim_token uuid NOT NULL,
    entry_id uuid,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    PRIMARY KEY (user_id, idempotency_key),
    CONSTRAINT voice_entry_actions_status_check CHECK (status IN ('claimed', 'completed')),
    CONSTRAINT voice_entry_actions_key_check CHECK (
        idempotency_key = pg_catalog.btrim(idempotency_key)
        AND pg_catalog.length(idempotency_key) BETWEEN 1 AND 128
    ),
    CONSTRAINT voice_entry_actions_lifecycle_check CHECK (
        (status = 'claimed' AND entry_id IS NULL)
        OR (status = 'completed' AND entry_id IS NOT NULL)
    ),
    CONSTRAINT voice_entry_actions_entry_owner_fk FOREIGN KEY (entry_id, user_id)
        REFERENCES public.entries(id, user_id) ON DELETE CASCADE
);
CREATE TRIGGER voice_entry_actions_set_updated_at
BEFORE UPDATE ON public.voice_entry_actions
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
ALTER TABLE public.voice_entry_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.voice_entry_actions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.voice_entry_actions FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

ALTER TABLE public.past_entry_imports
    ADD COLUMN completed_processing_token uuid;
ALTER TABLE public.past_entry_imports
    ADD CONSTRAINT past_entry_imports_completion_token_check CHECK (
        (status = 'completed') = (completed_processing_token IS NOT NULL)
    );

CREATE FUNCTION public.claim_voice_action_for_owner(
    p_user_id uuid, p_idempotency_key text, p_effective_date date, p_claim_token uuid
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE action public.voice_entry_actions%ROWTYPE;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.length(p_idempotency_key) NOT BETWEEN 1 AND 128
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-voice:' || p_user_id::text || ':' || p_idempotency_key, 0)
    );
    SELECT * INTO action FROM public.voice_entry_actions
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO public.voice_entry_actions (
            user_id, idempotency_key, effective_date, claim_token
        ) VALUES (p_user_id, p_idempotency_key, p_effective_date, p_claim_token);
        RETURN pg_catalog.jsonb_build_object('outcome', 'claimed', 'claim_token', p_claim_token);
    END IF;
    IF action.effective_date IS DISTINCT FROM p_effective_date THEN
        RETURN pg_catalog.jsonb_build_object('outcome', 'date_conflict');
    END IF;
    IF action.status = 'completed' THEN
        RETURN pg_catalog.jsonb_build_object('outcome', 'replay', 'entry_id', action.entry_id);
    END IF;
    RETURN pg_catalog.jsonb_build_object('outcome', 'in_progress');
END
$function$;

CREATE FUNCTION public.release_voice_action_for_owner(
    p_user_id uuid, p_idempotency_key text, p_claim_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    DELETE FROM public.voice_entry_actions
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND status = 'claimed' AND claim_token = p_claim_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.create_voice_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_idempotency_key text,
    p_processing_token uuid,
    p_claim_token uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_idempotency_key IS NULL
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.length(p_idempotency_key) NOT BETWEEN 1 AND 128
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status, processing_token,
        processing_started_at, idempotency_key
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'audio', p_entry_date,
        p_theme_config_id, 'processing', p_processing_token,
        pg_catalog.now(), p_idempotency_key
    );
    UPDATE public.voice_entry_actions
    SET status = 'completed', entry_id = p_entry_id
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND effective_date = p_entry_date AND status = 'claimed' AND claim_token = p_claim_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale voice claim';
    END IF;
    RETURN p_entry_id;
END
$function$;

CREATE FUNCTION public.queue_past_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_fingerprint_key_id text,
    p_request_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_request_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid past entry';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
        p_theme_config_id, 'pending'
    );
    INSERT INTO public.past_entry_imports (
        user_id, entry_id, fingerprint_key_id, request_fingerprint, status
    ) VALUES (
        p_user_id, p_entry_id, p_fingerprint_key_id, p_request_fingerprint, 'pending'
    );
    RETURN p_entry_id;
END
$function$;

CREATE FUNCTION public.claim_past_entry_import(p_worker_id text)
RETURNS TABLE(
    import_id uuid,
    user_id uuid,
    entry_id uuid,
    processing_token uuid,
    content_envelope jsonb,
    theme_config_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    claimed public.past_entry_imports%ROWTYPE;
    token uuid := gen_random_uuid();
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.length(pg_catalog.btrim(p_worker_id)) NOT BETWEEN 1 AND 100
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO claimed
    FROM public.past_entry_imports
    WHERE status = 'pending' AND attempts < 3
    ORDER BY created_at, id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.past_entry_imports
    SET status = 'running', attempts = attempts + 1, worker_id = p_worker_id,
        processing_token = token, completed_processing_token = NULL,
        heartbeat_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = claimed.id;
    UPDATE public.entries AS entry
    SET processing_status = 'processing', processing_token = token,
        processing_error_code = NULL, processing_started_at = pg_catalog.now(), completed_at = NULL
    WHERE entry.id = claimed.entry_id AND entry.user_id = claimed.user_id;
    RETURN QUERY
    SELECT claimed.id, claimed.user_id, claimed.entry_id, token,
        entry.content_envelope, entry.original_theme_config_id
    FROM public.entries AS entry
    WHERE entry.id = claimed.entry_id AND entry.user_id = claimed.user_id;
END
$function$;

CREATE FUNCTION public.renew_past_entry_import(
    p_import_id uuid, p_worker_id text, p_processing_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.past_entry_imports SET heartbeat_at = pg_catalog.now()
    WHERE id = p_import_id AND status = 'running' AND worker_id = p_worker_id
      AND processing_token = p_processing_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.recover_stale_past_entry_imports(p_stale_before timestamptz)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE item record; recovered integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    FOR item IN
        SELECT id, user_id, entry_id, attempts FROM public.past_entry_imports
        WHERE status = 'running' AND heartbeat_at < p_stale_before
        FOR UPDATE SKIP LOCKED
    LOOP
        IF item.attempts < 3 THEN
            UPDATE public.past_entry_imports
            SET status = 'pending', worker_id = NULL, processing_token = NULL,
                heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED'
            WHERE id = item.id;
            UPDATE public.entries
            SET processing_status = 'pending', processing_token = NULL,
                processing_error_code = NULL, processing_started_at = NULL
            WHERE id = item.entry_id AND user_id = item.user_id;
        ELSE
            UPDATE public.past_entry_imports
            SET status = 'failed', worker_id = NULL, processing_token = NULL,
                heartbeat_at = NULL, completed_at = pg_catalog.now(),
                last_error_code = 'WORKER_RETRIES_EXHAUSTED'
            WHERE id = item.id;
            UPDATE public.entries
            SET processing_status = 'failed', processing_token = NULL,
                processing_error_code = 'PROCESSING_FAILED'
            WHERE id = item.entry_id AND user_id = item.user_id;
        END IF;
        recovered := recovered + 1;
    END LOOP;
    RETURN recovered;
END
$function$;

CREATE FUNCTION public.complete_past_entry_import(
    p_import_id uuid, p_worker_id text, p_processing_token uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.past_entry_imports AS import
    SET status = 'completed', worker_id = NULL, processing_token = NULL,
        completed_processing_token = p_processing_token,
        heartbeat_at = NULL, completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE import.id = p_import_id AND import.status = 'running'
      AND import.worker_id = p_worker_id
      AND import.processing_token = p_processing_token
      AND EXISTS (
          SELECT 1 FROM public.entries e
          WHERE e.id = import.entry_id AND e.user_id = import.user_id
            AND e.processing_status = 'completed'
      );
    GET DIAGNOSTICS changed = ROW_COUNT;
    IF changed = 1 THEN
        RETURN true;
    END IF;
    RETURN EXISTS (
        SELECT 1 FROM public.past_entry_imports AS import
        WHERE import.id = p_import_id AND import.status = 'completed'
          AND import.completed_processing_token = p_processing_token
    );
END
$function$;

CREATE FUNCTION public.apply_past_entry_extraction(
    p_import_id uuid,
    p_worker_id text,
    p_processing_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE item public.past_entry_imports%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO item FROM public.past_entry_imports WHERE id = p_import_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import claim';
    END IF;
    IF item.status = 'completed' AND item.completed_processing_token = p_processing_token THEN
        RETURN true;
    END IF;
    IF item.status <> 'running' OR item.worker_id IS DISTINCT FROM p_worker_id
       OR item.processing_token IS DISTINCT FROM p_processing_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import claim';
    END IF;
    PERFORM pg_catalog.set_config(
        'request.jwt.claims',
        pg_catalog.jsonb_build_object('sub', item.user_id, 'role', 'authenticated')::text,
        true
    );
    PERFORM public.apply_entry_extraction_for_owner(
        item.user_id, item.entry_id, p_processing_token, p_theme_config_id, p_mode,
        p_themes, p_ideas, p_memories, p_reflections, false
    );
    UPDATE public.ideas SET status = 'approved', decision_source = 'past_import_auto',
        decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.extracted_memories SET status = 'approved',
        decision_source = 'past_import_auto', decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.reflections SET status = 'approved', decision_source = 'past_import_auto',
        decided_at = pg_catalog.now()
    WHERE entry_id = item.entry_id AND user_id = item.user_id AND status = 'pending_approval';
    UPDATE public.past_entry_imports
    SET status = 'completed', worker_id = NULL, processing_token = NULL,
        completed_processing_token = p_processing_token,
        heartbeat_at = NULL, completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = p_import_id AND processing_token = p_processing_token;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.claim_voice_action_for_owner(uuid, text, date, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.release_voice_action_for_owner(uuid, text, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.create_voice_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
REVOKE ALL ON FUNCTION public.queue_past_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, text)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.claim_voice_action_for_owner(uuid, text, date, uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.release_voice_action_for_owner(uuid, text, uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.create_voice_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, uuid, uuid)
    TO authenticated;
GRANT EXECUTE ON FUNCTION public.queue_past_entry_for_owner(uuid, uuid, jsonb, date, uuid, text, text)
    TO authenticated;

REVOKE ALL ON FUNCTION public.claim_past_entry_import(text) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.renew_past_entry_import(uuid, text, uuid) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.recover_stale_past_entry_imports(timestamptz) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_past_entry_import(uuid, text, uuid) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;
GRANT EXECUTE ON FUNCTION public.claim_past_entry_import(text) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.renew_past_entry_import(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.recover_stale_past_entry_imports(timestamptz) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_past_entry_import(uuid, text, uuid) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;

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

CREATE FUNCTION public.retry_entry_processing_for_owner(
    p_user_id uuid,
    p_entry_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    PERFORM 1
    FROM public.entries
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed'
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;

    UPDATE public.processing_jobs
    SET status = 'pending', run_after = pg_catalog.now(), attempts = 0,
        worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
        last_error_code = NULL, completed_at = NULL
    WHERE user_id = p_user_id AND entry_id = p_entry_id
      AND job_type = 'entry_processing' AND source_version = p_entry_id::text
      AND status = 'failed'
    RETURNING id INTO job_id;

    IF job_id IS NULL THEN
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version
        ) VALUES (
            p_user_id, p_entry_id, 'entry_processing', p_entry_id::text
        )
        ON CONFLICT (user_id, job_type, source_version) DO NOTHING
        RETURNING id INTO job_id;
    END IF;
    IF job_id IS NULL THEN
        RETURN false;
    END IF;

    UPDATE public.entries
    SET processing_status = 'pending', processing_token = NULL,
        processing_error_code = NULL, processing_started_at = NULL,
        completed_at = NULL
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed';

    UPDATE public.past_entry_imports
    SET status = 'pending', attempts = 0, worker_id = NULL,
        processing_token = NULL, completed_processing_token = NULL,
        heartbeat_at = NULL, last_error_code = NULL, completed_at = NULL
    WHERE entry_id = p_entry_id AND user_id = p_user_id AND status = 'failed';

    RETURN true;
END
$function$;

CREATE OR REPLACE FUNCTION public.submit_text_entry_from_draft_for_owner(
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
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_content_fingerprint !~ '^[0-9a-f]{64}$'
       OR p_processing_token IS NULL
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
            original_theme_config_id, processing_status, source_draft_id
        ) VALUES (
            p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
            p_theme_config_id, 'pending', draft_row.id
        );
        UPDATE public.entry_drafts
        SET status = 'submitted', content_envelope = NULL,
            submitted_entry_id = p_entry_id, submitted_at = pg_catalog.now()
        WHERE id = draft_row.id AND user_id = p_user_id;
        PERFORM public.enqueue_processing_job_for_owner(
            p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
        );
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', p_entry_id,
            'processing_token', NULL,
            'processing_status', 'pending',
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
        IF public.retry_entry_processing_for_owner(p_user_id, existing_entry.id) IS NOT TRUE THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'entry retry is not current';
        END IF;
        RETURN pg_catalog.jsonb_build_object(
            'entry_id', existing_entry.id,
            'processing_token', NULL,
            'processing_status', 'pending',
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

CREATE OR REPLACE FUNCTION public.create_voice_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_idempotency_key text,
    p_processing_token uuid,
    p_claim_token uuid
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_idempotency_key IS NULL
       OR p_idempotency_key <> pg_catalog.btrim(p_idempotency_key)
       OR pg_catalog.length(p_idempotency_key) NOT BETWEEN 1 AND 128
       OR p_processing_token IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid voice action';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status, idempotency_key
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'audio', p_entry_date,
        p_theme_config_id, 'pending', p_idempotency_key
    );
    UPDATE public.voice_entry_actions
    SET status = 'completed', entry_id = p_entry_id
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key
      AND effective_date = p_entry_date AND status = 'claimed' AND claim_token = p_claim_token;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale voice claim';
    END IF;
    PERFORM public.enqueue_processing_job_for_owner(
        p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
    );
    RETURN p_entry_id;
END
$function$;

CREATE OR REPLACE FUNCTION public.queue_past_entry_for_owner(
    p_user_id uuid,
    p_entry_id uuid,
    p_content_envelope jsonb,
    p_entry_date date,
    p_theme_config_id uuid,
    p_fingerprint_key_id text,
    p_request_fingerprint text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id
       OR public.is_valid_entry_envelope_v2(p_content_envelope) IS NOT TRUE
       OR p_request_fingerprint !~ '^[0-9a-f]{64}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid past entry';
    END IF;
    INSERT INTO public.entries (
        id, user_id, content_envelope, input_type, entry_date,
        original_theme_config_id, processing_status
    ) VALUES (
        p_entry_id, p_user_id, p_content_envelope, 'text', p_entry_date,
        p_theme_config_id, 'pending'
    );
    INSERT INTO public.past_entry_imports (
        user_id, entry_id, fingerprint_key_id, request_fingerprint, status
    ) VALUES (
        p_user_id, p_entry_id, p_fingerprint_key_id, p_request_fingerprint, 'pending'
    );
    PERFORM public.enqueue_processing_job_for_owner(
        p_user_id, p_entry_id, p_entry_id::text, pg_catalog.now()
    );
    RETURN p_entry_id;
END
$function$;

CREATE OR REPLACE FUNCTION public.claim_processing_job(p_worker_id text)
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
          AND target_entry.user_id = claimed.user_id
          AND NOT (
              target_entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS classification
                  WHERE classification.entry_id = target_entry.id
                    AND classification.user_id = target_entry.user_id
              )
          );
        UPDATE public.past_entry_imports AS imported
        SET status = 'running', attempts = claimed.attempts,
            worker_id = p_worker_id, processing_token = token,
            completed_processing_token = NULL, heartbeat_at = pg_catalog.now(),
            last_error_code = NULL, completed_at = NULL
        WHERE imported.entry_id = claimed.entry_id
          AND imported.user_id = claimed.user_id
          AND imported.status = 'pending';
    END IF;
    RETURN QUERY SELECT claimed.id, claimed.user_id, claimed.entry_id,
        claimed.job_type, claimed.source_version, token, claimed.attempts;
END
$function$;

CREATE OR REPLACE FUNCTION public.renew_processing_job(
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
    UPDATE public.processing_jobs
    SET heartbeat_at = pg_catalog.now()
    WHERE id = p_job_id AND status = 'running' AND worker_id = p_worker_id
      AND claim_token = p_claim_token
    RETURNING * INTO item;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    IF item.job_type = 'entry_processing' THEN
        UPDATE public.past_entry_imports
        SET heartbeat_at = pg_catalog.now()
        WHERE entry_id = item.entry_id AND user_id = item.user_id
          AND status = 'running' AND worker_id = p_worker_id
          AND processing_token = p_claim_token;
    END IF;
    RETURN true;
END
$function$;

CREATE OR REPLACE FUNCTION public.fail_processing_job(
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
            WHERE id = item.entry_id AND user_id = item.user_id
              AND processing_token = p_claim_token;
            UPDATE public.past_entry_imports
            SET status = 'failed', attempts = item.attempts, worker_id = NULL,
                processing_token = NULL, completed_processing_token = NULL,
                heartbeat_at = NULL, completed_at = pg_catalog.now(),
                last_error_code = p_error_code
            WHERE entry_id = item.entry_id AND user_id = item.user_id
              AND status = 'running' AND processing_token = p_claim_token;
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
        WHERE id = item.entry_id AND user_id = item.user_id
          AND processing_token = p_claim_token;
        UPDATE public.past_entry_imports
        SET status = 'pending', attempts = item.attempts, worker_id = NULL,
            processing_token = NULL, completed_processing_token = NULL,
            heartbeat_at = NULL, last_error_code = p_error_code, completed_at = NULL
        WHERE entry_id = item.entry_id AND user_id = item.user_id
          AND status = 'running' AND processing_token = p_claim_token;
    END IF;
    RETURN 'pending';
END
$function$;

CREATE OR REPLACE FUNCTION public.recover_stale_processing_jobs(p_stale_before timestamptz)
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
                WHERE id = item.entry_id AND user_id = item.user_id
                  AND processing_token = item.claim_token;
                UPDATE public.past_entry_imports
                SET status = 'failed', attempts = item.attempts, worker_id = NULL,
                    processing_token = NULL, completed_processing_token = NULL,
                    heartbeat_at = NULL, completed_at = pg_catalog.now(),
                    last_error_code = 'WORKER_RETRIES_EXHAUSTED'
                WHERE entry_id = item.entry_id AND user_id = item.user_id
                  AND status = 'running' AND processing_token = item.claim_token;
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
                WHERE id = item.entry_id AND user_id = item.user_id
                  AND processing_token = item.claim_token;
                UPDATE public.past_entry_imports
                SET status = 'pending', attempts = item.attempts, worker_id = NULL,
                    processing_token = NULL, completed_processing_token = NULL,
                    heartbeat_at = NULL, last_error_code = 'WORKER_INTERRUPTED',
                    completed_at = NULL
                WHERE entry_id = item.entry_id AND user_id = item.user_id
                  AND status = 'running' AND processing_token = item.claim_token;
            END IF;
        END IF;
        recovered := recovered + 1;
    END LOOP;
    RETURN recovered;
END
$function$;

CREATE FUNCTION public.get_entry_processing_payload(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
)
RETURNS TABLE (
    content_envelope jsonb,
    theme_config_id uuid,
    past_import boolean,
    already_materialized boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT entry.content_envelope, entry.original_theme_config_id,
        EXISTS (
            SELECT 1 FROM public.past_entry_imports AS imported
            WHERE imported.entry_id = entry.id AND imported.user_id = entry.user_id
        ),
        entry.processing_status = 'completed' AND EXISTS (
            SELECT 1 FROM public.entry_classifications AS classification
            WHERE classification.entry_id = entry.id
              AND classification.user_id = entry.user_id
        )
    FROM public.processing_jobs AS job
    JOIN public.entries AS entry
      ON entry.id = job.entry_id AND entry.user_id = job.user_id
    WHERE job.id = p_job_id AND job.job_type = 'entry_processing'
      AND job.status = 'running' AND job.worker_id = p_worker_id
      AND job.claim_token = p_claim_token
      AND (
          (entry.processing_status = 'processing' AND entry.processing_token = p_claim_token)
          OR (
              entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS existing
                  WHERE existing.entry_id = entry.id AND existing.user_id = entry.user_id
              )
          )
      );
END
$function$;

CREATE FUNCTION public.apply_legacy_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    imported boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO job FROM public.processing_jobs WHERE id = p_job_id FOR UPDATE;
    IF NOT FOUND OR job.job_type <> 'entry_processing' OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || job.user_id::text, 0)
    );
    IF EXISTS (
        SELECT 1 FROM public.entry_classifications
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
    END IF;
    PERFORM pg_catalog.set_config(
        'request.jwt.claims',
        pg_catalog.jsonb_build_object('sub', job.user_id, 'role', 'authenticated')::text,
        true
    );
    PERFORM public.apply_entry_extraction_for_owner(
        job.user_id, job.entry_id, p_claim_token, p_theme_config_id, p_mode,
        p_themes, p_ideas, p_memories, p_reflections, false
    );
    SELECT EXISTS (
        SELECT 1 FROM public.past_entry_imports
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) INTO imported;
    IF imported THEN
        UPDATE public.ideas
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.extracted_memories
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.reflections
        SET status = 'approved', decision_source = 'past_import_auto',
            decided_at = pg_catalog.now()
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'pending_approval';
        UPDATE public.past_entry_imports
        SET status = 'completed', worker_id = NULL, processing_token = NULL,
            completed_processing_token = p_claim_token, heartbeat_at = NULL,
            completed_at = pg_catalog.now(), last_error_code = NULL
        WHERE entry_id = job.entry_id AND user_id = job.user_id
          AND status = 'running' AND processing_token = p_claim_token;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import audit claim';
        END IF;
    END IF;
    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE id = job.id;
    RETURN true;
END
$function$;

CREATE FUNCTION public.complete_materialized_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
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
    UPDATE public.processing_jobs AS job
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL
    WHERE job.id = p_job_id AND job.job_type = 'entry_processing'
      AND job.status = 'running' AND job.worker_id = p_worker_id
      AND job.claim_token = p_claim_token
      AND EXISTS (
          SELECT 1 FROM public.entries AS entry
          WHERE entry.id = job.entry_id AND entry.user_id = job.user_id
            AND entry.processing_status = 'completed'
            AND EXISTS (
                SELECT 1 FROM public.entry_classifications AS classification
                WHERE classification.entry_id = entry.id
                  AND classification.user_id = entry.user_id
            )
      );
    GET DIAGNOSTICS changed = ROW_COUNT;
    RETURN changed = 1;
END
$function$;

CREATE FUNCTION public.enqueue_entry_processing_backfill(
    p_limit integer DEFAULT 100,
    p_run_after timestamptz DEFAULT pg_catalog.now() + pg_catalog.make_interval(mins => 5)
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    enqueued integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_limit NOT BETWEEN 1 AND 100 OR p_run_after IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    WITH selected AS (
        SELECT entry.id, entry.user_id
        FROM public.entries AS entry
        WHERE entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.processing_jobs AS existing
              WHERE existing.user_id = entry.user_id
                AND existing.job_type = 'entry_processing'
                AND existing.source_version = entry.id::text
          )
        ORDER BY entry.created_at, entry.id
        LIMIT p_limit
        FOR UPDATE OF entry SKIP LOCKED
    ), inserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', id::text, p_run_after
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO NOTHING
        RETURNING 1
    )
    SELECT pg_catalog.count(*)::integer INTO enqueued FROM inserted;
    RETURN enqueued;
END
$function$;

-- The generalized processing queue supersedes the historical-import-only
-- worker contract. Remove those worker RPCs so there is a single claim,
-- heartbeat, recovery, completion, and failure path after this migration.
DROP FUNCTION public.apply_past_entry_extraction(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
);
DROP FUNCTION public.complete_past_entry_import(uuid, text, uuid);
DROP FUNCTION public.recover_stale_past_entry_imports(timestamptz);
DROP FUNCTION public.renew_past_entry_import(uuid, text, uuid);
DROP FUNCTION public.claim_past_entry_import(text);

REVOKE ALL ON FUNCTION public.retry_entry_processing_for_owner(uuid, uuid)
    FROM PUBLIC, anon, orion_app, orion_worker;
GRANT EXECUTE ON FUNCTION public.retry_entry_processing_for_owner(uuid, uuid)
    TO authenticated;

REVOKE ALL ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_legacy_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_legacy_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz)
    TO orion_worker;

-- P0-04 combined entry analysis. The worker now persists legacy extraction,
-- quality audit, accepted signals, lifecycle state, and reflection counters in
-- one claim-bound transaction.

DROP FUNCTION public.get_entry_processing_payload(uuid, text, uuid);

CREATE FUNCTION public.get_entry_processing_payload(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid
)
RETURNS TABLE (
    content_envelope jsonb,
    theme_config_id uuid,
    entry_date date,
    past_import boolean,
    already_materialized boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT entry.content_envelope, entry.original_theme_config_id, entry.entry_date,
        EXISTS (
            SELECT 1 FROM public.past_entry_imports AS imported
            WHERE imported.entry_id = entry.id AND imported.user_id = entry.user_id
        ),
        entry.processing_status = 'completed' AND EXISTS (
            SELECT 1 FROM public.entry_classifications AS classification
            WHERE classification.entry_id = entry.id
              AND classification.user_id = entry.user_id
        )
    FROM public.processing_jobs AS job
    JOIN public.entries AS entry
      ON entry.id = job.entry_id AND entry.user_id = job.user_id
    WHERE job.id = p_job_id AND job.job_type = 'entry_processing'
      AND job.status = 'running' AND job.worker_id = p_worker_id
      AND job.claim_token = p_claim_token
      AND (
          (entry.processing_status = 'processing' AND entry.processing_token = p_claim_token)
          OR (
              entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS existing
                  WHERE existing.entry_id = entry.id AND existing.user_id = entry.user_id
              )
          )
      );
END
$function$;

CREATE FUNCTION public.get_entry_quality_history(
    p_user_id uuid,
    p_entry_id uuid,
    p_entry_date date
)
RETURNS TABLE (
    duplicate_cluster_key text,
    ngram_sketch text[],
    eligibility text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_entry_date IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    RETURN QUERY
    SELECT analysis.duplicate_cluster_key, analysis.ngram_sketch, analysis.eligibility
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND analysis.entry_id <> p_entry_id
      AND entry.entry_date BETWEEN p_entry_date - 90 AND p_entry_date
    ORDER BY analysis.source_version DESC
    LIMIT 1000;
END
$function$;

CREATE FUNCTION public.apply_combined_entry_processing_job(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_theme_config_id uuid,
    p_mode text,
    p_themes jsonb,
    p_ideas jsonb,
    p_memories jsonb,
    p_reflections jsonb,
    p_analysis jsonb,
    p_signals jsonb,
    p_apply_legacy boolean
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    imported boolean;
    analysis_payload jsonb := p_analysis;
    signals_payload jsonb := p_signals;
    existing_source_version bigint;
    reason_codes jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_themes) <> 'array'
       OR pg_catalog.jsonb_typeof(p_ideas) <> 'array'
       OR pg_catalog.jsonb_typeof(p_memories) <> 'array'
       OR pg_catalog.jsonb_typeof(p_reflections) <> 'array'
       OR pg_catalog.jsonb_typeof(p_analysis) <> 'object'
       OR pg_catalog.jsonb_typeof(p_signals) <> 'array'
       OR p_apply_legacy IS NULL
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
        SELECT source_version INTO existing_source_version
        FROM public.entry_analyses
        WHERE entry_id = job.entry_id AND user_id = job.user_id;
        IF existing_source_version IS NOT NULL THEN
            RETURN existing_source_version;
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
    IF EXISTS (
        SELECT 1 FROM public.entry_analyses
        WHERE entry_id = job.entry_id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'entry analysis already persisted';
    END IF;

    -- Close the exact-duplicate race under the same per-user lock that protects
    -- counters. The Python gate supplies the canonical cluster fingerprint.
    IF analysis_payload ->> 'eligibility' = 'accepted'
       AND NULLIF(analysis_payload ->> 'duplicate_cluster_key', '') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM public.entry_analyses AS existing
           WHERE existing.user_id = job.user_id
             AND existing.eligibility = 'accepted'
             AND existing.duplicate_cluster_key =
                 analysis_payload ->> 'duplicate_cluster_key'
       )
    THEN
        SELECT pg_catalog.to_jsonb(ARRAY(
            SELECT code
            FROM (
                SELECT DISTINCT code
                FROM pg_catalog.jsonb_array_elements_text(
                    COALESCE(
                        analysis_payload -> 'exclusion_reason_codes',
                        '[]'::jsonb
                    ) || '["EXACT_DUPLICATE"]'::jsonb
                ) AS reason(code)
                ORDER BY code
                LIMIT 10
            ) AS distinct_codes
        )) INTO reason_codes;
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{eligibility}', '"excluded"'::jsonb
        );
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{exclusion_reason_codes}', reason_codes
        );
        analysis_payload := pg_catalog.jsonb_set(
            analysis_payload, '{deterministic_features,exact_duplicate}', 'true'::jsonb
        );
        signals_payload := '[]'::jsonb;
    END IF;

    IF p_apply_legacy THEN
        IF EXISTS (
            SELECT 1 FROM public.entry_classifications
            WHERE entry_id = job.entry_id AND user_id = job.user_id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'extraction already persisted';
        END IF;
        PERFORM pg_catalog.set_config(
            'request.jwt.claims',
            pg_catalog.jsonb_build_object(
                'sub', job.user_id, 'role', 'authenticated'
            )::text,
            true
        );
        PERFORM public.apply_entry_extraction_for_owner(
            job.user_id, job.entry_id, p_claim_token, p_theme_config_id, p_mode,
            p_themes, p_ideas, p_memories, p_reflections, false
        );
        SELECT EXISTS (
            SELECT 1 FROM public.past_entry_imports
            WHERE entry_id = job.entry_id AND user_id = job.user_id
        ) INTO imported;
        IF imported THEN
            UPDATE public.ideas
            SET status = 'approved', decision_source = 'past_import_auto',
                decided_at = pg_catalog.now()
            WHERE entry_id = job.entry_id AND user_id = job.user_id
              AND status = 'pending_approval';
            UPDATE public.extracted_memories
            SET status = 'approved', decision_source = 'past_import_auto',
                decided_at = pg_catalog.now()
            WHERE entry_id = job.entry_id AND user_id = job.user_id
              AND status = 'pending_approval';
            UPDATE public.reflections
            SET status = 'approved', decision_source = 'past_import_auto',
                decided_at = pg_catalog.now()
            WHERE entry_id = job.entry_id AND user_id = job.user_id
              AND status = 'pending_approval';
            UPDATE public.past_entry_imports
            SET status = 'completed', worker_id = NULL, processing_token = NULL,
                completed_processing_token = p_claim_token, heartbeat_at = NULL,
                completed_at = pg_catalog.now(), last_error_code = NULL
            WHERE entry_id = job.entry_id AND user_id = job.user_id
              AND status = 'running' AND processing_token = p_claim_token;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale import audit claim';
            END IF;
        END IF;
    ELSIF NOT EXISTS (
        SELECT 1 FROM public.entries AS entry
        WHERE entry.id = job.entry_id AND entry.user_id = job.user_id
          AND entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'materialized entry is invalid';
    END IF;

    RETURN public.apply_entry_analysis(
        p_job_id, p_worker_id, p_claim_token, analysis_payload, signals_payload
    );
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_entry_processing_backfill(
    p_limit integer DEFAULT 100,
    p_run_after timestamptz DEFAULT pg_catalog.now() + pg_catalog.make_interval(mins => 5)
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    enqueued integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_limit NOT BETWEEN 1 AND 100 OR p_run_after IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    WITH selected AS (
        SELECT entry.id, entry.user_id
        FROM public.entries AS entry
        WHERE entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = entry.id
                AND analysis.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.processing_jobs AS running
              WHERE running.user_id = entry.user_id
                AND running.job_type = 'entry_processing'
                AND running.source_version = entry.id::text
                AND running.status IN ('pending', 'running')
          )
        ORDER BY entry.created_at, entry.id
        LIMIT p_limit
        FOR UPDATE OF entry SKIP LOCKED
    ), upserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', id::text, p_run_after
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
            status = 'pending', run_after = EXCLUDED.run_after, attempts = 0,
            worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
            last_error_code = NULL, completed_at = NULL
        WHERE public.processing_jobs.status IN ('completed', 'failed')
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = public.processing_jobs.entry_id
                AND analysis.user_id = public.processing_jobs.user_id
          )
        RETURNING 1
    )
    SELECT pg_catalog.count(*)::integer INTO enqueued FROM upserted;
    RETURN enqueued;
END
$function$;

DROP FUNCTION public.apply_legacy_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb
);
DROP FUNCTION public.complete_materialized_entry_processing_job(uuid, text, uuid);

REVOKE ALL ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_entry_quality_history(uuid, uuid, date)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.apply_combined_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, boolean
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.get_entry_processing_payload(uuid, text, uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_entry_quality_history(uuid, uuid, date)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.apply_combined_entry_processing_job(
    uuid, text, uuid, uuid, text, jsonb, jsonb, jsonb, jsonb, jsonb, jsonb, boolean
) TO orion_worker;

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

-- P0-09B: cohort-scoped rollout, real shadow completion, queue priority,
-- and persisted/resumable entry-analysis backfill control.

ALTER TABLE public.processing_jobs
    ADD COLUMN execution_mode text,
    ADD COLUMN priority smallint;

UPDATE public.processing_jobs
SET execution_mode = CASE job_type
        WHEN 'entry_processing' THEN 'user'
        ELSE 'publish'
    END,
    priority = CASE job_type
        WHEN 'entry_processing' THEN 100
        ELSE 80
    END;

ALTER TABLE public.processing_jobs
    ALTER COLUMN execution_mode SET DEFAULT 'user',
    ALTER COLUMN execution_mode SET NOT NULL,
    ALTER COLUMN priority SET DEFAULT 100,
    ALTER COLUMN priority SET NOT NULL,
    ADD CONSTRAINT processing_jobs_execution_mode_check CHECK (
        (job_type = 'entry_processing' AND execution_mode IN ('user', 'backfill'))
        OR (job_type = 'reflection_synthesis' AND execution_mode IN ('shadow', 'publish'))
    ),
    ADD CONSTRAINT processing_jobs_priority_check CHECK (
        (execution_mode = 'user' AND priority = 100)
        OR (execution_mode = 'publish' AND priority = 80)
        OR (execution_mode = 'shadow' AND priority = 60)
        OR (execution_mode = 'backfill' AND priority = 10)
    );

DROP INDEX public.processing_jobs_claim_idx;
CREATE INDEX processing_jobs_claim_idx
    ON public.processing_jobs (priority DESC, run_after, created_at, id)
    WHERE status = 'pending' AND attempts < 3;

CREATE TABLE public.reflection_shadow_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    job_id uuid NOT NULL,
    source_version bigint NOT NULL,
    candidate_count integer NOT NULL,
    selected_count integer NOT NULL,
    provider_called boolean NOT NULL,
    completed_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    UNIQUE (job_id),
    UNIQUE (user_id, source_version),
    CONSTRAINT reflection_shadow_runs_job_owner_fk
        FOREIGN KEY (job_id, user_id)
        REFERENCES public.processing_jobs(id, user_id) ON DELETE CASCADE,
    CONSTRAINT reflection_shadow_runs_counts_check CHECK (
        source_version >= 1
        AND candidate_count >= 0
        AND selected_count >= 0
        AND selected_count <= candidate_count
    )
);

CREATE INDEX reflection_shadow_runs_owner_source_idx
    ON public.reflection_shadow_runs (user_id, source_version DESC);

CREATE TABLE public.processing_backfill_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'planned',
    batch_size smallint NOT NULL,
    max_queue_depth integer NOT NULL,
    max_oldest_pending_seconds integer NOT NULL,
    planned_count integer NOT NULL,
    enqueued_count integer NOT NULL DEFAULT 0,
    cursor_created_at timestamptz,
    cursor_entry_id uuid,
    upper_bound_created_at timestamptz,
    upper_bound_entry_id uuid,
    last_throttle_reason text,
    last_checked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.now(),
    completed_at timestamptz,
    CONSTRAINT processing_backfill_runs_status_check CHECK (
        status IN ('planned', 'running', 'paused', 'completed')
    ),
    CONSTRAINT processing_backfill_runs_limits_check CHECK (
        batch_size BETWEEN 1 AND 100
        AND max_queue_depth BETWEEN 1 AND 100000
        AND max_oldest_pending_seconds BETWEEN 30 AND 86400
        AND planned_count >= 0
        AND enqueued_count >= 0
        AND enqueued_count <= planned_count
    ),
    CONSTRAINT processing_backfill_runs_cursor_check CHECK (
        (cursor_created_at IS NULL) = (cursor_entry_id IS NULL)
        AND (upper_bound_created_at IS NULL) = (upper_bound_entry_id IS NULL)
    ),
    CONSTRAINT processing_backfill_runs_throttle_check CHECK (
        last_throttle_reason IS NULL
        OR last_throttle_reason IN ('QUEUE_DEPTH', 'OLDEST_PENDING_AGE')
    ),
    CONSTRAINT processing_backfill_runs_lifecycle_check CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    )
);

CREATE UNIQUE INDEX processing_backfill_runs_one_active_idx
    ON public.processing_backfill_runs ((true))
    WHERE status IN ('planned', 'running', 'paused');

CREATE TABLE public.processing_backfill_users (
    run_id uuid NOT NULL REFERENCES public.processing_backfill_runs(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    PRIMARY KEY (run_id, user_id)
);

CREATE INDEX processing_backfill_users_owner_idx
    ON public.processing_backfill_users (user_id, run_id);

ALTER TABLE public.reflection_shadow_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reflection_shadow_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.processing_backfill_users FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.reflection_shadow_runs,
    public.processing_backfill_runs, public.processing_backfill_users
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;

CREATE OR REPLACE FUNCTION public.enqueue_processing_job_for_owner(
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
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, 'entry_processing', 'user', 100,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

CREATE OR REPLACE FUNCTION public.enqueue_processing_job(
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
    mode text;
    job_priority smallint;
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
    mode := CASE p_job_type WHEN 'entry_processing' THEN 'user' ELSE 'publish' END;
    job_priority := CASE p_job_type WHEN 'entry_processing' THEN 100 ELSE 80 END;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, p_job_type, mode, job_priority,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE
        SET source_version = EXCLUDED.source_version
    RETURNING id INTO result;
    RETURN result;
END
$function$;

DROP FUNCTION public.claim_processing_job(text);
CREATE FUNCTION public.claim_processing_job(p_worker_id text)
RETURNS TABLE (
    job_id uuid,
    user_id uuid,
    entry_id uuid,
    job_type text,
    execution_mode text,
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
    ORDER BY queued.priority DESC, queued.run_after, queued.created_at, queued.id
    LIMIT 1
    FOR UPDATE SKIP LOCKED;
    IF NOT FOUND THEN
        RETURN;
    END IF;
    UPDATE public.processing_jobs AS target
    SET status = 'running', attempts = target.attempts + 1, worker_id = p_worker_id,
        claim_token = token, heartbeat_at = pg_catalog.now(),
        last_error_code = NULL, completed_at = NULL,
        updated_at = pg_catalog.now()
    WHERE target.id = claimed.id
    RETURNING target.* INTO claimed;
    IF claimed.job_type = 'entry_processing' THEN
        UPDATE public.entries AS target_entry
        SET processing_status = 'processing', processing_token = token,
            processing_error_code = NULL, processing_started_at = pg_catalog.now(),
            completed_at = NULL
        WHERE target_entry.id = claimed.entry_id
          AND target_entry.user_id = claimed.user_id
          AND NOT (
              target_entry.processing_status = 'completed'
              AND EXISTS (
                  SELECT 1 FROM public.entry_classifications AS classification
                  WHERE classification.entry_id = target_entry.id
                    AND classification.user_id = target_entry.user_id
              )
          );
        UPDATE public.past_entry_imports AS imported
        SET status = 'running', attempts = claimed.attempts,
            worker_id = p_worker_id, processing_token = token,
            completed_processing_token = NULL, heartbeat_at = pg_catalog.now(),
            last_error_code = NULL, completed_at = NULL
        WHERE imported.entry_id = claimed.entry_id
          AND imported.user_id = claimed.user_id
          AND imported.status = 'pending';
    END IF;
    RETURN QUERY SELECT claimed.id, claimed.user_id, claimed.entry_id,
        claimed.job_type, claimed.execution_mode, claimed.source_version,
        token, claimed.attempts;
END
$function$;

DROP FUNCTION public.schedule_reflection_jobs(timestamptz);
CREATE FUNCTION public.schedule_reflection_jobs(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
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
    job_priority smallint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_now IS NULL
       OR p_execution_mode NOT IN ('shadow', 'publish')
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    job_priority := CASE p_execution_mode WHEN 'publish' THEN 80 ELSE 60 END;
    FOR profile IN
        SELECT user_id, timezone
        FROM public.user_profiles
        WHERE user_id = ANY(p_user_ids)
          AND (p_now AT TIME ZONE timezone)::time >= TIME '18:00:00'
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
                user_id, entry_id, job_type, execution_mode, priority,
                source_version, run_after
            ) VALUES (
                profile.user_id, NULL, 'reflection_synthesis',
                p_execution_mode, job_priority,
                state.latest_accepted_source_version::text, p_now
            ) ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
                execution_mode = EXCLUDED.execution_mode,
                priority = EXCLUDED.priority,
                status = 'pending',
                run_after = EXCLUDED.run_after,
                attempts = 0,
                worker_id = NULL,
                claim_token = NULL,
                heartbeat_at = NULL,
                last_error_code = NULL,
                completed_at = NULL,
                updated_at = pg_catalog.now()
            WHERE public.processing_jobs.job_type = 'reflection_synthesis'
              AND public.processing_jobs.execution_mode = 'shadow'
              AND EXCLUDED.execution_mode = 'publish'
              AND public.processing_jobs.status IN ('pending', 'completed', 'failed')
              AND NOT EXISTS (
                  SELECT 1 FROM public.reflection_snapshots AS snapshot
                  WHERE snapshot.user_id = public.processing_jobs.user_id
                    AND snapshot.source_version = public.processing_jobs.source_version::bigint
              );
            GET DIAGNOSTICS changed = ROW_COUNT;
            enqueued := enqueued + changed;
        END IF;
    END LOOP;
    RETURN enqueued;
END
$function$;

CREATE FUNCTION public.complete_reflection_shadow(
    p_job_id uuid,
    p_worker_id text,
    p_claim_token uuid,
    p_candidate_count integer,
    p_selected_count integer,
    p_provider_called boolean
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    result uuid;
    changed integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_candidate_count < 0
       OR p_selected_count < 0
       OR p_selected_count > p_candidate_count
       OR p_provider_called IS NULL
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
       AND job.execution_mode = 'shadow'
       AND job.claim_token IS NOT DISTINCT FROM p_claim_token
    THEN
        SELECT id INTO result
        FROM public.reflection_shadow_runs
        WHERE job_id = job.id AND user_id = job.user_id;
        IF result IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
        END IF;
        RETURN result;
    END IF;
    IF job.job_type <> 'reflection_synthesis'
       OR job.execution_mode <> 'shadow'
       OR job.status <> 'running'
       OR job.worker_id IS DISTINCT FROM p_worker_id
       OR job.claim_token IS DISTINCT FROM p_claim_token
       OR job.source_version !~ '^[1-9][0-9]*$'
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    INSERT INTO public.reflection_shadow_runs (
        user_id, job_id, source_version, candidate_count,
        selected_count, provider_called
    ) VALUES (
        job.user_id, job.id, job.source_version::bigint, p_candidate_count,
        p_selected_count, p_provider_called
    )
    ON CONFLICT (job_id) DO UPDATE SET job_id = EXCLUDED.job_id
    RETURNING id INTO result;

    UPDATE public.processing_jobs
    SET status = 'completed', worker_id = NULL, heartbeat_at = NULL,
        completed_at = pg_catalog.now(), last_error_code = NULL,
        updated_at = pg_catalog.now()
    WHERE id = job.id AND status = 'running'
      AND worker_id = p_worker_id AND claim_token = p_claim_token;
    GET DIAGNOSTICS changed = ROW_COUNT;
    IF changed <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;
    UPDATE public.reflection_user_state
    SET last_processing_error_code = NULL, updated_at = pg_catalog.now()
    WHERE user_id = job.user_id;
    RETURN result;
END
$function$;

CREATE FUNCTION public.plan_entry_processing_backfill(
    p_user_ids uuid[],
    p_batch_size integer,
    p_max_queue_depth integer,
    p_max_oldest_pending_seconds integer
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    result uuid;
    planned integer;
    upper_created timestamptz;
    upper_id uuid;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR p_batch_size NOT BETWEEN 1 AND 100
       OR p_max_queue_depth NOT BETWEEN 1 AND 100000
       OR p_max_oldest_pending_seconds NOT BETWEEN 30 AND 86400
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
       OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
           WHERE NOT EXISTS (
               SELECT 1 FROM auth.users WHERE id = requested.user_id
           )
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT pg_catalog.count(*)::integer
    INTO planned
    FROM public.entries AS entry
    WHERE entry.user_id = ANY(p_user_ids)
      AND entry.processing_status = 'completed'
      AND EXISTS (
          SELECT 1 FROM public.entry_classifications AS classification
          WHERE classification.entry_id = entry.id
            AND classification.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.entry_analyses AS analysis
          WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.processing_jobs AS active
          WHERE active.user_id = entry.user_id
            AND active.job_type = 'entry_processing'
            AND active.source_version = entry.id::text
            AND active.status IN ('pending', 'running')
      );

    SELECT entry.created_at, entry.id
    INTO upper_created, upper_id
    FROM public.entries AS entry
    WHERE entry.user_id = ANY(p_user_ids)
      AND entry.processing_status = 'completed'
      AND EXISTS (
          SELECT 1 FROM public.entry_classifications AS classification
          WHERE classification.entry_id = entry.id
            AND classification.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.entry_analyses AS analysis
          WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM public.processing_jobs AS active
          WHERE active.user_id = entry.user_id
            AND active.job_type = 'entry_processing'
            AND active.source_version = entry.id::text
            AND active.status IN ('pending', 'running')
      )
    ORDER BY entry.created_at DESC, entry.id DESC
    LIMIT 1;

    INSERT INTO public.processing_backfill_runs (
        status, batch_size, max_queue_depth, max_oldest_pending_seconds,
        planned_count, upper_bound_created_at, upper_bound_entry_id, completed_at
    ) VALUES (
        CASE WHEN planned = 0 THEN 'completed' ELSE 'planned' END,
        p_batch_size, p_max_queue_depth, p_max_oldest_pending_seconds,
        planned, upper_created, upper_id,
        CASE WHEN planned = 0 THEN pg_catalog.now() ELSE NULL END
    ) RETURNING id INTO result;

    INSERT INTO public.processing_backfill_users (run_id, user_id)
    SELECT result, requested.user_id
    FROM pg_catalog.unnest(p_user_ids) AS requested(user_id);
    RETURN result;
END
$function$;

CREATE FUNCTION public.get_entry_processing_backfill_status(p_run_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
    queue_depth integer;
    oldest_pending integer;
    cohort_size integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run FROM public.processing_backfill_runs WHERE id = p_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    SELECT pg_catalog.count(*)::integer INTO queue_depth
    FROM public.processing_jobs
    WHERE status IN ('pending', 'running');
    SELECT COALESCE(
        GREATEST(
            0,
            EXTRACT(
                EPOCH FROM pg_catalog.now() - pg_catalog.min(created_at)
            )::integer
        ),
        0
    ) INTO oldest_pending
    FROM public.processing_jobs
    WHERE status = 'pending';
    SELECT pg_catalog.count(*)::integer INTO cohort_size
    FROM public.processing_backfill_users WHERE run_id = p_run_id;
    RETURN pg_catalog.jsonb_build_object(
        'run_id', run.id,
        'status', run.status,
        'planned_count', run.planned_count,
        'enqueued_count', run.enqueued_count,
        'cohort_size', cohort_size,
        'batch_size', run.batch_size,
        'queue_depth', queue_depth,
        'oldest_pending_seconds', oldest_pending,
        'cursor_created_at', run.cursor_created_at,
        'cursor_entry_id', run.cursor_entry_id,
        'throttled', run.last_throttle_reason IS NOT NULL,
        'throttle_reason', run.last_throttle_reason
    );
END
$function$;

CREATE FUNCTION public.run_entry_processing_backfill_batch(p_run_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
    queue_depth integer;
    oldest_pending integer;
    selected_count integer;
    changed_count integer;
    last_created timestamptz;
    last_id uuid;
    has_more boolean;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker' THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run
    FROM public.processing_backfill_runs
    WHERE id = p_run_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    IF run.status IN ('paused', 'completed') THEN
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    SELECT pg_catalog.count(*)::integer INTO queue_depth
    FROM public.processing_jobs WHERE status IN ('pending', 'running');
    SELECT COALESCE(
        GREATEST(
            0,
            EXTRACT(
                EPOCH FROM pg_catalog.now() - pg_catalog.min(created_at)
            )::integer
        ),
        0
    ) INTO oldest_pending
    FROM public.processing_jobs WHERE status = 'pending';

    IF queue_depth >= run.max_queue_depth
       OR oldest_pending >= run.max_oldest_pending_seconds
    THEN
        UPDATE public.processing_backfill_runs
        SET status = 'running',
            last_throttle_reason = CASE
                WHEN queue_depth >= run.max_queue_depth THEN 'QUEUE_DEPTH'
                ELSE 'OLDEST_PENDING_AGE'
            END,
            last_checked_at = pg_catalog.now(),
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    WITH selected AS MATERIALIZED (
        SELECT entry.id, entry.user_id, entry.created_at
        FROM public.entries AS entry
        JOIN public.processing_backfill_users AS cohort
          ON cohort.user_id = entry.user_id AND cohort.run_id = p_run_id
        WHERE entry.processing_status = 'completed'
          AND (entry.created_at, entry.id) <=
              (run.upper_bound_created_at, run.upper_bound_entry_id)
          AND (
              run.cursor_created_at IS NULL
              OR (entry.created_at, entry.id) >
                 (run.cursor_created_at, run.cursor_entry_id)
          )
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = entry.id
                AND analysis.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.processing_jobs AS active
              WHERE active.user_id = entry.user_id
                AND active.job_type = 'entry_processing'
                AND active.source_version = entry.id::text
                AND active.status IN ('pending', 'running')
          )
        ORDER BY entry.created_at, entry.id
        LIMIT run.batch_size
        FOR UPDATE OF entry
    ), upserted AS (
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, execution_mode, priority,
            source_version, run_after
        )
        SELECT user_id, id, 'entry_processing', 'backfill', 10,
               id::text, pg_catalog.now()
        FROM selected
        ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
            execution_mode = 'backfill', priority = 10,
            status = 'pending', run_after = EXCLUDED.run_after, attempts = 0,
            worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
            last_error_code = NULL, completed_at = NULL,
            updated_at = pg_catalog.now()
        WHERE public.processing_jobs.status IN ('completed', 'failed')
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = public.processing_jobs.entry_id
                AND analysis.user_id = public.processing_jobs.user_id
          )
        RETURNING 1
    )
    SELECT
        (SELECT pg_catalog.count(*)::integer FROM selected),
        (SELECT pg_catalog.count(*)::integer FROM upserted),
        (SELECT created_at FROM selected ORDER BY created_at DESC, id DESC LIMIT 1),
        (SELECT id FROM selected ORDER BY created_at DESC, id DESC LIMIT 1)
    INTO selected_count, changed_count, last_created, last_id;

    IF selected_count = 0 THEN
        UPDATE public.processing_backfill_runs
        SET status = 'completed', completed_at = pg_catalog.now(),
            last_throttle_reason = NULL, last_checked_at = pg_catalog.now(),
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM public.entries AS entry
        JOIN public.processing_backfill_users AS cohort
          ON cohort.user_id = entry.user_id AND cohort.run_id = p_run_id
        WHERE (entry.created_at, entry.id) > (last_created, last_id)
          AND (entry.created_at, entry.id) <=
              (run.upper_bound_created_at, run.upper_bound_entry_id)
          AND entry.processing_status = 'completed'
          AND EXISTS (
              SELECT 1 FROM public.entry_classifications AS classification
              WHERE classification.entry_id = entry.id
                AND classification.user_id = entry.user_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM public.entry_analyses AS analysis
              WHERE analysis.entry_id = entry.id AND analysis.user_id = entry.user_id
          )
    ) INTO has_more;

    UPDATE public.processing_backfill_runs
    SET status = CASE WHEN has_more THEN 'running' ELSE 'completed' END,
        enqueued_count = enqueued_count + changed_count,
        cursor_created_at = last_created,
        cursor_entry_id = last_id,
        last_throttle_reason = NULL,
        last_checked_at = pg_catalog.now(),
        completed_at = CASE WHEN has_more THEN NULL ELSE pg_catalog.now() END,
        updated_at = pg_catalog.now()
    WHERE id = p_run_id;
    RETURN public.get_entry_processing_backfill_status(p_run_id);
END
$function$;

CREATE FUNCTION public.set_entry_processing_backfill_state(
    p_run_id uuid,
    p_action text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    run public.processing_backfill_runs%ROWTYPE;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_action NOT IN ('pause', 'resume')
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT * INTO run FROM public.processing_backfill_runs
    WHERE id = p_run_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'backfill run not found';
    END IF;
    IF run.status = 'completed' THEN
        RETURN public.get_entry_processing_backfill_status(p_run_id);
    END IF;
    IF p_action = 'pause' AND run.status IN ('planned', 'running') THEN
        UPDATE public.processing_backfill_runs
        SET status = 'paused', last_throttle_reason = NULL,
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
    ELSIF p_action = 'resume' AND run.status = 'paused' THEN
        UPDATE public.processing_backfill_runs
        SET status = 'running', last_throttle_reason = NULL,
            updated_at = pg_catalog.now()
        WHERE id = p_run_id;
    END IF;
    RETURN public.get_entry_processing_backfill_status(p_run_id);
END
$function$;

DROP FUNCTION public.enqueue_entry_processing_backfill(integer, timestamptz);

CREATE OR REPLACE FUNCTION public.retry_entry_processing_for_owner(
    p_user_id uuid,
    p_entry_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job_id uuid;
BEGIN
    IF auth.uid() IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM 1
    FROM public.entries
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed'
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN false;
    END IF;
    UPDATE public.processing_jobs
    SET status = 'pending', execution_mode = 'user', priority = 100,
        run_after = pg_catalog.now(), attempts = 0,
        worker_id = NULL, claim_token = NULL, heartbeat_at = NULL,
        last_error_code = NULL, completed_at = NULL
    WHERE user_id = p_user_id AND entry_id = p_entry_id
      AND job_type = 'entry_processing' AND source_version = p_entry_id::text
      AND status = 'failed'
    RETURNING id INTO job_id;
    IF job_id IS NULL THEN
        INSERT INTO public.processing_jobs (
            user_id, entry_id, job_type, execution_mode, priority, source_version
        ) VALUES (
            p_user_id, p_entry_id, 'entry_processing', 'user', 100, p_entry_id::text
        )
        ON CONFLICT (user_id, job_type, source_version) DO NOTHING
        RETURNING id INTO job_id;
    END IF;
    IF job_id IS NULL THEN
        RETURN false;
    END IF;
    UPDATE public.entries
    SET processing_status = 'pending', processing_token = NULL,
        processing_error_code = NULL, processing_started_at = NULL,
        completed_at = NULL
    WHERE id = p_entry_id AND user_id = p_user_id
      AND processing_status = 'failed';
    UPDATE public.past_entry_imports
    SET status = 'pending', attempts = 0, worker_id = NULL,
        processing_token = NULL, completed_processing_token = NULL,
        heartbeat_at = NULL, last_error_code = NULL, completed_at = NULL
    WHERE entry_id = p_entry_id AND user_id = p_user_id AND status = 'failed';
    RETURN true;
END
$function$;

-- Entry deletion can invalidate a published snapshot, but an authenticated RPC
-- must not choose a rollout cohort or shadow/publish mode. The cohort-aware
-- scheduler is the sole synthesis enqueuer after this migration.
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
    latest_source bigint;
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
        UPDATE public.reflection_user_state
        SET latest_accepted_source_version = latest_source,
            last_snapshot_source_version = LEAST(last_snapshot_source_version, latest_source),
            last_schedule_local_date = NULL,
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
    END IF;
    RETURN true;
END
$function$;

REVOKE ALL ON FUNCTION public.claim_processing_job(text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[])
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.complete_reflection_shadow(
    uuid, text, uuid, integer, integer, boolean
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.plan_entry_processing_backfill(
    uuid[], integer, integer, integer
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_entry_processing_backfill_status(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.run_entry_processing_backfill_batch(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.set_entry_processing_backfill_state(uuid, text)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.claim_processing_job(text) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[])
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.complete_reflection_shadow(
    uuid, text, uuid, integer, integer, boolean
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.plan_entry_processing_backfill(
    uuid[], integer, integer, integer
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_entry_processing_backfill_status(uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.run_entry_processing_backfill_batch(uuid)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.set_entry_processing_backfill_state(uuid, text)
    TO orion_worker;

-- P0-09C: worker-only queue observations and scheduler outcome counts.

DROP FUNCTION public.schedule_reflection_jobs(timestamptz, text, uuid[]);

CREATE FUNCTION public.schedule_reflection_jobs_observed(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    profile record;
    state public.reflection_user_state%ROWTYPE;
    local_date date;
    checked integer := 0;
    eligible integer := 0;
    enqueued integer := 0;
    changed integer;
    job_priority smallint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_now IS NULL
       OR p_execution_mode NOT IN ('shadow', 'publish')
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT pg_catalog.count(*)::integer INTO checked
    FROM public.user_profiles
    WHERE user_id = ANY(p_user_ids);
    job_priority := CASE p_execution_mode WHEN 'publish' THEN 80 ELSE 60 END;
    FOR profile IN
        SELECT user_id, timezone
        FROM public.user_profiles
        WHERE user_id = ANY(p_user_ids)
          AND (p_now AT TIME ZONE timezone)::time >= TIME '18:00:00'
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
            eligible := eligible + 1;
            INSERT INTO public.processing_jobs (
                user_id, entry_id, job_type, execution_mode, priority,
                source_version, run_after
            ) VALUES (
                profile.user_id, NULL, 'reflection_synthesis',
                p_execution_mode, job_priority,
                state.latest_accepted_source_version::text, p_now
            ) ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
                execution_mode = EXCLUDED.execution_mode,
                priority = EXCLUDED.priority,
                status = 'pending',
                run_after = EXCLUDED.run_after,
                attempts = 0,
                worker_id = NULL,
                claim_token = NULL,
                heartbeat_at = NULL,
                last_error_code = NULL,
                completed_at = NULL,
                updated_at = pg_catalog.now()
            WHERE public.processing_jobs.job_type = 'reflection_synthesis'
              AND public.processing_jobs.execution_mode = 'shadow'
              AND EXCLUDED.execution_mode = 'publish'
              AND public.processing_jobs.status IN ('pending', 'completed', 'failed')
              AND NOT EXISTS (
                  SELECT 1 FROM public.reflection_snapshots AS snapshot
                  WHERE snapshot.user_id = public.processing_jobs.user_id
                    AND snapshot.source_version = public.processing_jobs.source_version::bigint
              );
            GET DIAGNOSTICS changed = ROW_COUNT;
            enqueued := enqueued + changed;
        END IF;
    END LOOP;
    RETURN pg_catalog.jsonb_build_object(
        'checked', checked,
        'eligible', eligible,
        'enqueued', enqueued
    );
END
$function$;

CREATE FUNCTION public.schedule_reflection_jobs(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
    SELECT COALESCE(
        (public.schedule_reflection_jobs_observed(
            p_now, p_execution_mode, p_user_ids
        )->>'enqueued')::integer,
        0
    )
$function$;

CREATE FUNCTION public.get_processing_queue_observability()
RETURNS TABLE (
    job_type text,
    queue_depth bigint,
    oldest_pending_seconds bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ''
AS $function$
    SELECT requested.job_type,
        pg_catalog.count(queued.id)::bigint AS queue_depth,
        COALESCE(
            pg_catalog.floor(
                pg_catalog.date_part(
                    'epoch', pg_catalog.now() - pg_catalog.min(queued.created_at)
                )
            )::bigint,
            0
        ) AS oldest_pending_seconds
    FROM (
        VALUES ('entry_processing'::text), ('reflection_synthesis'::text)
    ) AS requested(job_type)
    LEFT JOIN public.processing_jobs AS queued
      ON queued.job_type = requested.job_type
     AND queued.status = 'pending'
    WHERE pg_catalog.current_setting('role', true) = 'orion_worker'
    GROUP BY requested.job_type
    ORDER BY requested.job_type
$function$;

REVOKE ALL ON FUNCTION public.schedule_reflection_jobs_observed(
    timestamptz, text, uuid[]
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.schedule_reflection_jobs(
    timestamptz, text, uuid[]
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_processing_queue_observability()
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs_observed(
    timestamptz, text, uuid[]
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.schedule_reflection_jobs(
    timestamptz, text, uuid[]
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_processing_queue_observability()
    TO orion_worker;

-- Qualify the selected snapshot variable used by the aggregate Reflection API RPC.
--
-- PL/pgSQL resolves an unqualified `snapshot_id` in SQL statements ambiguously when
-- both the function variable and a queried table expose that name. Rename only the
-- function variable while preserving the existing SECURITY DEFINER body and ACLs.

DO $migration$
DECLARE
    function_definition text;
    updated_definition text;
BEGIN
    SELECT pg_catalog.pg_get_functiondef(
        'public.get_reflections_for_owner(uuid, integer)'::pg_catalog.regprocedure
    )
    INTO function_definition;

    updated_definition := pg_catalog.replace(
        function_definition,
        E'\n    snapshot_id uuid;\n',
        E'\n    selected_snapshot_id uuid;\n'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'INTO snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload',
        'INTO selected_snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'IF snapshot_id IS NOT NULL THEN',
        'IF selected_snapshot_id IS NOT NULL THEN'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'insight.snapshot_id = snapshot_id',
        'insight.snapshot_id = selected_snapshot_id'
    );
    updated_definition := pg_catalog.replace(
        updated_definition,
        'feedback.snapshot_id = snapshot_id',
        'feedback.snapshot_id = selected_snapshot_id'
    );

    IF updated_definition = function_definition
       OR pg_catalog.strpos(updated_definition, 'selected_snapshot_id uuid;') = 0
       OR pg_catalog.strpos(updated_definition, 'insight.snapshot_id = snapshot_id') > 0
       OR pg_catalog.strpos(updated_definition, 'feedback.snapshot_id = snapshot_id') > 0
    THEN
        RAISE EXCEPTION 'get_reflections_for_owner definition did not match expected shape';
    END IF;

    EXECUTE updated_definition;
END
$migration$;

-- Allow an authenticated Reflection GET to expedite an existing pending
-- synthesis job without resetting completed, running, or failed work.

CREATE OR REPLACE FUNCTION public.enqueue_processing_job(
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
    mode text;
    job_priority smallint;
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
    mode := CASE p_job_type WHEN 'entry_processing' THEN 'user' ELSE 'publish' END;
    job_priority := CASE p_job_type WHEN 'entry_processing' THEN 100 ELSE 80 END;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, p_job_type, mode, job_priority,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
        source_version = EXCLUDED.source_version,
        run_after = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
            THEN pg_catalog.least(public.processing_jobs.run_after, EXCLUDED.run_after)
            ELSE public.processing_jobs.run_after
        END,
        updated_at = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
             AND EXCLUDED.run_after < public.processing_jobs.run_after
            THEN pg_catalog.now()
            ELSE public.processing_jobs.updated_at
        END
    RETURNING id INTO result;
    RETURN result;
END
$function$;

-- PostgreSQL implements LEAST as a conditional expression, not a function in
-- pg_catalog. The 0014 definition created successfully but failed at runtime
-- whenever the reflection read path attempted to enqueue or expedite a job.

CREATE OR REPLACE FUNCTION public.enqueue_processing_job(
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
    mode text;
    job_priority smallint;
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
    mode := CASE p_job_type WHEN 'entry_processing' THEN 'user' ELSE 'publish' END;
    job_priority := CASE p_job_type WHEN 'entry_processing' THEN 100 ELSE 80 END;
    INSERT INTO public.processing_jobs (
        user_id, entry_id, job_type, execution_mode, priority,
        source_version, run_after
    ) VALUES (
        p_user_id, p_entry_id, p_job_type, mode, job_priority,
        p_source_version, p_run_after
    )
    ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
        source_version = EXCLUDED.source_version,
        run_after = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
            THEN LEAST(public.processing_jobs.run_after, EXCLUDED.run_after)
            ELSE public.processing_jobs.run_after
        END,
        updated_at = CASE
            WHEN public.processing_jobs.job_type = 'reflection_synthesis'
             AND public.processing_jobs.status = 'pending'
             AND EXCLUDED.run_after < public.processing_jobs.run_after
            THEN pg_catalog.now()
            ELSE public.processing_jobs.updated_at
        END
    RETURNING id INTO result;
    RETURN result;
END
$function$;

CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

GRANT USAGE ON SCHEMA extensions TO authenticated, orion_app, orion_worker;

ALTER TABLE public.entry_signals
    ADD COLUMN embedding extensions.vector(1536),
    ADD COLUMN embedding_model text,
    ADD COLUMN embedded_at timestamptz,
    ADD CONSTRAINT entry_signals_embedding_metadata_check CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND embedded_at IS NULL)
        OR (
            embedding IS NOT NULL
            AND embedding_model ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
            AND embedded_at IS NOT NULL
        )
    );

CREATE FUNCTION public.store_entry_signal_embeddings(
    p_job_id uuid,
    p_claim_token uuid,
    p_embeddings jsonb,
    p_model_id text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    item jsonb;
    signal_id uuid;
    vector_value extensions.vector;
    expected_count integer;
    updated_count integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_embeddings) <> 'array'
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;

    IF NOT FOUND
       OR job.job_type <> 'entry_processing'
       OR job.entry_id IS NULL
       OR job.status <> 'completed'
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    SELECT pg_catalog.count(*)::integer INTO expected_count
    FROM public.entry_signals
    WHERE user_id = job.user_id AND entry_id = job.entry_id;

    IF expected_count <> pg_catalog.jsonb_array_length(p_embeddings)
       OR (
           SELECT pg_catalog.count(DISTINCT value ->> 'signal_id')
           FROM pg_catalog.jsonb_array_elements(p_embeddings)
       ) <> expected_count
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embeddings are incomplete';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_embeddings)
    LOOP
        IF pg_catalog.jsonb_typeof(item) <> 'object'
           OR (
               SELECT pg_catalog.count(*)
               FROM pg_catalog.jsonb_object_keys(item)
           ) <> 2
           OR NOT item ?& ARRAY['signal_id', 'values']
           OR pg_catalog.jsonb_typeof(item -> 'signal_id') <> 'string'
           OR pg_catalog.jsonb_typeof(item -> 'values') <> 'array'
           OR pg_catalog.jsonb_array_length(item -> 'values') <> 1536
        THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embedding is invalid';
        END IF;

        signal_id := (item ->> 'signal_id')::uuid;
        vector_value := (item -> 'values')::text::extensions.vector;

        UPDATE public.entry_signals
        SET embedding = vector_value,
            embedding_model = p_model_id,
            embedded_at = pg_catalog.now()
        WHERE id = signal_id
          AND user_id = job.user_id
          AND entry_id = job.entry_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'signal embedding is invalid';
        END IF;
        updated_count := updated_count + 1;
    END LOOP;

    RETURN updated_count;
END
$function$;

REVOKE ALL ON FUNCTION public.store_entry_signal_embeddings(
    uuid, uuid, jsonb, text
) FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.store_entry_signal_embeddings(
    uuid, uuid, jsonb, text
) TO orion_worker;

-- Centralize incremental recalculation eligibility so scheduler and aggregate
-- reads cannot disagree or trigger synthesis after only one recent entry.

CREATE FUNCTION public.is_reflection_recalculation_eligible(
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
      AND analysis.source_version > state.last_snapshot_source_version;

    IF pending_valid_entries = 0 THEN
        RETURN false;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted'
          AND analysis.source_version > state.last_snapshot_source_version
    ) INTO has_pending_signal;
    IF NOT has_pending_signal THEN
        RETURN false;
    END IF;

    -- A first snapshot still requires the global 3-entry, 2-date, 200-word
    -- basis. Incremental word/age triggers apply only after that first result.
    IF state.last_successful_snapshot_id IS NULL
       OR state.last_snapshot_source_version = 0
    THEN
        SELECT pg_catalog.max(entry.entry_date)
        INTO current_end
        FROM public.entry_analyses AS analysis
        JOIN public.entries AS entry
          ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
        WHERE analysis.user_id = p_user_id
          AND analysis.eligibility = 'accepted';
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
          AND entry.entry_date BETWEEN current_start AND current_end;
        RETURN basis_valid_entries >= 3
           AND basis_distinct_dates >= 2
           AND basis_reflective_words >= 200;
    END IF;

    RETURN pending_valid_entries >= 3
       OR pending_reflective_words >= 500
       OR (
           pending_valid_entries >= 1
           AND oldest_pending_valid_entry_at <= p_now - INTERVAL '3 days'
       );
END
$function$;

CREATE FUNCTION public.request_reflection_synthesis_if_eligible(
    p_user_id uuid,
    p_now timestamptz DEFAULT pg_catalog.now()
)
RETURNS TABLE (requested_job_id uuid, requested_source_version bigint)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    state public.reflection_user_state%ROWTYPE;
    existing_job public.processing_jobs%ROWTYPE;
    target_source bigint;
    result uuid;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_now IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('orion-reflection:' || p_user_id::text, 0)
    );
    SELECT * INTO state
    FROM public.reflection_user_state
    WHERE user_id = p_user_id
    FOR UPDATE;
    IF NOT FOUND
       OR NOT public.is_reflection_recalculation_eligible(p_user_id, p_now)
    THEN
        RETURN;
    END IF;

    SELECT * INTO existing_job
    FROM public.processing_jobs
    WHERE user_id = p_user_id AND job_type = 'reflection_synthesis'
    ORDER BY created_at DESC, id DESC
    LIMIT 1;
    IF FOUND THEN
        IF existing_job.status = 'running' THEN
            RETURN;
        END IF;
        IF existing_job.status = 'pending' THEN
            target_source := existing_job.source_version::bigint;
            IF target_source > state.latest_accepted_source_version THEN
                RETURN;
            END IF;
            result := public.enqueue_processing_job(
                p_user_id,
                NULL,
                'reflection_synthesis',
                target_source::text,
                p_now
            );
            RETURN QUERY SELECT result, target_source;
            RETURN;
        END IF;
        IF existing_job.source_version::bigint >= state.latest_accepted_source_version THEN
            RETURN;
        END IF;
    END IF;

    target_source := state.latest_accepted_source_version;
    result := public.enqueue_processing_job(
        p_user_id,
        NULL,
        'reflection_synthesis',
        target_source::text,
        p_now
    );
    RETURN QUERY SELECT result, target_source;
END
$function$;

CREATE OR REPLACE FUNCTION public.schedule_reflection_jobs_observed(
    p_now timestamptz,
    p_execution_mode text,
    p_user_ids uuid[]
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    profile record;
    state public.reflection_user_state%ROWTYPE;
    local_date date;
    checked integer := 0;
    eligible integer := 0;
    enqueued integer := 0;
    changed integer;
    job_priority smallint;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_now IS NULL
       OR p_execution_mode NOT IN ('shadow', 'publish')
       OR p_user_ids IS NULL
       OR pg_catalog.cardinality(p_user_ids) NOT BETWEEN 1 AND 1000
       OR pg_catalog.array_position(p_user_ids, NULL) IS NOT NULL
       OR (
           SELECT pg_catalog.count(DISTINCT requested.user_id)
           FROM pg_catalog.unnest(p_user_ids) AS requested(user_id)
       ) <> pg_catalog.cardinality(p_user_ids)
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    SELECT pg_catalog.count(*)::integer INTO checked
    FROM public.user_profiles
    WHERE user_id = ANY(p_user_ids);
    job_priority := CASE p_execution_mode WHEN 'publish' THEN 80 ELSE 60 END;
    FOR profile IN
        SELECT user_id, timezone
        FROM public.user_profiles
        WHERE user_id = ANY(p_user_ids)
          AND (p_now AT TIME ZONE timezone)::time >= TIME '18:00:00'
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
        IF public.is_reflection_recalculation_eligible(profile.user_id, p_now)
        THEN
            eligible := eligible + 1;
            INSERT INTO public.processing_jobs (
                user_id, entry_id, job_type, execution_mode, priority,
                source_version, run_after
            ) VALUES (
                profile.user_id, NULL, 'reflection_synthesis',
                p_execution_mode, job_priority,
                state.latest_accepted_source_version::text, p_now
            ) ON CONFLICT (user_id, job_type, source_version) DO UPDATE SET
                execution_mode = EXCLUDED.execution_mode,
                priority = EXCLUDED.priority,
                status = 'pending',
                run_after = EXCLUDED.run_after,
                attempts = 0,
                worker_id = NULL,
                claim_token = NULL,
                heartbeat_at = NULL,
                last_error_code = NULL,
                completed_at = NULL,
                updated_at = pg_catalog.now()
            WHERE public.processing_jobs.job_type = 'reflection_synthesis'
              AND public.processing_jobs.execution_mode = 'shadow'
              AND EXCLUDED.execution_mode = 'publish'
              AND public.processing_jobs.status IN ('pending', 'completed', 'failed')
              AND NOT EXISTS (
                  SELECT 1 FROM public.reflection_snapshots AS snapshot
                  WHERE snapshot.user_id = public.processing_jobs.user_id
                    AND snapshot.source_version = public.processing_jobs.source_version::bigint
              );
            GET DIAGNOSTICS changed = ROW_COUNT;
            enqueued := enqueued + changed;
        END IF;
    END LOOP;
    RETURN pg_catalog.jsonb_build_object(
        'checked', checked,
        'eligible', eligible,
        'enqueued', enqueued
    );
END
$function$;

REVOKE ALL ON FUNCTION public.is_reflection_recalculation_eligible(uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.request_reflection_synthesis_if_eligible(uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.is_reflection_recalculation_eligible(uuid, timestamptz)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.request_reflection_synthesis_if_eligible(uuid, timestamptz)
    TO orion_worker;

-- Worker-only semantic signal retrieval, bounded historical embedding backfill,
-- and exact snapshot evidence-entry counts for the Reflection API.

ALTER TABLE public.entry_signals
    ADD COLUMN embedding_backfill_token uuid,
    ADD COLUMN embedding_backfill_claimed_at timestamptz,
    ADD CONSTRAINT entry_signals_embedding_backfill_claim_check CHECK (
        (embedding_backfill_token IS NULL AND embedding_backfill_claimed_at IS NULL)
        OR (embedding_backfill_token IS NOT NULL AND embedding_backfill_claimed_at IS NOT NULL)
    );

CREATE INDEX entry_signals_embedding_backfill_claim_idx
    ON public.entry_signals (embedding_backfill_claimed_at, id)
    WHERE embedding IS NULL;

CREATE FUNCTION public.find_signal_semantic_neighbors(
    p_user_id uuid,
    p_anchor_signal_ids uuid[],
    p_source_version bigint,
    p_model_id text,
    p_top_k integer DEFAULT 8,
    p_similarity_threshold numeric DEFAULT 0.90
)
RETURNS TABLE (
    anchor_signal_id uuid,
    neighbor_signal_id uuid,
    cosine_distance double precision,
    similarity double precision
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    latest_date date;
    basis_start date;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_user_id IS NULL
       OR p_anchor_signal_ids IS NULL
       OR pg_catalog.cardinality(p_anchor_signal_ids) < 1
       OR pg_catalog.cardinality(p_anchor_signal_ids) > 4096
       OR EXISTS (
           SELECT 1 FROM pg_catalog.unnest(p_anchor_signal_ids) AS requested(id)
           WHERE requested.id IS NULL
       )
       OR (
           SELECT pg_catalog.count(DISTINCT requested.id)
           FROM pg_catalog.unnest(p_anchor_signal_ids) AS requested(id)
       ) <> pg_catalog.cardinality(p_anchor_signal_ids)
       OR p_source_version IS NULL OR p_source_version < 1
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
       OR p_top_k IS NULL OR p_top_k < 1 OR p_top_k > 50
       OR p_similarity_threshold IS NULL
       OR p_similarity_threshold < 0 OR p_similarity_threshold > 1
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

    IF latest_date IS NULL THEN
        RETURN;
    END IF;
    basis_start := latest_date - 89;

    RETURN QUERY
    WITH anchors AS (
        SELECT signal.id, signal.entry_id, signal.embedding
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        JOIN public.entries AS entry
          ON entry.id = signal.entry_id AND entry.user_id = signal.user_id
        WHERE signal.user_id = p_user_id
          AND signal.id = ANY(p_anchor_signal_ids)
          AND signal.embedding IS NOT NULL
          AND signal.embedding_model = p_model_id
          AND extensions.vector_dims(signal.embedding) = 1536
          AND analysis.eligibility = 'accepted'
          AND analysis.source_version <= p_source_version
          AND entry.entry_date BETWEEN basis_start AND latest_date
    ), ranked AS (
        SELECT anchor.id AS anchor_id,
               neighbor.id AS neighbor_id,
               (anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding)::double precision AS distance,
               pg_catalog.row_number() OVER (
                   PARTITION BY anchor.id
                   ORDER BY anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding,
                            neighbor.occurred_on,
                            neighbor.entry_id,
                            neighbor.id
               ) AS neighbor_rank
        FROM anchors AS anchor
        JOIN public.entry_signals AS neighbor
          ON neighbor.user_id = p_user_id
         AND neighbor.id <> anchor.id
         AND neighbor.entry_id <> anchor.entry_id
         AND neighbor.embedding IS NOT NULL
         AND neighbor.embedding_model = p_model_id
         AND extensions.vector_dims(neighbor.embedding) = 1536
        JOIN public.entry_analyses AS neighbor_analysis
          ON neighbor_analysis.id = neighbor.analysis_id
         AND neighbor_analysis.user_id = neighbor.user_id
         AND neighbor_analysis.entry_id = neighbor.entry_id
        JOIN public.entries AS neighbor_entry
          ON neighbor_entry.id = neighbor.entry_id
         AND neighbor_entry.user_id = neighbor.user_id
        WHERE neighbor_analysis.eligibility = 'accepted'
          AND neighbor_analysis.source_version <= p_source_version
          AND neighbor_entry.entry_date BETWEEN basis_start AND latest_date
          AND 1 - (anchor.embedding OPERATOR(extensions.<=>) neighbor.embedding) >= p_similarity_threshold
    )
    SELECT ranked.anchor_id,
           ranked.neighbor_id,
           ranked.distance,
           1 - ranked.distance
    FROM ranked
    WHERE ranked.neighbor_rank <= p_top_k
    ORDER BY ranked.anchor_id, ranked.neighbor_rank, ranked.neighbor_id;
END
$function$;

CREATE FUNCTION public.get_signal_embedding_backfill_status(p_model_id text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    missing_count integer;
    claimable_count integer;
    active_claim_count integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT pg_catalog.count(*)::integer,
           pg_catalog.count(*) FILTER (
               WHERE signal.embedding_backfill_token IS NULL
                  OR signal.embedding_backfill_claimed_at < pg_catalog.now() - INTERVAL '15 minutes'
           )::integer,
           pg_catalog.count(*) FILTER (
               WHERE signal.embedding_backfill_token IS NOT NULL
                 AND signal.embedding_backfill_claimed_at >= pg_catalog.now() - INTERVAL '15 minutes'
           )::integer
    INTO missing_count, claimable_count, active_claim_count
    FROM public.entry_signals AS signal
    JOIN public.entry_analyses AS analysis
      ON analysis.id = signal.analysis_id
     AND analysis.user_id = signal.user_id
     AND analysis.entry_id = signal.entry_id
    WHERE signal.embedding IS NULL
      AND analysis.eligibility = 'accepted';

    RETURN pg_catalog.jsonb_build_object(
        'model_id', p_model_id,
        'missing_signal_count', missing_count,
        'claimable_signal_count', claimable_count,
        'active_claim_count', active_claim_count
    );
END
$function$;

CREATE FUNCTION public.claim_signal_embedding_backfill_batch(
    p_batch_size integer,
    p_model_id text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    batch_token uuid := gen_random_uuid();
    items jsonb;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_size IS NULL OR p_batch_size < 1 OR p_batch_size > 128
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    WITH claimable AS (
        SELECT signal.id
        FROM public.entry_signals AS signal
        JOIN public.entry_analyses AS analysis
          ON analysis.id = signal.analysis_id
         AND analysis.user_id = signal.user_id
         AND analysis.entry_id = signal.entry_id
        WHERE signal.embedding IS NULL
          AND analysis.eligibility = 'accepted'
          AND (
              signal.embedding_backfill_token IS NULL
              OR signal.embedding_backfill_claimed_at < pg_catalog.now() - INTERVAL '15 minutes'
          )
        ORDER BY analysis.source_version, signal.entry_id, signal.source_start, signal.id
        FOR UPDATE OF signal SKIP LOCKED
        LIMIT p_batch_size
    ), claimed AS (
        UPDATE public.entry_signals AS signal
        SET embedding_backfill_token = batch_token,
            embedding_backfill_claimed_at = pg_catalog.now()
        FROM claimable
        WHERE signal.id = claimable.id AND signal.embedding IS NULL
        RETURNING signal.id, signal.user_id, signal.payload_envelope,
                  signal.signal_type, signal.themes, signal.need_tags, signal.loop_role
    )
    SELECT COALESCE(pg_catalog.jsonb_agg(
        pg_catalog.jsonb_build_object(
            'signal_id', claimed.id,
            'user_id', claimed.user_id,
            'payload_envelope', claimed.payload_envelope,
            'signal_type', claimed.signal_type,
            'themes', claimed.themes,
            'need_tags', claimed.need_tags,
            'loop_role', claimed.loop_role
        ) ORDER BY claimed.id
    ), '[]'::jsonb)
    INTO items
    FROM claimed;

    RETURN pg_catalog.jsonb_build_object(
        'batch_token', batch_token,
        'model_id', p_model_id,
        'items', items
    );
END
$function$;

CREATE FUNCTION public.store_signal_embedding_backfill_batch(
    p_batch_token uuid,
    p_embeddings jsonb,
    p_model_id text
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    item jsonb;
    signal_id uuid;
    vector_value extensions.vector;
    expected_count integer;
    stored_count integer;
    updated_count integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_token IS NULL
       OR p_embeddings IS NULL
       OR pg_catalog.jsonb_typeof(p_embeddings) <> 'array'
       OR p_model_id IS NULL
       OR p_model_id !~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$'
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    PERFORM 1
    FROM public.entry_signals
    WHERE embedding_backfill_token = p_batch_token
    ORDER BY id
    FOR UPDATE;

    SELECT pg_catalog.count(*)::integer,
           pg_catalog.count(*) FILTER (WHERE embedding IS NOT NULL)::integer
    INTO expected_count, stored_count
    FROM public.entry_signals
    WHERE embedding_backfill_token = p_batch_token;

    IF expected_count < 1
       OR expected_count <> pg_catalog.jsonb_array_length(p_embeddings)
       OR (
           SELECT pg_catalog.count(DISTINCT value ->> 'signal_id')
           FROM pg_catalog.jsonb_array_elements(p_embeddings)
       ) <> expected_count
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
           WHERE pg_catalog.jsonb_typeof(supplied.value) <> 'object'
              OR (SELECT pg_catalog.count(*)
                  FROM pg_catalog.jsonb_object_keys(supplied.value)) <> 2
              OR NOT supplied.value ?& ARRAY['signal_id', 'values']
              OR pg_catalog.jsonb_typeof(supplied.value -> 'signal_id') <> 'string'
              OR pg_catalog.jsonb_typeof(supplied.value -> 'values') <> 'array'
              OR pg_catalog.jsonb_array_length(supplied.value -> 'values') <> 1536
       )
    THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embeddings are incomplete';
    END IF;

    IF stored_count = expected_count THEN
        IF EXISTS (
            SELECT 1
            FROM public.entry_signals AS signal
            WHERE signal.embedding_backfill_token = p_batch_token
              AND (
                  signal.embedding_model IS DISTINCT FROM p_model_id
                  OR extensions.vector_dims(signal.embedding) <> 1536
              )
        ) OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
            WHERE NOT EXISTS (
                SELECT 1
                FROM public.entry_signals AS signal
                WHERE signal.embedding_backfill_token = p_batch_token
                  AND signal.id = (supplied.value ->> 'signal_id')::uuid
            )
        ) OR EXISTS (
            SELECT 1
            FROM pg_catalog.jsonb_array_elements(p_embeddings) AS supplied(value)
            JOIN public.entry_signals AS signal
              ON signal.embedding_backfill_token = p_batch_token
             AND signal.id = (supplied.value ->> 'signal_id')::uuid
            WHERE signal.embedding::text IS DISTINCT FROM
                  ((supplied.value -> 'values')::text::extensions.vector)::text
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding retry is invalid';
        END IF;
        RETURN expected_count;
    ELSIF stored_count > 0 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding state is invalid';
    END IF;

    FOR item IN SELECT value FROM pg_catalog.jsonb_array_elements(p_embeddings)
    LOOP
        signal_id := (item ->> 'signal_id')::uuid;
        vector_value := (item -> 'values')::text::extensions.vector;
        UPDATE public.entry_signals
        SET embedding = vector_value,
            embedding_model = p_model_id,
            embedded_at = pg_catalog.now()
        WHERE id = signal_id
          AND embedding IS NULL
          AND embedding_backfill_token = p_batch_token;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'backfill embedding is invalid';
        END IF;
        updated_count := updated_count + 1;
    END LOOP;
    RETURN updated_count;
END
$function$;

CREATE FUNCTION public.release_signal_embedding_backfill_batch(p_batch_token uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    released integer;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR p_batch_token IS NULL
    THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;
    UPDATE public.entry_signals
    SET embedding_backfill_token = NULL,
        embedding_backfill_claimed_at = NULL
    WHERE embedding IS NULL AND embedding_backfill_token = p_batch_token;
    GET DIAGNOSTICS released = ROW_COUNT;
    RETURN released;
END
$function$;

CREATE OR REPLACE FUNCTION public.get_reflections_for_owner(
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
    selected_snapshot_id uuid;
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

    SELECT profile.timezone INTO owner_timezone
    FROM public.user_profiles AS profile WHERE profile.user_id = p_user_id;
    IF owner_timezone IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'profile not found';
    END IF;

    SELECT pg_catalog.jsonb_build_object(
        'latest_accepted_source_version', state.latest_accepted_source_version,
        'last_snapshot_source_version', state.last_snapshot_source_version,
        'last_processing_error_code', state.last_processing_error_code
    ) INTO state_payload
    FROM public.reflection_user_state AS state WHERE state.user_id = p_user_id;

    SELECT pg_catalog.jsonb_build_object(
        'status', job.status, 'source_version', job.source_version, 'created_at', job.created_at
    ) INTO job_payload
    FROM public.processing_jobs AS job
    WHERE job.user_id = p_user_id AND job.job_type = 'reflection_synthesis'
    ORDER BY job.created_at DESC, job.id DESC LIMIT 1;

    SELECT snapshot.id, snapshot.basis_start, snapshot.basis_end, snapshot.source_version,
           pg_catalog.jsonb_build_object(
               'id', snapshot.id, 'version', snapshot.version,
               'source_version', snapshot.source_version,
               'basis_start', snapshot.basis_start, 'basis_end', snapshot.basis_end,
               'valid_entry_count', snapshot.valid_entry_count,
               'excluded_entry_count', snapshot.excluded_entry_count,
               'distinct_entry_dates', snapshot.distinct_entry_dates,
               'reflective_word_count', snapshot.reflective_word_count,
               'status', snapshot.status, 'created_at', snapshot.created_at,
               'excluded_reasons', COALESCE((
                   SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
                   FROM (
                       SELECT analysis.entry_kind, pg_catalog.count(*)::integer AS total
                       FROM public.entry_analyses AS analysis
                       JOIN public.entries AS entry
                         ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
                       WHERE analysis.user_id = p_user_id
                         AND analysis.eligibility <> 'accepted'
                         AND analysis.source_version <= snapshot.source_version
                         AND entry.entry_date BETWEEN snapshot.basis_start AND snapshot.basis_end
                       GROUP BY analysis.entry_kind ORDER BY analysis.entry_kind
                   ) AS summary
               ), '{}'::jsonb)
           )
    INTO selected_snapshot_id, snapshot_start, snapshot_end, snapshot_source, snapshot_payload
    FROM public.reflection_snapshots AS snapshot
    LEFT JOIN public.reflection_user_state AS state ON state.user_id = snapshot.user_id
    WHERE snapshot.user_id = p_user_id
    ORDER BY (snapshot.id = state.last_successful_snapshot_id) DESC,
             snapshot.version DESC, snapshot.id DESC LIMIT 1;

    SELECT COALESCE(pg_catalog.max(entry.entry_date),
                    (pg_catalog.now() AT TIME ZONE owner_timezone)::date)
    INTO current_end
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id;
    current_start := current_end - 89;

    SELECT pg_catalog.jsonb_build_object(
        'basis_start', current_start, 'basis_end', current_end,
        'valid_entry_count', pg_catalog.count(*) FILTER (WHERE analysis.eligibility = 'accepted')::integer,
        'excluded_entry_count', pg_catalog.count(*) FILTER (WHERE analysis.eligibility <> 'accepted')::integer,
        'distinct_entry_dates', pg_catalog.count(DISTINCT entry.entry_date)::integer,
        'reflective_word_count', COALESCE(pg_catalog.sum(analysis.reflective_word_count)
            FILTER (WHERE analysis.eligibility = 'accepted'), 0)::integer,
        'excluded_reasons', COALESCE((
            SELECT pg_catalog.jsonb_object_agg(summary.entry_kind, summary.total)
            FROM (
                SELECT excluded.entry_kind, pg_catalog.count(*)::integer AS total
                FROM public.entry_analyses AS excluded
                JOIN public.entries AS excluded_entry
                  ON excluded_entry.id = excluded.entry_id AND excluded_entry.user_id = excluded.user_id
                WHERE excluded.user_id = p_user_id
                  AND excluded.eligibility <> 'accepted'
                  AND excluded_entry.entry_date BETWEEN current_start AND current_end
                GROUP BY excluded.entry_kind ORDER BY excluded.entry_kind
            ) AS summary
        ), '{}'::jsonb)
    ) INTO current_basis
    FROM public.entry_analyses AS analysis
    JOIN public.entries AS entry
      ON entry.id = analysis.entry_id AND entry.user_id = analysis.user_id
    WHERE analysis.user_id = p_user_id
      AND entry.entry_date BETWEEN current_start AND current_end;

    IF selected_snapshot_id IS NOT NULL THEN
        WITH evidence_counts AS (
            SELECT evidence.insight_id,
                   pg_catalog.count(DISTINCT evidence.entry_id)::integer AS entry_count
            FROM public.reflection_snapshot_evidence AS evidence
            JOIN public.reflection_snapshot_insights AS counted_insight
              ON counted_insight.id = evidence.insight_id
             AND counted_insight.user_id = evidence.user_id
            WHERE evidence.user_id = p_user_id
              AND evidence.evidence_role = 'supporting'
              AND counted_insight.snapshot_id = selected_snapshot_id
            GROUP BY evidence.insight_id
        )
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_strip_nulls(pg_catalog.jsonb_build_object(
                'id', insight.id, 'pattern_type', insight.pattern_type,
                'ordinal', insight.ordinal, 'status', insight.status,
                'reason_code', insight.reason_code,
                'payload_envelope', insight.payload_envelope,
                'confidence_label', insight.confidence_label, 'score', insight.score,
                'evidence_entry_count', CASE WHEN insight.status = 'available'
                    THEN COALESCE(evidence_counts.entry_count, 0) END
            )) ORDER BY insight.pattern_type, insight.ordinal
        ), '[]'::jsonb) INTO insight_payload
        FROM public.reflection_snapshot_insights AS insight
        LEFT JOIN evidence_counts ON evidence_counts.insight_id = insight.id
        WHERE insight.user_id = p_user_id
          AND insight.snapshot_id = selected_snapshot_id;

        WITH ranked AS (
            SELECT evidence.*,
                   pg_catalog.row_number() OVER (
                       PARTITION BY evidence.insight_id
                       ORDER BY CASE evidence.evidence_role WHEN 'supporting' THEN 0 ELSE 1 END,
                                evidence.ordinal, evidence.signal_id
                   ) AS evidence_rank
            FROM public.reflection_snapshot_evidence AS evidence
            JOIN public.reflection_snapshot_insights AS insight
              ON insight.id = evidence.insight_id AND insight.user_id = evidence.user_id
            WHERE evidence.user_id = p_user_id
              AND insight.snapshot_id = selected_snapshot_id
        )
        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', ranked.insight_id, 'signal_id', ranked.signal_id,
                'entry_id', ranked.entry_id, 'evidence_role', ranked.evidence_role,
                'ordinal', ranked.ordinal, 'source_start', ranked.source_start,
                'source_end', ranked.source_end, 'entry_date', entry.entry_date,
                'input_type', entry.input_type,
                'entry_content_envelope', entry.content_envelope,
                'signal_payload_envelope', signal.payload_envelope,
                'themes', signal.themes
            ) ORDER BY ranked.insight_id, ranked.evidence_rank
        ), '[]'::jsonb) INTO evidence_payload
        FROM ranked
        JOIN public.entry_signals AS signal
          ON signal.id = ranked.signal_id AND signal.user_id = ranked.user_id
        JOIN public.entries AS entry
          ON entry.id = ranked.entry_id AND entry.user_id = ranked.user_id
        WHERE ranked.evidence_rank <= p_evidence_limit;

        SELECT COALESCE(pg_catalog.jsonb_agg(
            pg_catalog.jsonb_build_object(
                'insight_id', feedback.insight_id, 'response', feedback.response,
                'updated_at', feedback.updated_at
            ) ORDER BY feedback.insight_id
        ), '[]'::jsonb) INTO feedback_payload
        FROM public.reflection_feedback AS feedback
        WHERE feedback.user_id = p_user_id
          AND feedback.snapshot_id = selected_snapshot_id;
    END IF;

    RETURN pg_catalog.jsonb_build_object(
        'state', state_payload, 'job', job_payload, 'snapshot', snapshot_payload,
        'current_basis', current_basis, 'insights', insight_payload,
        'evidence', evidence_payload, 'feedback', feedback_payload
    );
END
$function$;

REVOKE ALL ON FUNCTION public.find_signal_semantic_neighbors(
    uuid, uuid[], bigint, text, integer, numeric
) FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.get_signal_embedding_backfill_status(text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.claim_signal_embedding_backfill_batch(integer, text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.store_signal_embedding_backfill_batch(uuid, jsonb, text)
    FROM PUBLIC, anon, authenticated, orion_app;
REVOKE ALL ON FUNCTION public.release_signal_embedding_backfill_batch(uuid)
    FROM PUBLIC, anon, authenticated, orion_app;

GRANT EXECUTE ON FUNCTION public.find_signal_semantic_neighbors(
    uuid, uuid[], bigint, text, integer, numeric
) TO orion_worker;
GRANT EXECUTE ON FUNCTION public.get_signal_embedding_backfill_status(text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.claim_signal_embedding_backfill_batch(integer, text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.store_signal_embedding_backfill_batch(uuid, jsonb, text)
    TO orion_worker;
GRANT EXECUTE ON FUNCTION public.release_signal_embedding_backfill_batch(uuid)
    TO orion_worker;

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

-- Claim-bound Entry Insight Review materialization.
-- Accepted signal rows, encrypted Review rows, and embeddings are applied by
-- the worker in one transaction. Review feedback is never changed on replay.

ALTER TABLE public.entry_signals
    DROP CONSTRAINT entry_signals_type_check;
ALTER TABLE public.entry_signals
    ADD CONSTRAINT entry_signals_type_check CHECK (signal_type IN (
        'event', 'emotion', 'energy_gain', 'energy_loss', 'self_knowledge',
        'desire', 'explicit_preference', 'need', 'avoidance', 'belief',
        'self_statement', 'action', 'outcome', 'conflict',
        'protective_strategy', 'realization', 'causal_relationship'
    ));

DROP POLICY review_items_insert_worker ON public.review_items;
REVOKE INSERT ON public.review_items FROM orion_worker;
REVOKE EXECUTE ON FUNCTION public.is_valid_encrypted_envelope_v1(jsonb)
    FROM orion_worker;

CREATE FUNCTION public.materialize_entry_review_items(
    p_job_id uuid,
    p_claim_token uuid,
    p_signals jsonb
)
RETURNS TABLE (
    analysis_accepted boolean,
    review_item_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $function$
DECLARE
    job public.processing_jobs%ROWTYPE;
    analysis public.entry_analyses%ROWTYPE;
    entry_local_date date;
    persisted_signal public.entry_signals%ROWTYPE;
    supplied_signal jsonb;
    review_item jsonb;
    expected_review_items integer := 0;
    persisted_review_items integer := 0;
BEGIN
    IF pg_catalog.current_setting('role', true) IS DISTINCT FROM 'orion_worker'
       OR pg_catalog.jsonb_typeof(p_signals) <> 'array'
       OR EXISTS (
           SELECT 1
           FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
           WHERE pg_catalog.jsonb_typeof(item.value) <> 'object'
       )
    THEN
        RAISE EXCEPTION USING
            ERRCODE = '42501', MESSAGE = 'operation not permitted';
    END IF;

    SELECT * INTO job
    FROM public.processing_jobs
    WHERE id = p_job_id
    FOR UPDATE;
    IF NOT FOUND
       OR job.job_type <> 'entry_processing'
       OR job.status <> 'completed'
       OR job.claim_token IS DISTINCT FROM p_claim_token
    THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    SELECT * INTO analysis
    FROM public.entry_analyses
    WHERE entry_id = job.entry_id AND user_id = job.user_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING
            ERRCODE = 'P0001', MESSAGE = 'stale processing claim';
    END IF;

    IF analysis.eligibility <> 'accepted' THEN
        RETURN QUERY SELECT false, 0;
        RETURN;
    END IF;

    SELECT entry_date INTO entry_local_date
    FROM public.entries
    WHERE id = job.entry_id AND user_id = job.user_id;

    IF pg_catalog.jsonb_array_length(p_signals) <> (
        SELECT pg_catalog.count(*)::integer
        FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'signal materialization is incomplete';
    END IF;

    FOR persisted_signal IN
        SELECT *
        FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
        ORDER BY id
    LOOP
        SELECT item.value INTO supplied_signal
        FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
        WHERE item.value ->> 'id' = persisted_signal.id::text;

        IF supplied_signal IS NULL
           OR supplied_signal ->> 'signal_type'
                IS DISTINCT FROM persisted_signal.signal_type
           OR (supplied_signal ->> 'source_start')::integer
                IS DISTINCT FROM persisted_signal.source_start
           OR (supplied_signal ->> 'source_end')::integer
                IS DISTINCT FROM persisted_signal.source_end
           OR (supplied_signal ->> 'occurred_on')::date
                IS DISTINCT FROM entry_local_date
        THEN
            RAISE EXCEPTION USING
                ERRCODE = '22023', MESSAGE = 'signal identity is invalid';
        END IF;

        IF persisted_signal.signal_type IN (
            'energy_gain', 'energy_loss', 'self_knowledge', 'realization',
            'explicit_preference', 'need', 'belief', 'avoidance',
            'protective_strategy', 'conflict', 'causal_relationship'
        ) THEN
            review_item := supplied_signal -> 'review_item';
            expected_review_items := expected_review_items + 1;
            IF pg_catalog.jsonb_typeof(review_item) <> 'object'
               OR NOT review_item ?& ARRAY[
                    'id', 'category', 'statement_envelope',
                    'source_quote_envelope', 'inference_level', 'metadata'
               ]
               OR review_item - ARRAY[
                    'id', 'category', 'statement_envelope',
                    'source_quote_envelope', 'inference_level', 'metadata'
               ] <> '{}'::jsonb
               OR public.is_valid_encrypted_envelope_v1(
                    review_item -> 'statement_envelope'
               ) IS NOT TRUE
               OR public.is_valid_encrypted_envelope_v1(
                    review_item -> 'source_quote_envelope'
               ) IS NOT TRUE
               OR review_item ->> 'inference_level'
                    NOT IN ('direct', 'inferred')
               OR pg_catalog.jsonb_typeof(review_item -> 'metadata') <> 'object'
               OR NOT (review_item -> 'metadata') ?& ARRAY[
                    'model_id', 'prompt_version', 'source'
               ]
               OR (review_item -> 'metadata') - ARRAY[
                    'model_id', 'prompt_version', 'source'
               ] <> '{}'::jsonb
               OR review_item #>> '{metadata,model_id}'
                    IS DISTINCT FROM analysis.model_id
               OR review_item #>> '{metadata,prompt_version}'
                    IS DISTINCT FROM analysis.prompt_version
               OR review_item #>> '{metadata,source}'
                    IS DISTINCT FROM 'entry_analysis'
               OR review_item ->> 'category' IS DISTINCT FROM (CASE
                    WHEN persisted_signal.signal_type IN (
                        'energy_gain', 'energy_loss'
                    ) THEN 'energy'
                    WHEN persisted_signal.signal_type IN (
                        'self_knowledge', 'realization', 'explicit_preference'
                    ) THEN 'self_knowledge'
                    ELSE 'needs_beliefs'
               END)
            THEN
                RAISE EXCEPTION USING
                    ERRCODE = '22023', MESSAGE = 'review item is invalid';
            END IF;

            INSERT INTO public.review_items (
                id, user_id, entry_id, entry_signal_id, scope, item_type,
                category, statement_envelope, source_quote_envelope,
                source_entry_ids, source_dates, inference_level,
                model_confidence, review_status, evidence_weight,
                reflection_eligible, metadata
            ) VALUES (
                (review_item ->> 'id')::uuid, job.user_id, job.entry_id,
                persisted_signal.id, 'entry_insight',
                persisted_signal.signal_type, review_item ->> 'category',
                review_item -> 'statement_envelope',
                review_item -> 'source_quote_envelope',
                ARRAY[job.entry_id], ARRAY[entry_local_date],
                review_item ->> 'inference_level', persisted_signal.confidence,
                'pending', 1.0, true, review_item -> 'metadata'
            )
            ON CONFLICT (entry_signal_id)
                WHERE entry_signal_id IS NOT NULL
            DO NOTHING;
        ELSIF supplied_signal ? 'review_item' THEN
            RAISE EXCEPTION USING
                ERRCODE = '22023',
                MESSAGE = 'non-reviewable signal has a review item';
        END IF;
    END LOOP;

    IF (
        SELECT pg_catalog.count(*)::integer
        FROM pg_catalog.jsonb_array_elements(p_signals) AS item(value)
        WHERE item.value ? 'review_item'
    ) <> expected_review_items THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'review item mapping is incomplete';
    END IF;

    SELECT pg_catalog.count(*)::integer INTO persisted_review_items
    FROM public.review_items
    WHERE entry_signal_id IN (
        SELECT id FROM public.entry_signals
        WHERE analysis_id = analysis.id AND user_id = job.user_id
    );
    IF persisted_review_items <> expected_review_items THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023', MESSAGE = 'review item persistence is incomplete';
    END IF;

    RETURN QUERY SELECT true, persisted_review_items;
END
$function$;

REVOKE ALL ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb)
    FROM PUBLIC, anon, authenticated, orion_app, orion_worker;
GRANT EXECUTE
    ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb)
    TO orion_worker;

COMMENT ON FUNCTION public.materialize_entry_review_items(uuid, uuid, jsonb) IS
    'Materializes validated encrypted Entry Insight Review rows for a completed claim without changing feedback on replay.';
