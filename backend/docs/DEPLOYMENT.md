# Deployment preparation

This backend is prepared for deployment review but is not authorized for deployment by this build.
Live Supabase/RLS proof remains waived and pending.

## Process topology

- Run the API as exactly one instance and one Uvicorn worker while rate limiting is in process.
- Run `python scripts/run_past_import_worker.py` as a separate worker process.
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

Use HTTPS Supabase and CORS origins. Keep API docs disabled. Retain the fixed reflection threshold,
request limits, one-worker setting, and separate application/worker URLs enforced by production
settings validation.

## Startup and health

Startup performs a bounded `SELECT 1` through every configured database engine and recovers stale
historical-import claims through the worker RPC. A failed readiness check prevents startup. It never
runs migrations. `/health` remains an opaque liveness response: `{"status":"ok"}`.

## Observability

Structured logs contain request ID, method, route path, status timing, and safe worker event codes.
They contain no journal content, transcript, raw audio, bearer token, provider payload, envelope, or
secret. Set `OTEL_ENABLED=true` with an HTTPS `OTEL_EXPORTER_OTLP_ENDPOINT` to enable FastAPI and
SQLAlchemy traces. No public metrics route exists.

## Release blockers

Before calling the service production-ready, run the waived two-account Supabase API/direct-RLS proof,
Auth deletion/cascade proof, and cross-user ciphertext/decryption proof against an authorized disposable
Supabase project. Deployment itself also requires explicit authorization.
