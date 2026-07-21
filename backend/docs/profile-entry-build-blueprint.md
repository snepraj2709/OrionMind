# Profile and entry backend build blueprint

Status: Stage 0 reviewed contract; later work remains subject to the staged gates in
`Implementation_doc.md`

Target: fresh Python 3.11 / FastAPI backend in `backend/`

Reference: read-only `Orion-Web-App`

## Audit record and authority

The initial documentation audit observed the reference transition from
`f691c29050ff6c336ce78404276004f68ed9cef2` to the owner-created commit
`1a993c3438460dcdf5d0680a272e43c6c09e34e3`. Stage 0 resolved the reference at the latter commit
and observed a clean worktree. Exact paths, checksums, and the observation time are recorded in
`reference-manifest.md`. The auditor did not write to the reference.

The frozen OpenAPI 1.5.0 contract is the primary wire-format source. Current routes, controllers,
services, repositories, migrations, and tests define externally observable behavior where the
OpenAPI is silent. Historical discrepancies and their explicit Stage 0 resolutions are recorded in
section 13.

Required runtime versions:

- Python 3.11; PostgreSQL 15+; FFmpeg and FFprobe.
- FastAPI 0.110.1, Pydantic 2.12.5, pydantic-settings 2.14.2, SQLAlchemy 2.0.51,
  psycopg 3.2.9, Supabase Python 2.27.2, OpenAI Python 1.99.9, PyCryptodome 3.23.0,
  httpx 0.28.1, python-multipart 0.0.21, Uvicorn 0.25.0, pytest 8.4.2.

## 1. Exact public route inventory

Exactly these 13 operations are public. `GET /health` is anonymous. Every other operation requires
a verified Supabase access-token bearer before body parsing, database access, upload consumption,
or provider work.

|   # | Method | Path                               | Operation ID            |
| --: | ------ | ---------------------------------- | ----------------------- |
|   1 | GET    | `/health`                          | `getHealth`             |
|   2 | GET    | `/api/v1/profile`                  | `getProfile`            |
|   3 | PATCH  | `/api/v1/profile`                  | `updateProfile`         |
|   4 | DELETE | `/api/v1/account`                  | `deleteAccount`         |
|   5 | GET    | `/api/v1/entries`                  | `listEntries`           |
|   6 | GET    | `/api/v1/entry/draft`              | `getTextEntryDraft`     |
|   7 | PUT    | `/api/v1/entry/draft`              | `saveTextEntryDraft`    |
|   8 | DELETE | `/api/v1/entry/draft`              | `discardTextEntryDraft` |
|   9 | POST   | `/api/v1/entry`                    | `createTextEntry`       |
|  10 | POST   | `/api/v1/past-entries`             | `createPastEntry`       |
|  11 | POST   | `/api/v1/entries/voice`            | `createVoiceEntry`      |
|  12 | GET    | `/api/v1/entries/{entry_id}`       | `getEntry`              |
|  13 | POST   | `/api/v1/entries/{entry_id}/retry` | `retryEntry`            |

Do not register root, docs in production, legacy `/api`, auth wrappers, candidate-library, review,
theme, reclassification, Journey, chapter, insight, or analytics operations. Supabase Auth owns
login, signup, refresh, logout, password, and session lifecycle.

## 2. HTTP contract

### Shared wire rules

- JSON uses snake_case. Dates are `YYYY-MM-DD`; timestamps are RFC 3339.
- Strict DTOs use `ConfigDict(extra="forbid")`.
- Every response carries `X-Request-ID`. Every error has exactly `error_code`, `message`, `details`,
  and `request_id`; it never exposes SQL, stack traces, ownership data, plaintext, envelopes, keys,
  tokens, provider messages, or audio.
- Owner-safe missing and cross-user resource lookups both return `404 NOT_FOUND`.
- Application-owned `429` and retryable `503` responses carry integer `Retry-After` seconds.
- Non-voice `/api/v1` requests have a 1 MiB transport body limit. Voice owns its streaming limit.
- `GET /api/v1/entries` and `POST /api/v1/past-entries` return
  `Cache-Control: private, no-store`; the past-import response also returns `Location`.

### Request DTOs

| DTO                      | Exact fields and validation                                                                                                                                                                                           |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ProfileUpdate`          | At least one of `display_name?: string` (trimmed, max 100) or `timezone?: string` (1-100, exact supported IANA identifier). Explicit null and extra fields fail.                                                      |
| `AccountDeletionRequest` | Required `confirmation: "DELETE MY ACCOUNT"`; required nonempty `reauthentication_token`; extras fail.                                                                                                                |
| `EntryDraftUpdate`       | Required `content: string`, max 200,000 scalars. Blank/whitespace content clears the active draft.                                                                                                                    |
| `TextEntryCreate`        | Exactly required nonblank `content: string`, 1-200,000 scalars. No date, user, ID, draft ID, idempotency key, or processing token.                                                                                    |
| `PastEntryCreate`        | Exactly required `entry_date: date` and nonblank `content: string`, 1-200,000 scalars. Date is inclusive from user-local today minus ten calendar years through today; February 29 clamps to February 28 when needed. |
| Voice request            | Required `Idempotency-Key` header, 1-128 characters, no leading/trailing whitespace; optional non-null `entry_date` query; multipart body with exactly one file part named `audio` and no other parts.                |
| Detail/retry path        | Required UUID `entry_id`. Malformed UUID returns `422 VALIDATION_ERROR`.                                                                                                                                              |
| Entry list query         | `page` default 1, minimum 1; `page_size` default 20, range 1-100. Unknown query fields are ignored by the reference.                                                                                                  |

### Response DTOs

- `HealthResponse`: `{status: "ok"}`.
- `Profile`: `{display_name: string, timezone: string}`.
- `EntryDraftResponse`: `{content: string|null, updated_at: date-time|null}`. No draft identity or
  submitted replay metadata is public.
- `PastEntryAccepted`: `{entry_id: uuid, entry_date: date, processing_status: "pending",
status_url: "/api/v1/entries/{entry_id}"}`.
- `EntryPage`: `{items: EntrySummary[], total: integer>=0, page: integer>=1,
page_size: integer 1..100}`.
- `EntrySummary`: `{id, input_type: text|audio, entry_date, processing_status, created_at,
content_preview, themes}`. Preview is the exact unsuffixed `plaintext[:200]` Unicode-code-point
  prefix. Entries sort by `entry_date DESC, created_at DESC, id DESC`. Non-completed entries have
  `themes: []`; completed entries have zero to three distinct initial themes in contiguous
  primary/secondary/tertiary order, each `{key,name,color_hex,tier}`.
- `EntryDetail`: `{id, content, input_type, entry_date, original_theme_config_id,
processing_status, processing_error_code, created_at, classification, ideas,
extracted_memories, reflections}`. `classification` is null unless completed; completed entries
  always have a classification, including `{mode:null,themes:[]}` for zero themes.
- `Classification`: `{theme_config_id, source: initial|backfill, mode: dominant|balanced|null,
themes: ThemeScore[0..3]}`. Themes are ordered contiguous tiers. Score vectors are: one dominant
  `1.0`; two dominant `0.6265/0.3735`; two balanced `0.5333/0.4667`; three dominant
  `0.52/0.31/0.17`; three balanced `0.40/0.35/0.25`.
- Idea/memory candidate: `{id, content, status, entry_id, entry_date, created_at, decided_at}`.
  Reflection: `{id, reflection_type, activity, confidence_score, status, entry_id, entry_date,
created_at, decided_at}`. Internal `decision_source` is never returned.

### Route statuses, headers, and stable errors

This table gives the frozen contract first. Runtime-only differences are in section 13.

| Operation                  | Success                                      | Success headers                             | Contract errors                                                                            |
| -------------------------- | -------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `GET /health`              | 200 `HealthResponse`                         | `X-Request-ID`                              | 429 `RATE_LIMITED` + `Retry-After`                                                         |
| `GET /profile`             | 200 `Profile`                                | `X-Request-ID`                              | 401, 429, 500 `INTERNAL_ERROR`                                                             |
| `PATCH /profile`           | 200 `Profile`                                | `X-Request-ID`                              | 401, 422, 429, 500                                                                         |
| `DELETE /account`          | 204, empty body                              | `X-Request-ID`                              | 401, 409, 422, 429, 503 + `Retry-After`                                                    |
| `GET /entries`             | 200 `EntryPage`                              | `Cache-Control`, `X-Request-ID`             | 401, 422, 429, 500                                                                         |
| `GET /entry/draft`         | 200 `EntryDraftResponse`                     | `X-Request-ID`                              | 401, 429, 503                                                                              |
| `PUT /entry/draft`         | 200 `EntryDraftResponse`                     | `X-Request-ID`                              | 401, 422, 429, 503                                                                         |
| `DELETE /entry/draft`      | 200 empty-draft response                     | `X-Request-ID`                              | 401, 429, 503                                                                              |
| `POST /entry`              | 201 new or 200 replay/reclaimed failed entry | `X-Request-ID`                              | 401, 409 `INVALID_STATE`, 422, 429, 502 `PROVIDER_UNAVAILABLE`, 503 + `Retry-After`        |
| `POST /past-entries`       | 202 `PastEntryAccepted`                      | `Location`, `Cache-Control`, `X-Request-ID` | 401, 409 `PAST_ENTRY_DUPLICATE`, 422, 429 (`RATE_LIMITED` or `PAST_ENTRY_QUEUE_FULL`), 503 |
| `POST /entries/voice`      | 201 new or 200 replay                        | `X-Request-ID`                              | 401, 409, 413 `AUDIO_LIMIT_EXCEEDED`, 415 `UNSUPPORTED_AUDIO_FORMAT`, 422, 429, 502, 503   |
| `GET /entries/{id}`        | 200 `EntryDetail`                            | `X-Request-ID`                              | 401, 404, 429, 500 `ENTRY_CONTENT_UNAVAILABLE`                                             |
| `POST /entries/{id}/retry` | 200 `EntryDetail`                            | `X-Request-ID`                              | 401, 404, 409, 429, 502, 503                                                               |

Additional observed error codes are `REAUTHENTICATION_REQUIRED`, `ACCOUNT_DELETION_UNAVAILABLE`,
`ENTRY_DRAFT_UNAVAILABLE`, `REQUEST_TIMEOUT`, `SERVICE_UNAVAILABLE`, and generic
`PAYLOAD_TOO_LARGE`. Exact safe messages and `details` shapes must be regression-tested.

## 3. Authentication and authorization

1. Only `/health` is anonymous. Parse the `Authorization` header as the HTTP Bearer scheme.
2. Verify the token with Supabase Auth `get_user`; never decode an unverified JWT for ownership.
3. Build a typed auth context containing the verified UUID, an owner-context database handle, and
   the access token. Never log or return the token.
4. Authenticate matched product routes before FastAPI parses JSON, query/path DTOs, or multipart
   bodies. Missing, malformed, invalid, expired, or non-UUID identities return the same canonical
   401 response.
5. Derive ownership only from the verified UUID. Ignore or reject client ownership fields; do not
   accept `user_id` in any DTO.
6. Every application transaction sets `SET LOCAL ROLE authenticated` and transaction-local
   `request.jwt.claims={sub,role}`. Internal owner RPCs run through the least-privilege `orion_app`
   capability role. Worker RPCs run through `orion_worker`; neither role has `BYPASSRLS`.
7. SQL always includes owner predicates even with RLS. Missing and foreign IDs are
   indistinguishable.
8. Account deletion requires both the normal bearer and a fresh Supabase proof resolving to the
   same UUID. Deletion uses the server-only Supabase admin client. `auth.users` is the cascade root.

## 4. Database blueprint

Use one fresh ordered migration set, not legacy upgrade files. Repositories receive a transaction
session from a Unit of Work and never commit. Do not implement PostgREST fallbacks.

### Required tables and invariants

| Table                          | Required purpose and invariants                                                                                                                                                                                                                                                   |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth.users`                   | Supabase-owned identity and account-deletion cascade root.                                                                                                                                                                                                                        |
| `user_profiles`                | PK/FK `user_id ON DELETE CASCADE`; trimmed display name <=100; valid IANA timezone; bounded voice-rate timestamps; created/updated timestamps.                                                                                                                                    |
| `theme_configs` / `themes`     | Internal immutable dimension. Seed only fixed Default 8 config ID `00000000-0000-0000-0000-000000000801` and its exact eight ordered key/name/color rows. No public mutation. Preserve FK integrity for `EntryDetail`.                                                            |
| `entry_drafts`                 | Backend UUID; owner FK cascade; encrypted envelope or null; 64-hex keyed fingerprint; status active/submitted; lifecycle check; at most one active per owner; submitted ciphertext cleared.                                                                                       |
| `entries`                      | Owner FK cascade; valid v2 encrypted envelope; text/audio; source date; fixed original config FK; pending/processing/completed/failed lifecycle check; token only while processing; error only while failed; optional voice idempotency key; optional owner-safe source draft FK. |
| `entry_classifications`        | Same-owner entry FK; config FK; one per `(entry_id, theme_config_id)`; nullable mode only for zero themes; source initial/backfill (backfill retained only as readable historical value).                                                                                         |
| `entry_themes`                 | Same-owner classification FK and same-config theme FK; unique tier and theme per classification; 0-3 contiguous tiers; exact score vector.                                                                                                                                        |
| `ideas` / `extracted_memories` | Same-owner entry FK cascade; exact source content 1-4000; pending/approved/rejected lifecycle; `decision_source` null/user/past_import_auto constraint. No public library operations.                                                                                             |
| `reflections`                  | Same-owner entry FK cascade; one row per `(entry_id, reflection_type)`; activity 1-1000; confidence 0..1; same lifecycle/provenance rules.                                                                                                                                        |
| `past_entry_imports`           | Owner and same-owner entry FKs cascade; unique entry and unique `(user_id,fingerprint_key_id,request_fingerprint)`; pending/running/completed/failed lifecycle; attempts 0..3; claim/worker/heartbeat invariants.                                                                 |

### Required indexes

- `entries`: unique `(user_id,idempotency_key)` where non-null; unique `source_draft_id` where
  non-null; history `(user_id,entry_date DESC,created_at DESC,id DESC)`; owner/processing; stale
  unfinished; original config; envelope key.
- `entry_drafts`: unique active owner; owner/submitted replay order; envelope key.
- Classification/evidence: owner/config/entry lookup; unique classification/config, tier, theme,
  reflection type; child `(entry_id,user_id,created_at,id)`; review-oriented owner/status indexes.
- Past imports: claimable pending `(created_at,id)`; stale running `(heartbeat_at,id)`; owner/status;
  unique owner fingerprint.
- Theme catalog: unique config key/name/sort order and lookup by config/order.

### RLS, grants, and triggers

- Enable RLS on every user-owned table. User-facing policies are capability-specific: profile
  select/update own; entry select/insert own; active draft select/insert/update/delete own; derived
  rows select own; fixed global theme catalog select. `past_entry_imports` has no browser policy.
- Revoke table access from PUBLIC and anon. Authenticated gets only the minimum operations above.
  Derived writes and all queue writes are execute-only RPC capabilities.
- `orion_app` and `orion_worker` are NOLOGIN, NOINHERIT, NOSUPERUSER, NOBYPASSRLS roles. Deployment
  login roles are members; migration SQL stores no passwords.
- Triggers: profile timezone validation; updated-at for profile, entry, draft, and import; profile
  bootstrap after `auth.users` insert; deferred config ownership; deferred classification
  completeness; past-import candidate auto-approval; import status synchronization after terminal
  entry status.

### Required transactional functions/RPCs

- Owner: `save_entry_draft_for_owner`, `discard_entry_draft_for_owner`,
  `submit_text_entry_from_draft_for_owner`, `claim_failed_entry_for_owner`,
  `mark_entry_processing_failed_for_owner`, `apply_entry_extraction_for_owner`, and
  `queue_past_entry_for_owner`.
- Worker: `claim_past_entry_import`, `renew_past_entry_import`, and
  `recover_stale_past_entry_imports`.
- Shared internal functions: strict v2 envelope validator, classification mode/score validation,
  updated-at trigger, profile-timezone validation, past-import provenance triggers.
- All SECURITY DEFINER functions set an empty `search_path`, schema-qualify objects, verify role and
  parent ownership, and have explicit REVOKE/GRANT statements.

## 5. Encryption and canonicalization

1. Canonicalize source text before fingerprints or encryption: require Python Unicode database
   14.0.0, convert CRLF and CR to LF, NFC-normalize, then trim only `TAB`, `LF`, `VT`, `FF`, `CR`,
   and ASCII space from both edges. Encode strict UTF-8. Reject empty or more than 200,000 Unicode
   scalars.
2. Persist only envelope v2 with exactly eight keys: `version=2`, `algorithm=AES-256-GCM`,
   `key_id`, `kdf=HKDF-SHA256`, and canonical-base64 `salt`, `nonce`, `ciphertext`, `tag`.
   Salt is 32 bytes, nonce 12, tag 16, ciphertext nonempty.
3. Derive a per-envelope 32-byte key with HKDF-SHA256 info `orion/entry-content/v2` from the
   server-held 32-byte master key and random salt.
4. Bind GCM AAD to version, algorithm, KDF, key ID, canonical owner UUID, canonical entry/draft UUID,
   and `field=content`. Any shape/key/AAD/tag/UTF-8 failure maps to a fixed safe content error.
5. Draft replay fingerprint: HMAC-SHA256 over version label, canonical owner UUID, and canonical
   plaintext. Past-import fingerprint additionally includes ISO entry date and returns the active
   key ID. Fingerprints are equality tokens, never public identifiers.
6. Store full canonical plaintext encrypted. Send at most 50,000 Unicode scalars and 200,000 UTF-8
   bytes to the extraction provider. Never store or log provider input.

## 6. Text-draft replay state machine

```text
ABSENT
  GET -> {content:null,updated_at:null}
  PUT blank -> ABSENT
  PUT nonblank -> ACTIVE(new backend UUID, encrypted content, keyed fingerprint)

ACTIVE
  GET -> decrypted content + updated_at
  PUT nonblank -> ACTIVE(same UUID, replaced envelope/fingerprint)
  PUT blank or DELETE -> ABSENT
  POST matching canonical content, under per-owner transaction lock
    -> create one linked PROCESSING entry
    -> SUBMITTED(clear draft ciphertext, retain fingerprint and submitted_at)
  POST missing/mismatch -> 409, no mutation

SUBMITTED
  GET/PUT/DELETE ignore submitted metadata
  POST matching latest submitted fingerprint
    -> linked entry completed/processing: 200 replay, no model call
    -> linked entry failed: atomic failed->processing claim, process, 200
  POST mismatch or missing link -> 409, no mutation

NEW ACTIVE AFTER SUBMISSION
  Same text is a new user intent and may create a distinct entry.
```

Draft save/discard/submit share a per-owner advisory transaction lock. The unique source-draft
index is the database replay guard. `source_draft_id` never identifies a processing attempt.

## 7. Entry-processing state machine

```text
pending (past import only) -> processing(token)
new text/voice -----------> processing(token)
processing(token) --atomic extraction commit--> completed(token null, error null)
processing(token) --safe finalization---------> failed(token null, safe code)
failed --atomic owner claim with new token----> processing
completed/processing replay ------------------> return current entry; no provider call
```

- Each attempt loads the entry's preserved config, deterministically segments canonical provider
  input, filters trivial evidence, and performs no model call if no segment is selectable.
- Otherwise make one `gpt-4o` structured extraction request with SDK retries disabled. Only a
  retryable primary provider failure may cause one `gpt-4o-mini` fallback. Invalid structured output
  fails; it is not silently accepted.
- The model returns source-segment references, never candidate/evidence prose. Validate allowed
  keys, unique references, 0-3 contiguous tiers, mode, confidence, and bounds. Materialize exact
  idea/memory/evidence text from backend offsets.
- One atomic transaction, guarded by current processing token, inserts classification, themes,
  ideas, memories, threshold-qualified reflections, and marks the entry completed. No partial
  derived rows survive failure.
- Normal text/voice/retry candidates start `pending_approval`; past-import provenance changes that
  inside the database transaction only.
- Retry is owner-scoped and allowed only from failed. Audio retry decrypts the stored transcript and
  never retranscribes.

## 8. Voice idempotency and cleanup lifecycle

1. Resolve effective date from the optional query or user-profile timezone. Reject future dates.
2. Look up `(verified user, Idempotency-Key)` before reading the body. Same effective date and audio
   type returns 200 existing detail; different date/type returns 409. Audio bytes are not compared.
3. Stream exactly one multipart file to a route-owned temporary file. Bound audio to 25 MiB and
   multipart overhead to 64 KiB; abort while streaming when exceeded.
4. Match declared MIME, magic signature, FFprobe container/audio packets, and FFmpeg decoded
   duration. Allowed: WAV, MP3/MPEG/MPGA, MP4/M4A, WEBM, OGG. Limit duration to 1,200 seconds.
5. Call `whisper-1` once, timeout 120 seconds, SDK retries disabled. Reject empty transcript.
6. Canonicalize/encrypt only the transcript, insert one audio entry with unique owner/key, then run
   normal processing. Total route lifecycle deadline is 300 seconds.
7. Always close/unlink the temporary file on success, validation rejection, provider failure,
   persistence failure, timeout, disconnect, and cancellation. On post-insert cancellation/timeout,
   revoke/finalize the active processing token safely. Never persist or log raw audio.
8. A unique-insert race re-reads the owner/key row and returns it only if type/date match. Each new
   recording needs a new key.

## 9. Past-import durable queue lifecycle

```text
POST -> atomic entry(pending) + import(pending, attempts=0) -> 202
worker claim, SKIP LOCKED -> import(running, attempts+1, claim token, heartbeat)
                           + entry(processing, processing token)
running --heartbeat every 30s--> running
running --token-guarded extraction commit--> entry completed + import completed
running --safe failure---------------------> entry failed + import failed
stale <3 attempts--------------------------> entry/import pending for reclaim
stale completed entry----------------------> import completed, no model replay
stale failed or attempts>=3----------------> terminal failed
```

- Request path makes zero AI calls. Queue depth is capped at 200 pending/running rows per owner.
- Duplicate identity is HMAC over owner/date/canonical content and active fingerprint key ID.
  Duplicate returns 409 with owner-safe existing entry ID/date/status and creates no work.
- Worker claims oldest pending work with `FOR UPDATE SKIP LOCKED`, has 120-second stale threshold,
  30-second heartbeat/recovery interval, maximum three attempts, and token-guarded persistence.
- Database-proven same-owner import provenance auto-approves exact Ideas and Memories and only
  threshold-qualified reflections, sets `decided_at` and `decision_source=past_import_auto`, and
  never accepts an API/worker approval flag.

## 10. Internal dependencies needed by EntryDetail

Although their public endpoints are excluded, EntryDetail requires internal persistence and view
models for:

- fixed/historical `theme_configs` and `themes` so classification keys and names can be joined;
- `entry_classifications` and `entry_themes` for the preserved initial classification and scores;
- `ideas`, `extracted_memories`, and `reflections` for owner-matched lifecycle children;
- deterministic source segmentation, strict model DTOs, prompt construction, OpenAI extraction,
  reflection thresholding, and atomic derived persistence;
- encryption/decryption and safe content-unavailable mapping;
- profile timezone for entry-date resolution;
- past-import provenance, because it changes child lifecycle values visible in EntryDetail.

These are internal modules only. Do not register candidate-library, review, theme, reclassification,
Journey, chapter, insight, or analytics routes.

## 11. Route-to-layer-to-storage map

| Route                      | Controller responsibility                   | Service workflow                                      | Repository / transaction                         | Tables or RPCs                                           |
| -------------------------- | ------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------- |
| `GET /health`              | Return fixed DTO                            | None                                                  | None                                             | None                                                     |
| `GET /profile`             | Auth dependency, 200                        | Read profile                                          | Owner UoW query                                  | `user_profiles`                                          |
| `PATCH /profile`           | Parse strict DTO, 200                       | Normalize/update supplied fields                      | Owner UoW locked update                          | `user_profiles`                                          |
| `DELETE /account`          | Parse body, 204                             | Verify fresh same-user proof; admin delete            | Supabase Auth admin                              | `auth.users` cascade                                     |
| `GET /entries`             | Parse page, set no-store                    | Page, decrypt selected owner rows, map summaries      | Owner UoW stable page + batched initial themes   | `entries`, classifications, entry themes, themes         |
| `GET /entry/draft`         | 200 even absent                             | Restore/decrypt active only                           | Owner UoW query                                  | `entry_drafts`                                           |
| `PUT /entry/draft`         | Parse strict content                        | Clear or canonicalize/encrypt/fingerprint/save        | Owner UoW RPC                                    | `save_entry_draft_for_owner`                             |
| `DELETE /entry/draft`      | 200 empty DTO                               | Clear active only                                     | Owner UoW RPC                                    | `discard_entry_draft_for_owner`                          |
| `POST /entry`              | Parse content; choose 201/200               | Draft transition, process/replay/reclaim              | Owner UoW RPC, then token-guarded processing UoW | `submit_text_entry_from_draft_for_owner`, extraction RPC |
| `POST /past-entries`       | Parse DTO; set 202/Location/no-store        | Validate date, canonicalize/encrypt/fingerprint/queue | Owner UoW RPC                                    | `queue_past_entry_for_owner`, entries/imports            |
| `POST /entries/voice`      | Header/query/body parsing, 201/200, cleanup | Replay, validate, transcribe, encrypt, process        | Owner UoWs; unique owner/key                     | entries and extraction RPCs                              |
| `GET /entries/{id}`        | UUID/auth, 200/404                          | Authorize, decrypt, assemble evidence                 | Owner UoW batched detail                         | entries, classifications, themes, three child tables     |
| `POST /entries/{id}/retry` | UUID/auth, 200                              | Failed-only claim and common processing               | Owner UoW RPCs                                   | claim/apply/fail RPCs and detail tables                  |

`routes.py` contains only registrations. Controllers own FastAPI dependencies, parsing, status, and
headers. Services receive typed values, never Request/Response. Repositories own SQL/RPC calls but
receive an active Unit of Work. Views are the sole public DTO mapping boundary.

## 12. Test matrix

| Area              | Required proof                                                                                                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Route inventory   | Exactly 13 operations; one anonymous operation; excluded route families 404; production docs/schema absent.                                                                                 |
| Auth boundary     | Missing/malformed/invalid/expired bearer before JSON, UUID, DB, upload, or provider work; valid UUID ownership; no client user ID.                                                          |
| Strict schemas    | Required/extra/null/length/timezone/date/header/multipart cases; canonical error envelope and field list.                                                                                   |
| Profile/account   | Owner read/update; timezone trigger; fresh same-user reauth; admin failure safe/retryable; missing Auth user retry idempotence; cascade deletion.                                           |
| Encryption        | Canonicalization, Unicode/version pin, random envelopes, exact shape/base64 sizes, owner/row AAD, tamper/wrong-key failure, HMAC scope, plaintext/log scans.                                |
| Draft replay      | Empty GET, encrypted PUT, blank clear, active ID reuse, mismatch 409 no mutation, lost-response replay, concurrent submit, failed reclaim, new identical intent.                            |
| Text processing   | Full ciphertext vs provider cap, no-selectable zero-call completion, 0/1/2/3 theme vectors, exact source spans, threshold, one fallback ceiling, atomic rollback, token guard.              |
| Entry list/detail | Stable pagination, exact 200-code-point preview, all statuses/input types, initial theme integrity, empty page no decrypt, owner-before-decrypt, no writes/AI, no-store.                    |
| Voice             | Every container/MIME/signature combination; FFprobe/FFmpeg bounds; exact limits; replay before body; key/date conflict; one transcription; timeout/cancel/disconnect cleanup; no raw bytes. |
| Retry             | Foreign/missing 404; nonfailed 409; one concurrent claim; new token; stored transcript only; provider/service failure finalization.                                                         |
| Past import       | Ten-year/leap boundaries; 202 headers; zero-call request; HMAC duplicate; queue cap; SKIP LOCKED; heartbeat/stale/attempt recovery; provenance-only auto-approval.                          |
| RLS/grants        | Direct cross-user SELECT/INSERT/UPDATE/DELETE; forged parent/child owner; execute permissions; empty search paths; browser cannot mutate derived/queue state.                               |
| Account deletion  | Two-user live proof that Auth identity and every required application row cascade; no prior-account data after account switch.                                                              |
| Architecture      | Import/layer rules; no FastAPI in services; no SQL/OpenAI in controllers; repositories do not commit; model files contain mappings only; every DTO forbids extras.                          |
| Contract          | Parse OpenAPI; exactly 13 operations; every `$ref` resolves; required path params declared; no excluded paths/schemas; runtime schema/route parity.                                         |

Before implementation handoff, run type/static checks, the complete non-live pytest suite, migration
install tests on disposable PostgreSQL 15+, live two-user Supabase RLS/account-deletion tests, and
FFmpeg/FFprobe voice integration tests. Live tests must be explicitly reported blocked if disposable
credentials are unavailable.

## 12.1 Environment-variable matrix

| Variable                                      | Production | Secret      | Purpose and validation                                                         |
| --------------------------------------------- | ---------- | ----------- | ------------------------------------------------------------------------------ |
| `ENVIRONMENT`                                 | Required   | No          | `development`, `test`, or `production`; production enables fail-closed checks. |
| `ENABLE_API_DOCS`                             | Required   | No          | Boolean; must be false in production.                                          |
| `SUPABASE_URL`                                | Required   | No          | HTTPS Supabase URL used only at Auth boundaries.                               |
| `SUPABASE_PUBLISHABLE_KEY`                    | Required   | No          | Public key for server Auth verification; never an ownership source by itself.  |
| `SUPABASE_SECRET_KEY`                         | Required   | Yes         | Server-only Auth admin key used for account deletion.                          |
| `APP_DATABASE_URL`                            | Required   | Yes         | PostgreSQL URL for the least-privilege application login/UoW.                  |
| `WORKER_DATABASE_URL`                         | Required   | Yes         | PostgreSQL URL for the distinct worker login/UoW.                              |
| `OPENAI_API_KEY`                              | Required   | Yes         | Structured extraction and transcription credential.                            |
| `ENTRY_ENCRYPTION_ACTIVE_KEY_ID`              | Required   | No          | Identifier of the active version-2 encryption key.                             |
| `ENTRY_ENCRYPTION_KEYS`                       | Required   | Yes         | JSON map of key IDs to padded-base64 32-byte master keys.                      |
| `ENTRY_FINGERPRINT_ACTIVE_KEY_ID`             | Required   | No          | Identifier of the active keyed-fingerprint key.                                |
| `ENTRY_FINGERPRINT_KEYS`                      | Required   | Yes         | JSON map of key IDs to padded-base64 32-byte HMAC keys.                        |
| `REFLECTION_REVIEW_THRESHOLD`                 | Required   | No          | Finite `[0,1]` decimal; frozen production value `0.80`.                        |
| `CORS_ALLOW_ORIGINS`                          | Required   | No          | Explicit comma-separated HTTPS origins in production; no wildcard.             |
| `REQUEST_TIMEOUT_SECONDS`                     | Required   | No          | Positive bounded non-voice deadline; default 30.                               |
| `MAX_REQUEST_BODY_BYTES`                      | Required   | No          | Positive non-voice transport limit; default 1 MiB.                             |
| `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW` | Required   | No          | Non-negative bounded pool sizing.                                              |
| `DATABASE_POOL_RECYCLE_SECONDS`               | Required   | No          | Positive connection recycle interval.                                          |
| `LOG_FORMAT`                                  | Required   | No          | `json` in production; metadata only.                                           |
| `OTEL_ENABLED`, `OTEL_SERVICE_NAME`           | Optional   | No          | Private telemetry configuration; no public metrics route.                      |
| `OTEL_EXPORTER_OTLP_ENDPOINT`                 | Optional   | Potentially | Optional HTTPS collector endpoint; attributes remain privacy-safe.             |
| `SUPABASE_TEST_*`                             | Test only  | Yes         | Optional two-user proof credentials; never required by runtime.                |

## 13. Contradictions and known verification gaps

1. The reference changed commits during the earlier documentation audit. Stage 0 freezes commit
   `1a993c34...` and the checksums in `reference-manifest.md`; its worktree was clean at the Stage 0
   observation.
2. Frozen OpenAPI omits the required `entry_id` parameter on both templated paths. Runtime parses a
   UUID. The trimmed document adds the existing `EntryId` component reference as a non-behavioral
   structural correction.
3. OpenAPI `EntryDetail.required` omits `processing_error_code`, while the runtime Pydantic DTO
   requires it and every example returns it. The trimmed contract marks it required.
4. Frozen profile operations advertise 500 while legacy runtime paths could emit 404/503. The fresh
   contract follows the higher-authority frozen response map: missing-profile and database failures
   are sanitized as `500 INTERNAL_ERROR`; profile bootstrap normally prevents the former.
5. Account deletion freezes invalid, expired, or different-user reauthentication as `401
REAUTHENTICATION_REQUIRED`, semantic confirmation/state conflict as `409`, and an unconfirmed
   provider outcome as `503 ACCOUNT_DELETION_UNAVAILABLE` with `Retry-After: 30`.
6. Draft dependency failures use the documented retryable `503`. Any authenticated-content envelope,
   key, AAD, tag, or decode failure uses the fixed non-retryable `500 ENTRY_CONTENT_UNAVAILABLE`.
7. Malformed transport framing may return canonical `400`, a non-voice request exceeding 1 MiB may
   return canonical `413`, and a timed-out request returns `503 REQUEST_TIMEOUT` with
   `Retry-After: 1`. These are global HTTP-boundary outcomes rather than route-domain responses.
8. `POST /past-entries` freezes both `Location` and `Cache-Control: private, no-store` on success.
   Queue saturation uses `429 PAST_ENTRY_QUEUE_FULL` with an integer `Retry-After`.
9. `Idempotency-Key` is 1-128 characters and must equal its own trimmed value; leading/trailing
   whitespace is invalid. This runtime validation deliberately narrows the opaque OpenAPI scalar.
10. Reference SQL history includes legacy broad policies, PostgREST paths, reclassification tables,
    and later retirement deltas. The fresh build must express only the final required schema and
    cannot copy those historical layers.
11. Current synchronous text/voice processing spans multiple short transactions around provider
    calls. Atomicity applies to each source transition and derived commit, not to the network call.
12. Stage 0 performs document and contract checks only. Disposable PostgreSQL/Supabase RLS,
    cross-user access, account cascade, concurrency, and queue recovery remain mandatory later-stage
    gates and may not be represented by mocks.

No application code is authorized in Stage 0. These resolutions are frozen by the execution handoff
and must be reflected consistently in code, tests, and the final packaged contract.
