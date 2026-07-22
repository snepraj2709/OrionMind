# Reflection Engine audit

Audit date: 2026-07-22

Contract: `docs/Reflection-Algorithm.md` and the implementation brief supplied for this task.

Baseline verification:

- Frontend unit suite: 279 passed.
- Backend suite from `backend/`: 265 passed, 28 skipped.
- The 28 skips are database/live integration boundaries and are not counted as current proof.
- Current embedding branch: 299 backend tests pass against disposable PostgreSQL 16 with pgvector.
- The worktree was clean before this audit. `main` was one unrelated commit ahead of `origin/main` (`0ee533c ignore playwright`).

## Current flow map

| Stage                                                                    | Current implementation                                                              | Audit result                                                 |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Authenticated entry creation and encrypted persistence                   | FastAPI entry routes/services, owner-scoped units of work, entry RPCs               | Implemented; local regression coverage passes                |
| Shared worker, claims, heartbeats, retries and stale recovery            | `processing_jobs`, `JobService`, `ProcessingWorker`, worker RPCs                    | Implemented; local regression coverage passes                |
| Segmentation, deterministic quality, PII redaction and signal extraction | `source_segments.py`, `quality.py`, `redaction.py`, `ProcessingService`             | Implemented; local regression coverage passes                |
| Exact quote/offset/entry/owner validation                                | processing materialization, reflection evidence validator, RLS and API tests        | Implemented; local regression coverage passes                |
| Signal embeddings and pgvector storage                                   | Fixed-dimension provider, pgvector column and claim-bound atomic worker persistence | Fixed and authenticated live E2E verified in RF-AUDIT-001    |
| Recalculation eligibility                                                | Local-6-PM entry/date scheduler plus aggregate-GET synthesis request                | Incorrect/incomplete; P1 finding RF-AUDIT-002                |
| Hidden driver, loop and tension construction                             | Deterministic candidates, scoring, Terra renderer and conditional Sol critic        | Implemented; local regressions and retained live sample pass |
| Versioned snapshot and strict aggregate API                              | snapshot RPCs, plural authenticated API, feedback endpoint                          | Implemented; local regression coverage passes                |
| Frontend loading/error/empty/stale/success and partial insight states    | typed HTTP repository and existing Reflection screen components                     | Implemented; frontend regressions pass                       |
| Required adversarial live dataset and before/after vector diff           | Existing live runner accepts only the fixed 30-entry genuine dataset                | Missing verification; P1 finding RF-AUDIT-003                |

## Findings

### RF-AUDIT-000 — Synthesis job enqueue crashes at runtime

- Severity: `P1`
- Expected behaviour: an eligible aggregate read or scheduler sweep enqueues or expedites a reflection synthesis job idempotently.
- Actual behaviour: migration `0014_reflection_on_demand.sql` calls `pg_catalog.least(timestamp, timestamp)`. PostgreSQL implements `LEAST` as a conditional expression, so the function definition installs but every enqueue/expedite execution raises `UndefinedFunction`.
- Relevant files: `backend/migrations/0014_reflection_on_demand.sql`, `backend/supabase_schema.sql`, `backend/tests/test_stage7_reflection_database.py`.
- Reproducible test: install all migrations in PostgreSQL and call `public.enqueue_processing_job` for a reflection synthesis source version; PostgreSQL raises `function pg_catalog.least(timestamp with time zone, timestamp with time zone) does not exist`.
- Proposed smallest fix: leave the applied `0014` checksum unchanged, add a forward migration that replaces the function with unqualified `LEAST`, and add a runtime database regression.
- Status: fixed in commit `c1ccd19`. Migration `0015` is applied remotely, its ledger checksum matches the local file, the migration runner is idempotently current, and the installed function uses valid `LEAST(...)` rather than `pg_catalog.least(...)`.

### RF-AUDIT-001 — Accepted signals are never embedded

- Severity: `P1`
- Expected behaviour: each accepted, redacted signal receives one embedding; the embedding is stored in PostgreSQL pgvector, unchanged signals are not re-embedded, and excluded content creates no embeddings.
- Actual behaviour before the fix: `entry_signals` stored encrypted payloads and deterministic fingerprints only. The schema did not install pgvector. `ProcessingService` had no embedding dependency or batch call. The prior test report explicitly marked embeddings as not implemented.
- Relevant files: `backend/app/modules/processing/embeddings.py`, `backend/app/modules/processing/service.py`, `backend/app/modules/processing/repository.py`, `backend/app/main.py`, `backend/migrations/0016_signal_embeddings.sql`, `backend/supabase_schema.sql`, `backend/tests/test_stage7_signal_embeddings.py`, `backend/tests/test_stage7_entry_analysis.py`, `backend/scripts/run_sample_reflection_e2e.py`, `docs/reflection-testing-pipeline.md`.
- Reproducible test: process an accepted entry and inspect `public.entry_signals`; there is no embedding column or stored vector. Repository search for `vector`, `embedding`, and `cosine` finds no backend implementation.
- Proposed smallest fix: add the pgvector extension and a fixed-dimension nullable migration column for upgrade safety; batch-embed only accepted redacted signal summaries before the atomic apply RPC; require embeddings for newly inserted signals; inject the existing OpenAI client behind a small provider protocol; add unit/database/privacy regressions and a bounded cosine-observation query. Do not add another vector database or use similarity as publication proof.
- Status: fixed and live-verified. The configured embedding model passed a content-free Models API preflight and one synthetic 1,536-dimension embedding request. The full backend suite passes `299` tests against disposable PostgreSQL 16 with pgvector, including worker-only RPC ACLs, cosine-operator availability, exact vector dimensions, excluded-entry call suppression, and rollback when vector persistence fails. Remote migration `0016` is applied, its ledger checksum matches the local file, and the runner is idempotently current. A temporary authenticated test identity submitted one uniquely marked entry through `POST /api/v1/past-entries`; the local production worker completed one Luna call and one embedding call, persisted all `11` accepted signals as `vector(1536)` using `text-embedding-3-small`, measured self-cosine distance `0`, and returned the completed entry through authenticated `GET /api/v1/entries/{entry_id}`. Collected telemetry contained no generated content. Cleanup used the owner-scoped entry-deletion RPC and then removed the temporary Auth identity; the read-only observer confirmed zero residual rows. Estimated measured model cost was `$0.02720816`, of which embeddings were `$0.00001166`.

### RF-AUDIT-002 — Recalculation eligibility is inconsistent and aggregate reads can synthesize too early

- Severity: `P1`
- Expected behaviour: update after three new valid entries, 500 new reflective words, or one valid entry pending for three days; an aggregate GET must not bypass these criteria. The initial eligible snapshot remains allowed once the global 3-entry/2-date/200-word basis is met.
- Actual behaviour: the scheduler checks three entries or two entries on two dates and does not track new reflective words or pending age. `ReflectionsService._requested_source_version` can enqueue a new synthesis job whenever any accepted source version is newer than the snapshot, so one new accepted entry followed by a GET can trigger paid synthesis.
- Relevant files: `backend/app/modules/reflections/service.py`, `backend/app/modules/reflections/repository.py`, `backend/app/modules/jobs/service.py`, `backend/migrations/0011_reflection_rollout.sql`, `backend/migrations/0014_reflection_on_demand.sql`, `backend/tests/test_reflections_api.py`, `backend/tests/test_stage7_reflection_database.py`.
- Reproducible test: provide an eligible existing snapshot at source version N and aggregate state at N+1 with one new valid entry; `_requested_source_version` returns N+1 and the GET requests a synthesis job.
- Proposed smallest fix: track new reflective words and oldest pending accepted-entry time in `reflection_user_state`; centralize the three eligibility predicates in a database function used by scheduler/on-demand paths; allow GET to expedite an already eligible/pending job but not bypass eligibility; add exact boundary and idempotency regressions.
- Status: open.

### RF-AUDIT-003 — The live harness does not exercise the required garbage, contradiction, injection, cleanup or embedding diff datasets

- Severity: `P1`
- Expected behaviour: a small authenticated test run adds prefixed valid, garbage, contradictory and injection entries through the real API; polls the real worker; records before/after snapshots and vector observations; verifies excluded entries do not affect counters; and cleans up only generated rows.
- Actual behaviour: `run_sample_reflection_e2e.py` is intentionally bound to exactly 30 genuine June 2026 entries and fails closed when the test user is non-empty. It records a strong genuine-flow report but cannot run the new deterministic adversarial dataset or embedding measurements.
- Relevant files: `backend/scripts/run_sample_reflection_e2e.py`, `backend/tests/test_sample_reflection_e2e.py`, `data/sample-reflection-result.json`, `docs/reflection-testing-pipeline.md`.
- Reproducible test: attempt to supply fewer/mixed prefixed entries or run against the retained designated test account; the canonical dataset and empty-account guards stop the run before the requested cases.
- Proposed smallest fix: add a separate bounded hardening runner rather than weakening the canonical 30-entry proof. Reuse authentication, API, worker polling and read-only observer helpers; require a prefix; track exact created IDs; clean up only those IDs; write content-free local metrics and cosine observations.
- Status: blocked on RF-AUDIT-001 and RF-AUDIT-002.

## P2 and deferred observations

### RF-AUDIT-004 — Weekly deterministic rebuild is not implemented

- Severity: `P2`
- Expected behaviour: a weekly 90-day rebuild corrects measured incremental drift.
- Actual behaviour: candidate construction is rebuilt from the current 90-day signal basis during synthesis, but there is no independent weekly trigger.
- Relevant files: `backend/app/modules/reflection_engine/service.py`, `backend/migrations/0011_reflection_rollout.sql`, `backend/app/modules/jobs/worker.py`.
- Reproducible test: inspect scheduler predicates; no weekly timestamp/state exists.
- Proposed smallest fix: defer until drift is demonstrated. The synthesis path already reconstructs candidates from the bounded current basis, so adding another trigger now is a scheduling enhancement rather than a confirmed correctness repair.
- Status: deferred.

### RF-AUDIT-005 — Standalone safety screening remains combined with quality/prompt safeguards

- Severity: `Deferred`
- Expected behaviour: journal prompt injection remains untrusted content and unsafe output is discarded.
- Actual behaviour: the current combined analyzer prompt, strict schemas, closed catalogs, local materialization and validation enforce this boundary; there is no separate safety service.
- Relevant files: `backend/app/modules/processing/prompts.py`, `backend/app/modules/processing/schemas.py`, `backend/app/modules/processing/service.py`, `backend/tests/test_stage7_reflection_privacy.py`.
- Reproducible test: existing prompt-injection tests validate empty/closed output and local catalogs.
- Proposed smallest fix: no architecture change unless the adversarial live run demonstrates a bypass.
- Status: deferred.

### RF-AUDIT-006 — Upgrade rows remain nullable until a bounded backfill is justified

- Severity: `P2`
- Expected behaviour: new and invalidated accepted signals are embedded exactly once; an upgrade must not force a full-user rebuild or re-embed unchanged rows.
- Actual behaviour: migration `0016` is upgrade-safe and leaves pre-existing signals with `NULL` embeddings. New worker-processed signals receive vectors atomically, but there is no automatic historical-vector backfill.
- Relevant files: `backend/migrations/0016_signal_embeddings.sql`, `backend/app/modules/processing/service.py`, `backend/app/modules/processing/repository.py`.
- Reproducible test: upgrade a database containing `entry_signals`; existing rows remain valid with null embedding metadata, while newly processed accepted signals store 1,536-dimension vectors.
- Proposed smallest fix: defer a bounded, null-only backfill until a product query requires historical vectors. It must reuse encrypted signal payloads without rerunning Luna, obey queue budgets, and never overwrite an existing vector.
- Status: deferred for the current MVP; the required hardening dataset will create its matching historical and new signals after migration.

## Fix order

1. RF-AUDIT-000 — synthesis enqueue runtime repair.
2. RF-AUDIT-001 — pgvector signal embeddings.
3. RF-AUDIT-002 — exact recalculation eligibility.
4. RF-AUDIT-003 — bounded authenticated hardening runner and final diff evidence.

No P0 defect is currently reproduced by the local test suite. Live/database isolation claims will remain provisional until the authenticated hardening run and configured integration boundaries complete.
