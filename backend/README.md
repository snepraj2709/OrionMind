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

To enqueue one idempotent, low-priority batch of up to 100 already-materialized legacy entries:

```bash
.venv/bin/python scripts/run_processing_worker.py --backfill-batch 100
```

The API uses in-process rate limiting and must run as exactly one instance with one Uvicorn worker.
Before horizontal scale, replace it with a shared Redis-compatible limiter. See
`docs/DEPLOYMENT.md` for the controlled migration, role, worker, readiness, tracing, and scale-out
requirements. The committed `supabase_schema.sql` is the exact ordered concatenation of all migrations.
