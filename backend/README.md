# Orion profile and entry backend

Fresh Python 3.11/FastAPI implementation of the reviewed 13-operation profile and entry contract.
Supabase Auth owns browser authentication; this API verifies access tokens and derives ownership
from the verified UUID. PostgreSQL RLS independently enforces isolation.

## Local setup

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env
.venv/bin/uvicorn server:app --reload
```

`GET /health` is anonymous. Swagger and `/openapi.json` appear only outside production when
`ENABLE_API_DOCS=true`. Never place the Supabase secret key, database URLs, OpenAI key, encryption
keys, fingerprint keys, bearer tokens, journal text, transcripts, or provider payloads in logs.

## Verification

```bash
.venv/bin/python -m compileall app server.py
.venv/bin/python -m pytest -m "not live_supabase"
```

Database migrations are a controlled pre-deploy action and never run during normal application
startup. Do not target a shared or production database without explicit authorization.

After creating the Supabase project or authorized disposable database, apply the ordered,
checksum-locked migration set explicitly:

```bash
ORION_MIGRATION_DATABASE_URL='postgresql://migration-role:secret@host/database' \
  .venv/bin/python scripts/migrate.py
```

Run the durable shared processing worker as a separate process using the restricted worker database
role. Text, voice, historical imports, retries, and operator backfill batches all use the same
`processing_jobs` queue:

```bash
.venv/bin/python scripts/run_processing_worker.py
```

Entry jobs decrypt and redact locally, then make one strict combined Responses API analysis call
with provider storage disabled. Configure that call with `OPENAI_ENTRY_ANALYSIS_MODEL` (default
`gpt-5.6-luna`). Deterministic exclusions make no provider call, while accepted analysis, legacy
extraction, entry completion, signals, and reflection counters commit atomically.

Reflection rollout is cohort-scoped and defaults off. Set `REFLECTION_ROLLOUT_MODE=shadow` with an
explicit comma-separated `REFLECTION_ROLLOUT_USER_IDS` cohort to run full synthesis without creating
snapshots or candidates. `publish` is the only mode that may serve the Reflections API. The worker
rejects synthesis jobs whose persisted mode or owner no longer matches the configured rollout.

Historical analysis backfill is a persisted operator workflow. It scans only the configured cohort,
in ascending `(created_at, id)` order, and enqueues priority-10 jobs. New user-created entry jobs use
priority 100 and are always claimed first. Create a plan, retain the returned safe run ID from the
structured log, and advance it one bounded batch at a time:

```bash
.venv/bin/python scripts/run_processing_worker.py --backfill-plan --backfill-batch-size 100
.venv/bin/python scripts/run_processing_worker.py --backfill-action status --backfill-run-id RUN_UUID
.venv/bin/python scripts/run_processing_worker.py --backfill-action batch --backfill-run-id RUN_UUID
.venv/bin/python scripts/run_processing_worker.py --backfill-action pause --backfill-run-id RUN_UUID
.venv/bin/python scripts/run_processing_worker.py --backfill-action resume --backfill-run-id RUN_UUID
```

Each batch stops before enqueueing when the configured total queue-depth or oldest-pending-age budget
is reached. Commands and logs expose counts, state, budgets, and opaque IDs only; they never load or
print raw journal content.

Reflection observability is OTLP-only and exposes no HTTP metrics route. When `OTEL_ENABLED=true`,
the API and worker export the nine contract metrics plus queue-age and scheduler-user instruments.
Reflection events use a strict field allowlist; model attempts record only configured model role/ID,
prompt version, duration, available token counts, controlled outcome, and retry class. Journal or
redacted text, prompts, evidence, provider responses, mappings, envelopes, and exception strings are
never recorded. See `docs/REFLECTION_OBSERVABILITY.md` for the exact instruments and runbook.

Presidio and `tldextract` initialize before the application is returned. The spaCy model must already
be installed; public-suffix parsing uses only `tldextract`'s packaged snapshot with no cache or network
fallback. Missing local privacy dependencies fail startup.

After external access is explicitly authorized, verify the configured Luna, Terra, and Sol IDs with
the non-content Models API preflight. It never creates a Response:

```bash
.venv/bin/python scripts/check_reflection_model_access.py
```

The frozen evaluation runner accepts extracted spans and classifications only, not journal content.
It refuses fewer than 100 unique records or any record without explicit consent:

```bash
.venv/bin/python scripts/run_reflection_evaluation.py path/to/consented-frozen-results.json
```

The API uses in-process rate limiting and must run as exactly one instance with one Uvicorn worker.
Before horizontal scale, replace it with a shared Redis-compatible limiter. See
`docs/DEPLOYMENT.md` for the controlled migration, role, worker, readiness, tracing, and scale-out
requirements. The committed `supabase_schema.sql` is the exact ordered concatenation of all migrations.
