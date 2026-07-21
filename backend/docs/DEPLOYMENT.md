# Deployment preparation

This backend is prepared for deployment review but is not authorized for deployment by this build.
Live Supabase/RLS proof remains waived and pending.

## Process topology

- Run the API as exactly one instance and one Uvicorn worker while rate limiting is in process.
- Run `python scripts/run_processing_worker.py` as the separate shared processing worker.
- The API connects through the restricted application login; the worker connects through a distinct
  login that can assume only `orion_worker`.
- Before adding an API replica or Uvicorn worker, replace the process limiter with a shared
  Redis-compatible implementation preserving the committed endpoint classes and windows.

The container's default command already uses `--workers 1`. Production settings also reject a
`WEB_CONCURRENCY` value other than `1` and reject disabled rate limiting.

## Controlled pre-deploy migration

Migrations never run at API or worker startup. With an explicitly authorized migration-owner URL,
run exactly:

```bash
ORION_MIGRATION_DATABASE_URL='postgresql://migration-owner:secret@host/database' \
  python scripts/migrate.py
```

The runner takes the Orion advisory transaction lock, verifies the checksum ledger, and applies the
ordered migration set once. Never point it at a live or shared database without explicit approval.

## Required secrets and roles

Set every production-required value in `.env.example` through the deployment secret manager. Keep
Supabase service credentials, PostgreSQL URLs, OpenAI keys, AES keys, fingerprint keys, and OTLP
credentials out of image layers and logs. Provision distinct login roles outside the application
migrations, grant the application login the required `authenticated` role membership, and grant the
worker login only the `orion_worker` capability.

Set `OPENAI_ENTRY_ANALYSIS_MODEL` to an available structured-output model; the committed default is
`gpt-5.6-luna`. Entry analysis uses one Responses API call with provider storage and SDK retries
disabled. The worker retries only the durable queue's allowlisted transient failures. Local Presidio
redaction loads the installed `en_core_web_sm` model before startup completes. `tldextract` uses its
packaged public-suffix snapshot with cache and remote suffix URLs disabled. Neither dependency may
download data at runtime; missing local data fails startup.

Use HTTPS Supabase and CORS origins. Keep API docs disabled. Retain the fixed reflection threshold,
request limits, one-worker setting, and separate application/worker URLs enforced by production
settings validation.

Keep `REFLECTION_ENGINE_ENABLED=false`, `REFLECTION_SCHEDULER_ENABLED=false`,
`REFLECTION_API_ENABLED=false`, `REFLECTION_ROLLOUT_MODE=off`, and
`REFLECTION_ROLLOUT_USER_IDS` empty in production until all Reflection release blockers are closed.
The scheduler requires the engine plus `shadow` or `publish` mode. Any active mode requires an
explicit UUID cohort. The public API additionally requires `publish`; enabled requests from users
outside the cohort receive the same opaque unavailable response as a disabled API. Frontend
production builds must likewise keep `NEXT_PUBLIC_REFLECTIONS_ENABLED=false`. These controls are
not substitutes for KMS readiness.

## Controlled Reflection rollout and backfill

Use a fixed internal cohort and begin in `shadow`. Shadow jobs execute the real synthesis and local
validation path, then atomically persist only non-content counts in `reflection_shadow_runs`; they
do not create candidates, insights, evidence, or snapshots. Moving the same cohort to `publish`
promotes eligible shadow jobs through the scheduler. Reverting `REFLECTION_ROLLOUT_MODE=off` and
disabling the scheduler stops new synthesis; the worker also fails any mismatched claimed synthesis
job closed.

Backfill is a separate, persisted operator workflow and may be prepared before synthesis is enabled.
It selects only completed, already-materialized entries owned by `REFLECTION_ROLLOUT_USER_IDS`, never
loads their content in the operator process, and advances idempotently in ascending
`(created_at, id)` order. User-created entry work has priority 100; backfill has priority 10.

```bash
# 1. Create one plan and copy only the logged run_id.
python scripts/run_processing_worker.py --backfill-plan --backfill-batch-size 100

# 2. Inspect or advance one bounded batch.
python scripts/run_processing_worker.py --backfill-action status --backfill-run-id RUN_UUID
python scripts/run_processing_worker.py --backfill-action batch --backfill-run-id RUN_UUID

# 3. Pause safely, then resume from the persisted cursor.
python scripts/run_processing_worker.py --backfill-action pause --backfill-run-id RUN_UUID
python scripts/run_processing_worker.py --backfill-action resume --backfill-run-id RUN_UUID
```

`PROCESSING_BACKFILL_MAX_QUEUE_DEPTH` and
`PROCESSING_BACKFILL_MAX_OLDEST_PENDING_SECONDS` are captured in each plan. A batch that reaches
either budget enqueues nothing and reports `QUEUE_DEPTH` or `OLDEST_PENDING_AGE`; inspect queue
health, let foreground work drain, then run the same batch command again. Only one unfinished plan
may exist. Status output contains the opaque run ID, counts, state, queue budgets, and throttle code,
never user IDs, journal content, ciphertext, prompts, or provider payloads.

## Startup and health

Web startup performs only a bounded `SELECT 1` through every configured database engine. A failed
readiness check prevents startup. The processing worker—not the web process—recovers stale shared
queue claims on worker startup and every configured recovery interval. Neither process runs
migrations. `/health` remains an opaque liveness response: `{"status":"ok"}`.

## Observability

Structured Reflection logs accept only the documented event and field allowlist. Request completion
uses the matched route template and records status plus timing. Model attempts record role, configured
model ID, prompt version, duration, input/output tokens when returned, outcome, and retry class. Logs
and manual spans contain no journal or redacted text, transcript, raw audio, bearer token, prompt,
evidence, provider response, PII mapping, envelope, exception string, or secret.

Set `OTEL_ENABLED=true` with an HTTPS `OTEL_EXPORTER_OTLP_ENDPOINT` to enable FastAPI/SQLAlchemy
traces and periodic OTLP Reflection metric export. No public metrics route exists. The worker-only
observability RPC reports pending depth and oldest pending age for both job types. Scheduler events
and metrics separately report users checked, eligible, and enqueued. Instrument names, labels, and
the privacy test are documented in `REFLECTION_OBSERVABILITY.md`.

Do not infer model availability from configuration. With separately authorized network access and
the existing secret-managed `OPENAI_API_KEY`, run this non-content Models API preflight from
`backend/`; it performs no Responses request and submits no journal or evidence content:

```bash
.venv/bin/python scripts/check_reflection_model_access.py
```

Do not run the evaluation gate on production journals or ad-hoc exports. Supply a frozen internal
result set containing no text, at least 100 unique records, and explicit per-record consent:

```bash
.venv/bin/python scripts/run_reflection_evaluation.py /authorized/path/results.json
```

The command exits non-zero unless exact idea/memory span precision is at least `0.90`, top-theme
agreement is at least `0.95`, invalid structured outputs do not increase from the legacy baseline,
and known Reflection polarity regressions are zero. The repository intentionally contains no
fabricated 100-entry dataset or claimed result.

## Release blockers

Before calling the service production-ready, implement a real KMS-backed key source and its
rotation and recovery runbook; environment-held master-key maps are not sufficient. Then run the
waived two-account Supabase API/direct-RLS proof, Auth
deletion/cascade proof, and cross-user ciphertext/decryption proof against an authorized disposable
Supabase project. Deployment itself also requires explicit authorization.
