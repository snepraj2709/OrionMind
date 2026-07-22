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
| Recalculation eligibility                                                | Central persisted-data predicate used by local-6-PM and aggregate-GET request paths | Fixed and authenticated live E2E verified in RF-AUDIT-002    |
| Hidden driver, loop and tension construction                             | Deterministic candidates, scoring, Terra renderer and conditional Sol critic        | Implemented; local regressions and retained live sample pass |
| Versioned snapshot and strict aggregate API                              | snapshot RPCs, plural authenticated API, feedback endpoint                          | Implemented; local regression coverage passes                |
| Frontend loading/error/empty/stale/success and partial insight states    | typed HTTP repository and existing Reflection screen components                     | Implemented; frontend regressions pass                       |
| Required adversarial live dataset and before/after vector diff           | Separate bounded runner uses a temporary Auth identity and content-free report      | Implemented; authenticated 14-case live E2E passed           |

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
- Actual behaviour before fix: the scheduler checked three entries or two entries on two dates and did not evaluate new reflective words or pending age. `ReflectionsService._requested_source_version` could enqueue a new synthesis job whenever any accepted source version was newer than the snapshot, so one new accepted entry followed by a GET could trigger paid synthesis.
- Relevant files: `backend/app/modules/reflections/service.py`, `backend/app/modules/reflections/repository.py`, `backend/app/modules/reflections/types.py`, `backend/migrations/0017_reflection_recalculation_eligibility.sql`, `backend/supabase_schema.sql`, `backend/tests/test_reflections_api.py`, `backend/tests/test_p009c_reflection_observability.py`, `backend/tests/test_stage7_reflection_database.py`.
- Reproducible test: `test_recalculation_eligibility_boundaries_and_atomic_request` proves the exact 500-word, three-day, three-entry and initial-snapshot boundaries plus signal gating, ACLs and replay idempotency. `test_stale_snapshot_with_one_recent_entry_does_not_request_synthesis` protects the API delegation boundary.
- Proposed smallest fix: derive pending entry count, reflective words and oldest entry timestamp from the existing indexed accepted analyses since the last snapshot; centralize the predicate in one worker-only database function used by scheduler and on-demand paths; request or expedite synthesis atomically under the existing per-user advisory lock. No new counters, table or service are required.
- Status: fixed and live-verified. The full backend suite passes `301` tests, including PostgreSQL 16 boundary, scheduler timezone/DST, concurrent sweep, schema-upgrade and privilege checks. Remote migration `0017` is applied and an immediate rerun reports the schema current. In an isolated authenticated live run, one accepted entry produced six embedded signals and an aggregate GET created zero synthesis jobs. After three accepted entries across two dates and 265 reflective words, all 29 signals had embeddings; the aggregate GET created exactly one pending synthesis job and a replay returned the same job without duplication. No synthesis or critic call ran. The measured verification used three Luna and three embedding calls at an estimated `$0.08459708`, then deleted the temporary Auth identity; the read-only observer confirmed zero residual rows.

### RF-AUDIT-003 — The live harness does not exercise the required garbage, contradiction, injection, cleanup or embedding diff datasets

- Severity: `P1`
- Expected behaviour: a small authenticated test run adds prefixed valid, garbage, contradictory and injection entries through the real API; polls the real worker; records before/after snapshots and vector observations; verifies excluded entries do not affect counters; and cleans up only generated rows.
- Actual behaviour before the staged fix: `run_sample_reflection_e2e.py` is intentionally bound to exactly 30 genuine June 2026 entries and fails closed when the test user is non-empty. It records a strong genuine-flow report but cannot run the new deterministic adversarial dataset or embedding measurements.
- Relevant files: `backend/scripts/run_sample_reflection_e2e.py`, `backend/scripts/run_reflection_hardening_e2e.py`, `backend/tests/test_reflection_hardening_e2e.py`, `backend/tests/test_sample_reflection_e2e.py`, `data/sample-reflection-result.json`, `docs/reflection-testing-pipeline.md`.
- Reproducible test: attempt to supply fewer/mixed prefixed entries or run against the retained designated test account; the canonical dataset and empty-account guards stop the run before the requested cases.
- Proposed smallest fix: add a separate bounded hardening runner rather than weakening the canonical 30-entry proof. Reuse authentication, API, worker polling and read-only observer helpers; require a prefix; track exact created IDs; clean up only those IDs; write content-free local metrics and cosine observations.
- Status: fixed and authenticated live-verified. The isolated 14-case run used a temporary Auth identity and the real API, worker, strict schemas, encryption, database roles and model providers. Five baseline entries produced 43 accepted signals and matching embeddings, then snapshot version 1 at source version 110. Blank input returned 422; mic/noise, exact duplicate, near duplicate, copied informational text and task/note content were excluded with zero signals and zero embeddings, and the snapshot/counters did not advance. Three contradictory/adversarial updates produced 18 accepted signals and matching embeddings; candidate contradiction was observed and snapshot version 2 advanced to source version 118. The bounded vector observation measured 1,480 related and 119 unrelated cross-entry pairs with no missing embedding. One Luna attempt timed out with zero returned tokens and completed through the normal single retry; both Terra synthesis calls and all three conditional Sol calls succeeded. The content-free report passed its safety guard, deletion of the temporary identity cascaded only its generated data, and the observer confirmed zero residual rows.

### RF-AUDIT-003A — Every post-snapshot candidate refresh fails strict materialization

- Severity: `P1`
- Expected behaviour: a later eligible synthesis decrypts the previously persisted candidate payload, recalculates deterministic scores with new evidence and counterevidence, and advances the snapshot.
- Actual behaviour before the fix: `get_reflection_candidate_basis` correctly returned each candidate's encrypted `payload_envelope`, but `_materialize_basis` also passed that storage-only field into the extra-forbid `PreviousCandidate` model. The first synthesis succeeded because no prior candidate existed; the first eligible refresh failed before any synthesis-model call with `INVALID_SYNTHESIS`, and the API retained the prior snapshot as `stale/failed`.
- Relevant files: `backend/app/modules/reflection_engine/service.py`, `backend/tests/test_stage7_reflection_candidates.py`, `backend/scripts/run_reflection_hardening_e2e.py`.
- Reproducible test: materialize an exact persisted candidate-basis row containing `payload_envelope`; prior code raises a Pydantic extra-field validation error. The authenticated hardening run reproduced the same boundary after five accepted baseline entries, one available snapshot, six correctly excluded entries and three accepted counterevidence/injection entries.
- Proposed root fix: define strict persisted-row models for candidate signals and previous candidates at the repository boundary. Validate the complete database JSON shape, decrypt envelopes explicitly, and pass only declared domain fields into `CandidateSignal` and `PreviousCandidate`; never spread arbitrary persistence dictionaries into strict domain models. Make the hardening runner fail immediately when either synthesis drain reports a terminal job.
- Status: fixed in commit `64e9e4b` and authenticated live-verified. The regression runs a first synthesis and a second contradictory refresh using the exact persisted candidate row shape, proves snapshot version advancement, verifies storage-only envelopes never cross the domain boundary, and rejects undeclared persistence fields. The complete candidate/synthesis modules pass (`48` tests). In the isolated live run, the second synthesis loaded the encrypted version-1 candidates, reconstructed the strict domain basis, completed Terra and Sol on its first job attempt, and persisted snapshot version 2 instead of failing with `INVALID_SYNTHESIS`.

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
- Status: deferred. The authenticated prompt-injection fixture was treated as journal evidence under the existing untrusted-content boundary; it did not escape the strict schema or prevent safe snapshot publication.

### RF-AUDIT-006 — Upgrade rows remain nullable until a bounded backfill is justified

- Severity: `P2`
- Expected behaviour: new and invalidated accepted signals are embedded exactly once; an upgrade must not force a full-user rebuild or re-embed unchanged rows.
- Actual behaviour: migration `0016` is upgrade-safe and leaves pre-existing signals with `NULL` embeddings. New worker-processed signals receive vectors atomically, but there is no automatic historical-vector backfill.
- Relevant files: `backend/migrations/0016_signal_embeddings.sql`, `backend/app/modules/processing/service.py`, `backend/app/modules/processing/repository.py`.
- Reproducible test: upgrade a database containing `entry_signals`; existing rows remain valid with null embedding metadata, while newly processed accepted signals store 1,536-dimension vectors.
- Proposed smallest fix: defer a bounded, null-only backfill until a product query requires historical vectors. It must reuse encrypted signal payloads without rerunning Luna, obey queue budgets, and never overwrite an existing vector.
- Status: deferred for upgrade backfill only. The authenticated hardening dataset created 61 new accepted signals across baseline and update phases, all with matching embeddings; all excluded inputs created zero vectors.

## Fix order

1. RF-AUDIT-000 — synthesis enqueue runtime repair.
2. RF-AUDIT-001 — pgvector signal embeddings.
3. RF-AUDIT-002 — exact recalculation eligibility.
4. RF-AUDIT-003A — strict persisted-candidate refresh boundary.
5. RF-AUDIT-003 — bounded authenticated hardening runner and final diff evidence.

No P0 defect is currently reproduced. All four P1 defects found in this audit are fixed with targeted regressions and authenticated/database-backed proof; P2 scheduling and upgrade-backfill items remain explicitly deferred.
