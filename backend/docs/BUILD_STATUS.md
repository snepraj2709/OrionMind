# Backend build status

## Stage gates

| Stage                             | Status                               | Implementation evidence                                  | Review passes | Verification                                                                                                                  | Blockers                                                             |
| --------------------------------- | ------------------------------------ | -------------------------------------------------------- | ------------: | ----------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| 0 — Reference contract            | Verified complete                    | `reference-manifest.md`, blueprint, trimmed OpenAPI      |             2 | 13 operations; sole anonymous health; 41 reachable refs; zero dangling/unreachable refs; source parity and diff hygiene pass  | None                                                                 |
| 1 — Shared platform               | Verified complete                    | HTTP/auth/config/UoW/health platform                     |             3 | 25 focused/full non-live tests; compile/import; version, privacy, Docker build/runtime, and hygiene checks pass               | None                                                                 |
| 2 — Database/profile/account      | Verified complete; live proof waived | Fresh schema, migration runner, profile/account feature  |             3 | 45 full tests; clean concurrent install; real SQLAlchemy API; two-user RLS, grants, constraints, checksums, and cascades pass | User explicitly waived unavailable live Supabase proof on 2026-07-21 |
| 3 — Processing core               | Verified complete                    | Strict extraction, bounded provider, atomic RPCs         |             3 | 61 full tests; structured validation, fallback ceiling, source spans, threshold, rollback, stale-token and concurrency pass   | None                                                                 |
| 4 — Drafts/text/list/detail/retry | Verified complete                    | AES-GCM drafts and complete owner text lifecycle         |             3 | 70 full tests; encryption, replay, concurrency, pagination, detail, retry, RLS and privacy proofs pass                        | None                                                                 |
| 5 — Voice/past imports            | Locally verified                     | Streaming voice boundary and durable worker queue        |             3 | 97 full tests; genuine audio families, cleanup, replay, encryption, queue tokens, RLS/grants, heartbeat and recovery pass     | Live Supabase proof waived                                           |
| 6 — Contract freeze/release proof | Locally verified; live proof waived  | Frozen artifact, limits, readiness, worker, release docs |             3 | 127 full tests; OpenAPI/route, rate, readiness/recovery, privacy, Docker build/runtime and migration parity pass              | Live two-account Supabase proof waived; deployment not authorized    |
| 7 — Reflection Engine P0-01–P0-04 | Locally verified through P0-04       | Combined redacted entry analysis on the shared queue     |             2 | 170 full tests; quality, privacy, Responses API, exact offsets, atomic apply, stale claims, backfill, and schema parity pass  | P0-05 and later are not implemented; production KMS remains blocked  |

## P0-04 combined entry-analysis evidence

- The shared `entry_processing` worker decrypts locally, computes deterministic quality features,
  locks and updates the encrypted PII vault, sends only redacted text to the configured
  `gpt-5.6-luna` analyzer, validates strict combined output, and restores exact original offsets.
- Deterministic garbage, microphone tests, and accepted-history exact/near duplicates create an
  auditable excluded analysis without a provider call. Semantic uncertain/excluded results retain
  legacy extraction but create no signals and increment no reflection counters.
- The provider uses `client.responses.parse` with SDK retries disabled, no tools,
  `truncation="disabled"`, a keyed safety identifier, and `store=False`. Closed signal, need, loop,
  theme, entry-kind, eligibility, and reason-code catalogs reject unknown values and extra fields.
- `apply_combined_entry_processing_job` is the sole entry-worker success path. It verifies the
  current claim, takes the per-user advisory lock, closes duplicate races, and applies legacy
  extraction, quality audit, accepted signals, entry/job completion, historical approval state,
  and reflection counters in one transaction. The obsolete legacy-only apply RPC is removed.
- Focused P0-04 processing/quality/privacy/database matrix: 64 passed. Full backend suite: 170
  passed with one third-party pending-deprecation warning from Starlette's multipart import.

## P0-03 shared processing queue evidence

- Text and voice requests persist encrypted content, return the unchanged `EntryDetail` DTO in
  `pending`, and make no extraction-provider call in the web process.
- Historical imports create their audit row and one `entry_processing` job atomically. Generalized
  claim, heartbeat, failure, stale recovery, and completion RPCs mirror the audit status, while
  successful historical candidates retain `past_import_auto` approval.
- Failed-entry retry resets the same source-version job to `pending` with zero attempts. Repeated
  submission/enqueue remains one effective job.
- `run_processing_worker.py` is the only processing-worker entry point. Web startup performs
  readiness checks only; worker startup and its recurring loop own stale recovery.
- Focused P0-03 matrix: 64 passed. Full backend suite: 147 passed with one third-party pending
  deprecation warning from Starlette's multipart import.

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
- At the Stage 2 gate, `supabase_schema.sql` was byte-identical to
  `migrations/0001_foundation.sql`; later stages regenerate it as the ordered migration concatenation.
- Existing-user bootstrap and new-user trigger pass; fixed Default 8 contains exactly eight rows.
- Real HTTP -> controller -> service -> repository -> SQLAlchemy UoW profile read/partial-update pass.
- Direct two-user profile select/update isolation, foreign-parent rejection, invalid-envelope rejection,
  revoked anon/worker/derived/queue access, and Auth-rooted table cascades pass.
- Account HTTP contract, same/other/invalid proof, safe retryable provider failure, and already-missing
  idempotence pass through isolated Supabase gateway doubles.
- Reference HEAD/status recheck: `1a993c3438460dcdf5d0680a272e43c6c09e34e3`, clean.
- Final local findings-first review: zero open actionable local findings.
- No target `.env` or Supabase/database credentials were configured, so real two-account Supabase API
  RLS and Auth identity deletion/cascade proof was not run. The user explicitly waived this live proof
  on 2026-07-21 and directed execution to continue through Stage 6; the local disposable proof remains
  the Stage 2 gate evidence.

## Stage 3 findings

### ST3-001

Finding ID: ST3-001
Severity: High
Requirement: Past-import provenance and automatic approval must be a worker-only capability.
Evidence: The initial owner extraction RPC accepted a caller-controlled `past_import` boolean and used
it to select approved candidate state.
Impact: An authenticated browser with a processing token could attempt to create auto-approved
derived rows outside the durable import worker boundary.
Fix: The owner RPC now rejects `past_import=true`; Stage 5 must provide a separate worker-only RPC.
Regression test: Direct authenticated invocation with the flag fails and leaves the processing entry
and all derived tables unchanged.
Status: fixed

### ST3-002

Finding ID: ST3-002
Severity: Medium
Requirement: Schema parity and migration-lock tests must remain valid as the ordered migration set grows.
Evidence: Stage 2 assertions assumed exactly one migration and one applied filename.
Impact: Correct Stage 3 installs failed the test even though both migrations were serialized and recorded.
Fix: Assert contiguous versions, complete ledger rows, one concurrent runner applying the entire current
set, and exact ordered schema concatenation.
Regression test: Concurrent clean install and parity assertions pass with both migrations.
Status: fixed

### ST3-003

Finding ID: ST3-003
Severity: Low
Requirement: Negative database tests must prove rollback without leaving their connection aborted.
Evidence: Initial stale-token and constraint tests caught SQL errors inside a savepoint context, causing
the context to attempt release instead of observing the error and rolling back.
Impact: The harness failed after the intended database rejection and could not inspect rollback state.
Fix: Move exception assertions outside transaction contexts so psycopg rolls back the savepoint.
Regression test: Atomic rollback and stale-token checks pass and subsequent assertions use the same connection.
Status: fixed

## Stage 3 verification evidence

- Full non-live plus PostgreSQL 15 disposable suite: 61 passed; one expected pinned-Starlette warning.
- Strict Pydantic output rejects extra fields, invalid modes, non-contiguous tiers, duplicate keys,
  unknown config keys/segments, non-finite confidence, and bounded-output violations.
- Exact source spans and 50,000-scalar/200,000-byte provider cap pass without truncating stored source.
- Primary success uses one request; only eligible retryable failure reaches exactly one fallback; SDK
  retries are zero and connection/response/total timeouts are explicit.
- Reflection threshold `0.80` is inclusive; normal candidate rows remain `pending_approval`.
- Atomic RPC proof covers success, derived-row rollback, stale/duplicate token rejection, one winner
  under concurrent commits, safe failed transition, and a new retry token.
- Provider and source privacy scan: no journal text, prompts, parsed output, token, or provider payload logging.
- Runtime inventory remains the four Stage 2 operations; Stage 3 adds no public routes.
- Final Stage 3 findings-first review: zero open actionable findings.

## Stage 4 findings

### ST4-001

Finding ID: ST4-001
Severity: High
Requirement: Internal list results must carry decrypted page content through a declared typed boundary.
Evidence: The first list implementation attempted to attach plaintext dynamically to a frozen slotted
summary dataclass.
Impact: Every non-empty list request would fail at runtime before response mapping.
Fix: Added an explicit internal-only `plaintext` field to `EntrySummaryData`; public views expose only
the exact unsuffixed 200-code-point preview.
Regression test: Unicode preview and empty/one/two/three-theme page mapping plus the real database list pass.
Status: fixed

### ST4-002

Finding ID: ST4-002
Severity: Medium
Requirement: Text submission accepts no idempotency header or caller-owned operational identity.
Evidence: Strict JSON rejected operational fields, but the initial controller silently ignored an
`Idempotency-Key` header.
Impact: Clients could incorrectly infer that the key controlled text-entry replay semantics.
Fix: Reject `Idempotency-Key` on `POST /api/v1/entry` with the canonical validation error; replay remains
exclusively the saved-draft fingerprint and source-draft transition.
Regression test: Header rejection occurs without entry creation or provider invocation.
Status: fixed

### ST4-003

Finding ID: ST4-003
Severity: High
Requirement: Malformed provider output and persistence failures must use safe stable boundary errors.
Evidence: Only the provider adapter's explicit unavailable exception was translated; materialization
validation could fall through as a generic 500.
Impact: The response code diverged from the provider-failure contract and obscured retry semantics.
Fix: Map structured-output validation to safe `502 PROVIDER_UNAVAILABLE`, map internal processing
dependency failures to retryable `503 SERVICE_UNAVAILABLE`, and preserve typed domain errors.
Regression test: Provider failure marks the exact token failed, returns a sanitized 502, and retry succeeds.
Status: fixed

## Stage 4 verification evidence

- Full non-live plus PostgreSQL 15 disposable suite: 70 passed; one expected pinned-Starlette warning.
- Canonicalization proves Unicode 14 NFC, CR/CRLF to LF, strict UTF-8, frozen six-character edge trim,
  exact 200,000-scalar bound, and non-ASCII whitespace preservation.
- AES-256-GCM/HKDF envelope round-trip passes; wrong user, record, key, tag, shape, or decode produces
  one content-unavailable result; owner/date fingerprints are deterministic and scoped.
- Active draft ciphertext contains no plaintext, repeated save retains backend identity, blank PUT and
  DELETE clear only active rows, submitted ciphertext is null, malformed draft returns safe 503.
- Matching text creates once; concurrent lost-response submission returns one 201 and one 200 with one
  provider call; completed replay calls no provider; new identical draft creates a distinct entry.
- Missing/mismatched draft returns 409 without mutation; text rejects operational body fields and
  `Idempotency-Key`.
- User-timezone date derivation, stable pagination, exact multibyte preview, batch theme loading, cache
  header, full detail, empty and one/two/three-theme shapes, and list zero-AI behavior pass.
- Foreign/missing detail is 404 before decrypt; malformed owner envelope is one safe 500.
- Failed replay and explicit retry share token claim semantics; concurrent retry has one claimant and
  one provider call; stale/current processing-token database proofs remain green.
- Runtime inventory is exactly the Stage 4 eleven operations; no review/library/theme/journey routes.
- Final Stage 4 findings-first review: zero open actionable findings.

## Stage 5 findings

### ST5-001

Finding ID: ST5-001
Severity: High
Requirement: Voice parsing must remain incremental and bounded while owning exactly one temporary file.
Evidence: The initial signature check read the complete upload into memory, and multipart overhead had
no independent ceiling after exempting voice from the general 1 MiB limit.
Impact: A valid 25 MiB upload caused a second full-memory copy, while oversized headers or framing could
bypass the file-byte counter.
Fix: Read only the 16-byte signature and enforce a 64 KiB maximum multipart overhead in addition to the
exact incremental 25 MiB audio limit.
Regression test: Exact/over byte boundaries, malformed multipart, cancellation, and idempotent cleanup.
Status: fixed

### ST5-002

Finding ID: ST5-002
Severity: High
Requirement: Durable queue claims and completion must be current-token-only, recoverable, and idempotent.
Evidence: The first worker execution reproduced an ambiguous PL/pgSQL output-column reference, and a
lost completion response could not be replayed after the active processing token was cleared.
Impact: Workers could not claim queued imports, and successful work might be retried unnecessarily after
an ambiguous response.
Fix: Qualify queue/entry columns, persist a completion token, accept exact-token completion replay, add
active heartbeats, and retain the three-attempt stale-recovery state machine.
Regression test: Claim, heartbeat, wrong-token rejection, exact completion replay, interruption recovery,
attempt exhaustion, worker-only RPCs, and denied worker table access on PostgreSQL 15.
Status: fixed

### ST5-003

Finding ID: ST5-003
Severity: High
Requirement: Audio duration enforcement must resist forged or absent container metadata.
Evidence: The first validation pass trusted FFprobe's container duration and used FFmpeg only as a
decode-success check.
Impact: A container reporting a short duration could carry more than 20 minutes of decodable audio.
Fix: Measure decoded output time through owned FFmpeg progress, require positive decoded duration, and
enforce the limit against both reported and decoded durations.
Regression test: Exact/over duration, forged-short metadata, missing metadata with positive decode,
missing audio streams, and genuine WAV/MP3/M4A/WebM/OGG containers.
Status: fixed

### ST5-004

Finding ID: ST5-004
Severity: Medium
Requirement: Voice retains its own bounded upload/provider lifecycle and must not block the async server.
Evidence: The general 30-second request timeout still wrapped voice, unlike the selected reference, and
synchronous preparation/processing ran directly inside the async controller.
Impact: Slow valid uploads could be cancelled by the wrong deadline and synchronous database/provider
work could block unrelated requests.
Fix: Exempt only the exact voice path from the general deadline, preserve route-owned subprocess/provider
bounds, and offload synchronous service calls to the thread pool.
Regression test: Non-voice timeout remains canonical, voice reaches route-owned validation, cancellation
abandons the action claim, and replay consumes zero ASGI body events.
Status: fixed

## Stage 5 verification evidence

- Full non-live plus PostgreSQL 15 disposable suite: 97 passed; one expected pinned-Starlette warning.
- Runtime inventory is exactly all 13 selected operations; health remains the sole anonymous operation.
- Genuine WAV, MP3/MPEG, MP4/M4A, WebM, and OGG files pass declared/signature/decode validation;
  mismatches, unsupported, empty, truncated, header-only, duplicate, undeclared, and incomplete inputs fail.
- Exact 25 MiB and 20-minute boundaries, forged/missing duration, FFmpeg/FFprobe timeout ownership,
  disconnect/cancellation, persistence/provider failures, and temporary-file cleanup pass.
- Voice idempotency proves one 201, same-action 200 replay before any ASGI body event, date conflict 409,
  new-key new recording, encrypted transcript-only storage, and retry without retranscription.
- Past import proves strict schema, owner-local inclusive ten-year range, leap-safe shift, pre-account dates,
  owner/date/content fingerprint scope, duplicate 409, atomic entry/work creation, and zero request-time AI.
- Worker proof covers narrow claim tokens, ID, attempts, active heartbeat, wrong/stale-token rejection,
  exact-token idempotent completion, automatic past-import candidate approval provenance, stale recovery,
  attempt exhaustion, two-user isolation, and denied browser/worker capability escalation.
- Source/log/storage scan found no journal text, transcript, raw audio, client filename, token, provider
  payload, encryption envelope, or secret logging.
- User explicitly waived unavailable live Supabase proof on 2026-07-21; all Stage 5 database proof used
  the local disposable PostgreSQL 15 container only.
- Final Stage 5 findings-first review: zero open actionable local findings.

## Stage 6 findings

### ST6-001

Finding ID: ST6-001
Severity: High
Requirement: Local docs and generated artifacts must be the reviewed trimmed OpenAPI, with route drift
prevented.
Evidence: The app generated a fresh framework schema at runtime and had no assertion tying registered
methods and paths to the selected 13-operation inventory.
Impact: DTO or route changes could silently publish a contract different from the reviewed YAML.
Fix: Package a semantic JSON rendering of the trimmed YAML, serve that exact artifact locally, and assert
the exact route/method set during composition.
Regression test: YAML/JSON semantic parity, 41-reference closure, runtime response equality, exact 13
operations, and injected-route drift rejection.
Status: fixed

### ST6-002

Finding ID: ST6-002
Severity: High
Requirement: Every endpoint class requires an integer `Retry-After` limit with an explicit scale-out
constraint.
Evidence: No limiter existed at the Stage 5 gate.
Impact: Expensive voice, processing, import, retry, account, and read operations had no backend abuse
boundary.
Fix: Add owner/IP-scoped sliding-window classes before body parsing, bounded inactive-scope pruning,
production fail-closed enablement, and a one-instance/one-worker constraint.
Regression test: Every class limit and operation mapping, auth-before-limit ordering, voice
limit-before-body, health IP limit, and integer retry headers.
Status: fixed

### ST6-003

Finding ID: ST6-003
Severity: High
Requirement: Startup must check dependencies and recover stale work without running migrations.
Evidence: Lifespan previously yielded immediately and disposed pools only at shutdown.
Impact: The service could accept traffic with unavailable databases and leave interrupted imports
unrecovered until an operator intervened.
Fix: Add connect/query deadlines, application/worker `SELECT 1`, current worker-RPC stale recovery with a
statement timeout, and fail-closed startup. `/health` remains opaque.
Regression test: Readiness execution, bounded timeout, opaque liveness, and real PostgreSQL startup
recovery of an interrupted queue claim.
Status: fixed

### ST6-004

Finding ID: ST6-004
Severity: High
Requirement: Durable historical work needs an executable restricted worker lifecycle.
Evidence: Worker claim/service code existed but the container exposed no worker process entrypoint.
Impact: Accepted `202` imports would remain pending unless application internals were invoked manually.
Fix: Add a signal-aware polling worker with restricted UoWs, periodic recovery, safe event-only logs, and
deployment topology documentation.
Regression test: Worker module compile/import, queue claim/heartbeat/completion/recovery integration, and
container packaging proof.
Status: fixed

### ST6-005

Finding ID: ST6-005
Severity: High
Requirement: The image must not receive local secrets and must prove code validity before switching to
the non-root runtime user.
Evidence: The first release Docker context had no `.dockerignore`; a runtime compile probe also showed
that `/app` is intentionally non-writable after `USER orion`.
Impact: A local `.env` could enter the Docker build context, and compilation was not an explicit image
build gate.
Fix: Exclude local env/test/cache/input files from the context and compile application, scripts, and
server during image build before selecting UID 10001.
Regression test: Clean Docker build, non-root API runtime, FFprobe presence, health 200, and canonical
404s for docs, metrics, and legacy Auth paths.
Status: fixed

## Stage 6 verification evidence

- Full non-live plus PostgreSQL 15 disposable suite: 127 passed; one expected pinned-Starlette warning.
- Python 3.11 compile/import and `git diff --check`: passed.
- Trimmed YAML and packaged JSON are semantically equal: 13 operations, 41 unique reachable local
  references, zero dangling references, and no unrelated path.
- Runtime/frozen OpenAPI equality, exact route assertion, sole anonymous health, and absent docs in
  production mode pass.
- All endpoint classes return integer `Retry-After`; auth precedes limiting and limiting precedes body
  parsing. In-process limits are locked to one API instance/worker and Redis-compatible shared limiting
  is documented as the prerequisite for scale-out.
- Database connection/query readiness and worker recovery are bounded. Startup runs no migration.
- Optional OTLP tracing instruments FastAPI and SQLAlchemy only when explicitly enabled; no public
  metrics route exists and privacy scans remain clean.
- Docker image `orion-backend:stage6` builds with FFmpeg/FFprobe, runs as UID 10001 with one Uvicorn
  worker, returns exact health, and returns canonical 404 for OpenAPI, metrics, and legacy Auth paths.
- Controlled advisory-locked migration and separate API/worker deployment commands are documented.
- Reference recheck remains `1a993c3438460dcdf5d0680a272e43c6c09e34e3` with a clean worktree.
- User explicitly waived live proof on 2026-07-21. Two-account Supabase API/direct-RLS, live Auth
  deletion/cascade, and live cross-user ciphertext/decryption evidence remain pending; deployment was
  not attempted.
- Final Stage 6 and whole-project findings-first review: zero open actionable local findings.

## Final route evidence

Populated during Stage 6.

| Method | Path                               | Auth proof                     | Schema proof                           | Service proof                         | DB/RLS proof                        | Negative proof                         | Status                              |
| ------ | ---------------------------------- | ------------------------------ | -------------------------------------- | ------------------------------------- | ----------------------------------- | -------------------------------------- | ----------------------------------- |
| GET    | `/health`                          | Sole anonymous operation       | `HealthResponse` frozen/runtime parity | Fixed controller result               | No dependency read                  | Opaque body; IP rate limit             | Locally verified                    |
| GET    | `/api/v1/profile`                  | Verified bearer UUID           | `Profile` strict DTO                   | Profile read service                  | Owner UoW + forced RLS              | Missing/other owner denied             | Locally verified                    |
| PATCH  | `/api/v1/profile`                  | Verified bearer UUID           | `ProfileUpdate` strict/partial         | Canonical validation/update           | Owner RPC/UoW + forced RLS          | Null/extra/invalid timezone            | Locally verified                    |
| DELETE | `/api/v1/account`                  | Bearer + same-user fresh proof | Exact deletion request                 | Idempotent Auth deletion              | Auth-root cascade                   | Other/invalid proof; retryable failure | Locally verified; live Auth pending |
| GET    | `/api/v1/entries`                  | Verified bearer UUID           | Bounded `EntryPage`                    | Decrypt/map without AI                | Owner select + forced RLS           | Stable pagination; no foreign rows     | Locally verified                    |
| GET    | `/api/v1/entry/draft`              | Verified bearer UUID           | Nullable strict draft response         | Owner decrypt                         | Active-owner RLS                    | Corrupt/foreign draft safe             | Locally verified                    |
| PUT    | `/api/v1/entry/draft`              | Auth before JSON               | Exact content-only DTO                 | Canonical encrypt/fingerprint         | Atomic owner draft RPC              | Blank clear; extra/owner fields denied | Locally verified                    |
| DELETE | `/api/v1/entry/draft`              | Verified bearer UUID           | Fixed nullable response                | Active draft discard                  | Owner discard RPC                   | Submitted/foreign rows unchanged       | Locally verified                    |
| POST   | `/api/v1/entry`                    | Auth before JSON               | Exact text DTO                         | Draft replay + processing             | Atomic draft-submit/extraction RPCs | Mismatch 409; header/IDs denied        | Locally verified                    |
| POST   | `/api/v1/past-entries`             | Auth before JSON               | Exact date/content + 202               | Encrypt/fingerprint/queue only        | Atomic owner queue RPC              | Range/duplicate/extra denied           | Locally verified                    |
| POST   | `/api/v1/entries/voice`            | Auth/limit/replay before body  | Frozen MIME/query/header contract      | Stream, validate, transcribe, process | Atomic action/entry RPC + RLS       | Mismatch/limits/cancel cleanup         | Locally verified                    |
| GET    | `/api/v1/entries/{entry_id}`       | Verified bearer UUID           | Strict `EntryDetail`                   | Owner decrypt + view mapping          | Owner tables + forced RLS           | Foreign/missing 404 before decrypt     | Locally verified                    |
| POST   | `/api/v1/entries/{entry_id}/retry` | Verified bearer UUID           | Strict `EntryDetail`                   | Stored-source retry                   | Current-token claim/extraction RPC  | Nonfailed/concurrent/foreign rejected  | Locally verified                    |
