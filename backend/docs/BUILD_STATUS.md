# Backend build status

## Stage gates

| Stage                             | Status                               | Implementation evidence                                 | Review passes | Verification                                                                                                                  | Blockers                                                                                                                                        |
| --------------------------------- | ------------------------------------ | ------------------------------------------------------- | ------------: | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 0 — Reference contract            | Verified complete                    | `reference-manifest.md`, blueprint, trimmed OpenAPI     |             2 | 13 operations; sole anonymous health; 41 reachable refs; zero dangling/unreachable refs; source parity and diff hygiene pass  | None                                                                                                                                            |
| 1 — Shared platform               | Verified complete                    | HTTP/auth/config/UoW/health platform                    |             3 | 25 focused/full non-live tests; compile/import; version, privacy, Docker build/runtime, and hygiene checks pass               | None                                                                                                                                            |
| 2 — Database/profile/account      | Locally verified; live proof pending | Fresh schema, migration runner, profile/account feature |             3 | 45 full tests; clean concurrent install; real SQLAlchemy API; two-user RLS, grants, constraints, checksums, and cascades pass | Live two-account Supabase Auth/RLS/account-deletion proof unavailable: no target credentials and no live/shared database mutation authorization |
| 3 — Processing core               | Not started                          |                                                         |             0 |                                                                                                                               |                                                                                                                                                 |
| 4 — Drafts/text/list/detail/retry | Not started                          |                                                         |             0 |                                                                                                                               |                                                                                                                                                 |
| 5 — Voice/past imports            | Not started                          |                                                         |             0 |                                                                                                                               |                                                                                                                                                 |
| 6 — Contract freeze/release proof | Not started                          |                                                         |             0 |                                                                                                                               |                                                                                                                                                 |

## Stage 0 findings

### ST0-001

Finding ID: ST0-001
Severity: High
Requirement: The trimmed OpenAPI must preserve selected-operation examples and complete reference
closure without unrelated components.
Evidence: The preserved input removed selected-operation example references and their transitive
components. It also omitted the runtime-frozen past-import cache header and idempotency whitespace
constraint.
Impact: The review artifact could not prove the complete selected-operation contract.
Fix: Restored only `CompletedEntry` and `CompletedAudioEntry` plus their transitive examples, added
the past-import cache header, and froze the no-edge-whitespace key constraint.
Regression test: YAML parse, local `$ref` resolver, selected-operation inventory, and excluded-path
check.
Status: fixed

### ST0-002

Finding ID: ST0-002
Severity: Medium
Requirement: The manifest must describe the exact current reference snapshot and checksums.
Evidence: The preserved blueprint described a formerly observed untracked file, but the Stage 0
reference worktree is now clean and no manifest existed.
Impact: A later implementer could audit against a different source state.
Fix: Added `reference-manifest.md` with canonical paths, HEAD, dirty state, checksums, and versions;
updated the blueprint audit record.
Regression test: Re-run canonical path, reference HEAD/status, and checksum commands.
Status: fixed

### ST0-003

Finding ID: ST0-003
Severity: Medium
Requirement: The blueprint must include an environment-variable matrix.
Evidence: The preserved blueprint documented versions but had no environment-variable matrix.
Impact: Production settings and secret boundaries were not implementation-ready.
Fix: Added the runtime/test matrix with requiredness, secrecy, and validation.
Regression test: Findings-first document review against Stage 0 item 13.
Status: fixed

### ST0-004

Finding ID: ST0-004
Severity: High
Requirement: Approved-source discrepancies must be resolved before application implementation.
Evidence: Blueprint items 4-9 explicitly requested decisions for profile, account deletion, draft
decryption, global transport errors, past-import headers/queue saturation, and idempotency-key
whitespace.
Impact: Implementations could expose incompatible statuses, headers, and safe error codes.
Fix: Froze explicit resolutions using the owner-designated execution contract and the documented
source order; retained the discrepancies as historical audit evidence.
Regression test: Contract review plus later HTTP-boundary tests for each resolution.
Status: fixed

### ST0-005

Finding ID: ST0-005
Severity: Low
Requirement: Contract repairs must not introduce behavior or components absent from the approved
selected-operation closure.
Evidence: The first repair pass added an unnecessary `EntryDetail` else branch and an unreferenced
zero-theme example while restoring the missing selected-operation examples.
Impact: The trim would contain review-created schema behavior and an unreachable component.
Fix: Removed the branch and unreferenced example; retained only source-backed, reachable components.
Regression test: Reachability walk reports 41 reachable components and `extras=[]`; local reference
resolution reports zero dangling references.
Status: fixed

## Stage 0 verification evidence

- Ruby/Psych YAML parse: passed.
- Selected inventory assertion: 13 exact method/path pairs.
- Anonymous-security assertion: only `GET /health`.
- Selected reference operation-ID comparison: passed.
- Local `$ref` resolution: 41 unique references, zero dangling.
- Component reachability: 41 reachable, zero extra.
- Excluded public path scan: zero matches.
- Blueprint section audit: all required items, including the environment matrix, present.
- `git diff --check`: passed.
- Reference HEAD/status recheck: `1a993c3438460dcdf5d0680a272e43c6c09e34e3`, clean.
- Final Stage 0 findings-first review: zero open actionable findings.

## Stage 1 findings

### ST1-001

Finding ID: ST1-001
Severity: High
Requirement: Provider payloads, content, tokens, and secrets must never enter logs.
Evidence: The unexpected-exception handler used `logger.exception`, which serializes exception
messages and tracebacks even though the HTTP response was sanitized.
Impact: Provider or persistence exceptions could leak sensitive text into application logs.
Fix: Log only request ID, method, and path without exception text or traceback.
Regression test: `test_unexpected_exception_text_is_not_logged`.
Status: fixed

### ST1-002

Finding ID: ST1-002
Severity: High
Requirement: HTTP failures must use the canonical error envelope and request ID.
Evidence: The handler registered the FastAPI HTTP exception subclass, while router-generated 404s
are Starlette HTTP exceptions.
Impact: Unknown routes could return the framework `detail` shape.
Fix: Register the shared handler for `starlette.exceptions.HTTPException`.
Regression test: production root/docs/schema/legacy route cases assert `NOT_FOUND` envelopes.
Status: fixed

### ST1-003

Finding ID: ST1-003
Severity: High
Requirement: Production settings validation must fail closed for encryption and fingerprint keys.
Evidence: Key-map validation checked only JSON membership, not canonical padded base64 or 32-byte
decoded length.
Impact: Production could start with unusable key material and fail after accepting traffic.
Fix: Validate every configured key as canonical padded base64 decoding to exactly 32 bytes.
Regression test: invalid production key material raises a settings validation error.
Status: fixed

### ST1-004

Finding ID: ST1-004
Severity: High
Requirement: The 1 MiB transport limit applies to non-voice requests; voice owns an incremental
25 MiB limit.
Evidence: The general middleware originally applied its limit to every path.
Impact: Valid audio would be rejected before the voice controller could enforce its streaming
format, size, duration, and cleanup contract.
Fix: Exempt only the exact voice path from the general limit; Stage 5 supplies its bounded parser.
Regression test: non-voice oversize is 413 while the exact voice path reaches route-owned handling.
Status: fixed

### ST1-005

Finding ID: ST1-005
Severity: Medium
Requirement: Shared platform must expose dependency seams for database, Supabase, OpenAI, and
encryption.
Evidence: Database, Supabase, and OpenAI seams existed but no typed content-cipher seam was present.
Impact: Entry services would otherwise couple directly to an encryption implementation.
Fix: Added the `ContentCipher` protocol under shared security.
Regression test: compile/import and architecture review.
Status: fixed

### ST1-006

Finding ID: ST1-006
Severity: High
Requirement: Production dependency endpoints and database role separation must fail closed.
Evidence: Initial settings validation required nonempty URL strings but did not constrain Supabase
to HTTPS, database URLs to the psycopg PostgreSQL driver, or app/worker URLs to distinct logins.
Impact: A deployment could use insecure Auth transport or collapse user and worker capabilities.
Fix: Require HTTPS Supabase, `postgresql+psycopg` URLs with login roles, distinct app/worker URLs,
and HTTPS OTLP when enabled.
Regression test: production settings reject insecure Supabase, wrong DB driver, shared DB URL, and
invalid enabled telemetry configuration.
Status: fixed

## Stage 1 verification evidence

- Exact dependency installation under Python 3.11.15: passed; all requested versions asserted.
- Focused platform suite: 25 passed.
- Full non-live suite at this gate: 25 passed.
- Compile/import: passed; `server:app` title is `Orion profile and entry API`.
- Runtime inventory at this stage: only `GET /health`; response exactly `{"status":"ok"}`.
- Local docs-on and bearer metadata: passed.
- Production root/docs/Redoc/schema/legacy absence: passed with canonical 404 envelopes.
- Auth-before-malformed JSON/multipart, CORS DELETE preflight, body limit, timeout, request ID, and
  retry-header cases: passed.
- User UoW commit/rollback and transaction-local claims; worker-role setup: passed.
- Secret/payload log and source architecture scans: passed.
- Docker image `orion-backend:stage1`: built successfully with Python 3.11 slim and FFmpeg.
- Docker runtime smoke: `/health` 200 exact body; `/docs` and `/openapi.json` 404.
- Final Stage 1 findings-first review: zero open actionable findings.

## Stage 2 findings

### ST2-001

Finding ID: ST2-001
Severity: High
Requirement: Authentication must run before request parsing on every protected product route.
Evidence: The initially nested profile router retained FastAPI's default route class instead of the
parent router's pre-body protected route class, so valid bearer requests reached the dependency
without an authenticated context.
Impact: All Stage 2 product operations returned `401`, and malformed bodies were not being tested at
the real feature boundary.
Fix: Made the profile feature router explicitly use `ProtectedAPIRoute`.
Regression test: All profile/account HTTP cases pass, including auth-before-malformed-body proof.
Status: fixed

### ST2-002

Finding ID: ST2-002
Severity: High
Requirement: Persistent entry and active-draft ciphertext must be a strict canonical envelope v2.
Evidence: The first schema pass accepted arbitrary JSON objects in entry and draft envelope columns.
Impact: Invalid, non-decryptable, or non-canonical ciphertext could cross the database boundary.
Fix: Added an immutable strict eight-key validator with exact algorithms, key IDs, canonical base64,
byte lengths, ciphertext bounds, and table constraints; active drafts also require keyed fingerprints.
Regression test: Fresh-install proof rejects an invalid envelope and accepts the exact valid shape.
Status: fixed

### ST2-003

Finding ID: ST2-003
Severity: High
Requirement: Derived and queue writes are execute-only capabilities; the worker role is restricted.
Evidence: The first schema pass granted the worker role direct write access and permissive policies on
all user-owned tables.
Impact: Worker code could bypass the transactional RPC boundaries required by later stages.
Fix: Removed worker table grants and policies, retaining only schema usage until narrowly scoped
`SECURITY DEFINER` RPC execution is granted in later stages.
Regression test: Direct worker access to the queue table fails with insufficient privilege.
Status: fixed

### ST2-004

Finding ID: ST2-004
Severity: High
Requirement: The transitive entry-detail tables must preserve the frozen public data vocabulary.
Evidence: The first schema pass represented derived idea/memory/reflection text as envelopes, used
`pending` instead of `pending_approval`, and stored theme tiers as integers.
Impact: Later detail mapping and structured persistence would diverge from the frozen response contract.
Fix: Restored bounded derived text/activity fields, exact candidate statuses and reflection types, and
the `primary`/`secondary`/`tertiary` tier vocabulary; corrected the fixed config display name.
Regression test: Schema constraint and exact Default 8 catalog assertions in the disposable proof.
Status: fixed

## Stage 2 verification evidence

- Full non-live plus disposable-database suite: 45 passed; one expected pinned-Starlette multipart
  deprecation warning.
- Compile/import pass under Python 3.11.15.
- Fresh PostgreSQL 15 install from two concurrent runners: exactly one apply; the other observes the
  checksum ledger after the advisory lock.
- Migration rerun is idempotent; a tampered checksum fails closed.
- `supabase_schema.sql` is byte-identical to `migrations/0001_foundation.sql`.
- Existing-user bootstrap and new-user trigger pass; fixed Default 8 contains exactly eight rows.
- Real HTTP -> controller -> service -> repository -> SQLAlchemy UoW profile read/partial-update pass.
- Direct two-user profile select/update isolation, foreign-parent rejection, invalid-envelope rejection,
  revoked anon/worker/derived/queue access, and Auth-rooted table cascades pass.
- Account HTTP contract, same/other/invalid proof, safe retryable provider failure, and already-missing
  idempotence pass through isolated Supabase gateway doubles.
- Reference HEAD/status recheck: `1a993c3438460dcdf5d0680a272e43c6c09e34e3`, clean.
- Final local findings-first review: zero open actionable local findings.
- Live gate remains open: no target `.env` or Supabase/database credentials are configured, and no
  authorization was given to mutate a live/shared project. Real two-account Supabase API RLS and Auth
  identity deletion/cascade proof was therefore not run.

## Final route evidence

Populated during Stage 6.

| Method | Path | Auth proof | Schema proof | Service proof | DB/RLS proof | Negative proof | Status |
| ------ | ---- | ---------- | ------------ | ------------- | ------------ | -------------- | ------ |
