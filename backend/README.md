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

The committed `supabase_schema.sql` is byte-identical to the fresh-install migration at this gate.
