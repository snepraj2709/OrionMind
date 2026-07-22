# Orion Mind

Orion Mind is a private journaling application that turns text or voice entries into structured, reviewable material and—when the gated reflection system is enabled—longitudinal patterns across multiple entries.

The repository contains a Next.js frontend, a FastAPI backend, PostgreSQL migrations, a durable processing worker, and a reflection engine. Some screens are connected to the backend today; the review workflow is not. This README describes the code as it exists and calls out those gaps explicitly.

## 1. Project overview

Orion is intended for people who want to journal and gradually identify recurring patterns without treating every model-generated observation as fact.

The product uses several related terms:

| Term           | Meaning in this repository                                                                                                                                                                                                                          |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entry          | One encrypted journal record created from text, a voice transcript, or a dated historical import.                                                                                                                                                   |
| Source segment | A temporary sentence-sized span built during processing. It has an ID and exact character offsets, but it is not stored in a generic `segments` table.                                                                                              |
| Review item    | A candidate idea, extracted memory, or per-entry reflection with `pending_approval`, `approved`, or `rejected` status. The database models exist, but the current review screen uses mock data rather than backend endpoints.                       |
| Reflection     | The name is used twice: `public.reflections` stores per-entry review candidates such as `filled_energy`; the longitudinal reflection engine stores cross-entry hidden drivers, recurring loops, and inner tensions in snapshots and insight tables. |

The implemented production reflection path is:

```text
Entry added
→ encrypted entry and processing job stored
→ worker decrypts locally, redacts PII, and creates temporary source segments
→ entry is classified and accepted entries produce atomic signals
→ deterministic cross-entry candidates are scored
→ eligible candidates are synthesized and validated
→ a reflection snapshot is exposed as Hidden drivers, Recurring loops, and Inner tensions
```

The requested review-gated path is not fully wired. Approving a review item in `/approvals` currently changes only an in-memory mock store. The production reflection engine reads accepted `entry_analyses` and `entry_signals`; it does not wait for, or consume, user-approved rows from `ideas`, `extracted_memories`, or the entry-level `reflections` table.

## 2. Tech stack

### Frontend

| Technology                 | What it does here                                                                          |
| -------------------------- | ------------------------------------------------------------------------------------------ |
| Next.js 16                 | App Router pages, layouts, route handlers, production build, and server/client boundaries. |
| React 19                   | UI composition and interactive screens.                                                    |
| TypeScript                 | Frontend types and compile-time checks.                                                    |
| Tailwind CSS 4             | Token-driven styling through the shared design system.                                     |
| Radix UI                   | Accessible primitive behavior used by shared UI components.                                |
| TanStack Query             | Entry, reflection, and review query/mutation state, caching, retries, and invalidation.    |
| TanStack Table             | Data-table behavior.                                                                       |
| Zod                        | Strict validation of frontend API responses and form inputs.                               |
| React Hook Form            | Form state and validation integration.                                                     |
| Supabase JavaScript client | Browser authentication, session persistence in `sessionStorage`, and access-token refresh. |
| Vitest and Testing Library | Frontend unit and component tests.                                                         |
| Playwright                 | Browser and screenshot tests.                                                              |

### Backend

| Technology                                | What it does here                                                                                                    |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Python 3.11                               | Backend runtime.                                                                                                     |
| FastAPI and Uvicorn                       | Authenticated HTTP API, middleware, OpenAPI, and ASGI serving.                                                       |
| Pydantic and pydantic-settings            | Strict request/response, model-output, job, and environment validation.                                              |
| SQLAlchemy 2 and psycopg 3                | PostgreSQL sessions, transactions, and RPC calls.                                                                    |
| PostgreSQL / Supabase                     | Durable storage, database functions, constraints, authentication ownership, and row-level security.                  |
| OpenAI Python SDK                         | Whisper-1 transcription and structured Responses API calls.                                                          |
| GPT-5.6 Luna                              | Configured default for combined entry quality analysis, theme classification, legacy extraction, and atomic signals. |
| GPT-5.6 Terra                             | Configured default for wording eligible cross-entry reflection candidates.                                           |
| GPT-5.6 Sol                               | Configured default critic for higher-risk reflection candidates.                                                     |
| Microsoft Presidio, spaCy, and tldextract | Offline PII detection and local redaction before entry-analysis requests.                                            |
| PyCryptodome                              | AES-GCM envelopes, fingerprints, and encrypted application payloads.                                                 |
| FFmpeg / ffprobe                          | Local validation and decoding checks for uploaded audio.                                                             |
| OpenTelemetry                             | Optional OTLP traces and reflection/queue metrics. No public metrics endpoint is implemented.                        |
| pytest                                    | Backend unit, contract, database, privacy, worker, and reflection tests.                                             |

## 3. Repository structure

```text
.
├── src/
│   ├── app/                         # Next.js pages, layouts, and route handlers
│   │   ├── (protected)/entries/     # Entry list, detail, and new-entry pages
│   │   ├── (protected)/approvals/   # Mock-backed review page
│   │   ├── (protected)/reflections/ # Production reflection screen
│   │   └── api/                     # Frontend health and fixture route handlers
│   ├── features/
│   │   ├── entries/                 # Entry schemas, HTTP repository, queries, and screens
│   │   ├── approvals/               # Review UI and mock repository
│   │   └── reflections/             # Reflection API schemas, repository, queries, and UI
│   ├── services/                    # Authorized API client, Supabase, and mock store
│   ├── components/                  # Shared UI, layout, feedback, and design-system components
│   ├── config/                      # API, routes, status, theme, and typography registries
│   └── test/                        # Frontend test setup
├── e2e/                             # Playwright browser and screenshot tests
├── backend/
│   ├── app/modules/
│   │   ├── entries/                 # Entry API, service, storage, voice upload, and views
│   │   ├── processing/              # Segmentation, redaction, prompts, quality, and entry AI
│   │   ├── jobs/                    # Durable queue repository, service, and worker loop
│   │   ├── reflection_engine/       # Candidate scoring, evidence checks, synthesis, and snapshots
│   │   ├── reflections/             # Aggregate reflection read and feedback API
│   │   ├── past_imports/            # Historical-entry queueing
│   │   ├── profile/                 # Profile and account operations
│   │   └── health/                  # Liveness endpoint
│   ├── app/shared/                  # Auth, config, database, security, HTTP, and observability
│   ├── migrations/                  # Ordered PostgreSQL schema and RPC migrations
│   ├── scripts/                     # Migration, worker, preflight, and evaluation entry points
│   ├── tests/                       # Backend test suite
│   ├── docs/contracts/              # Frozen OpenAPI contract
│   └── Dockerfile                   # One-worker backend image
├── scripts/run-backend.sh           # Root backend development launcher
├── docs/                             # Design system and reflection documentation
├── package.json                     # Frontend scripts and dependencies
└── .env.example / backend/.env.example
```

## 4. Local setup

### Prerequisites

- Node.js 22 or newer (`package.json` declares `>=22.0.0`)
- npm and the committed `package-lock.json`
- Python 3.11
- PostgreSQL/Supabase roles and URLs if running database-backed operations
- FFmpeg and ffprobe if submitting voice entries locally

### Install dependencies

From the repository root:

```bash
npm ci
```

Create the backend environment and install both runtime and development requirements:

```bash
cd backend
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cd ..
```

### Configure environment variables

```bash
cp .env.example .env
cp backend/.env.example backend/.env
```

Fill in only the values required for the services you intend to run. Do not put a Supabase secret key in the root frontend `.env`.

For production email confirmation and password recovery, set
`NEXT_PUBLIC_SITE_URL=https://www.orionmind.in` in Vercel. In Supabase,
open **Authentication → URL Configuration**, set **Site URL** to
`https://www.orionmind.in`, and add these exact redirect URLs:

```text
https://www.orionmind.in/signup
https://www.orionmind.in/login
```

Keep `http://localhost:3000/signup` and `http://localhost:3000/login` as
additional redirect URLs only when local email-flow testing is required.

The apex production URL redirects to the canonical `https://www.orionmind.in`
origin. Configure the Railway API with all exact production browser origins
(without wrapping quotes):

```text
CORS_ALLOW_ORIGINS=https://orion-mind.vercel.app,https://orionmind.in,https://www.orionmind.in
```

Allowing the apex domain does not allow the distinct `www` origin. See
[`backend/docs/DEPLOYMENT.md`](backend/docs/DEPLOYMENT.md) for the production
preflight verification command.

Configure the Confirm signup and Reset password templates to route Supabase
`token_hash` values through Orion. This removes browser-local PKCE coupling and
lets Orion validate and scrub each one-time callback before showing the login or
password-update screen. Use the versioned templates and Management API command
in [`docs/supabase-auth-email-templates.md`](docs/supabase-auth-email-templates.md).

### Run migrations

Migrations are explicit and never run during API or worker startup. Use an authorized migration-owner connection only:

```bash
cd backend
ORION_MIGRATION_DATABASE_URL='postgresql://migration-role:password@localhost:5432/orion' \
  .venv/bin/python scripts/migrate.py
cd ..
```

### Start the application

Start the frontend:

```bash
npm run dev
```

Start the backend in another terminal. This wrapper creates `backend/.venv` and installs dependencies if needed:

```bash
npm run backend
```

Start the durable processing/reflection worker in another terminal:

```bash
cd backend
.venv/bin/python scripts/run_processing_worker.py
```

The backend serves `/health`. Local Swagger at `/docs` and `/openapi.json` is available only when `ENABLE_API_DOCS=true` outside production.

### Run tests and checks

Frontend checks required by this repository:

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

Browser tests build and start the frontend automatically unless `PLAYWRIGHT_BASE_URL` is supplied:

```bash
npm run test:e2e
```

Backend tests that do not contact a live Supabase project:

```bash
cd backend
.venv/bin/python -m pytest -m "not live_supabase"
```

### Production builds

Build the frontend:

```bash
npm run build
```

Build the backend container from the repository root:

```bash
docker build -t orion-backend backend
```

The image runs one Uvicorn worker. The processing worker is a separate process using the same image and `python scripts/run_processing_worker.py`, as configured in `backend/railway.worker.toml`.

## 5. Environment variables

Examples below are formats, not usable credentials.

### Frontend

| Variable                               | Required or optional                             | Purpose                                                                                   | Safe example format               |
| -------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------- | --------------------------------- |
| `NEXT_PUBLIC_SUPABASE_URL`             | Required for browser auth                        | Supabase project URL used by the browser client.                                          | `https://project-ref.supabase.co` |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Required for browser auth                        | Public/publishable Supabase key. Never use a secret/service-role key here.                | `sb_publishable_...`              |
| `NEXT_PUBLIC_API_BASE_URL`             | Required for the real backend                    | Backend origin; trailing slashes are removed.                                             | `http://127.0.0.1:8000`           |
| `SUPABASE_TEST_EMAIL`                  | Optional, test-only                              | Playwright account email.                                                                 | `orion-e2e@example.test`          |
| `SUPABASE_TEST_PASSWORD`               | Optional, test-only                              | Playwright account password.                                                              | `replace-with-test-password`      |
| `ORION_MOCK_AUTH_SECRET`               | Required only if mock auth is used in production | HMAC key for the server-only mock session helper; development has a fixed local fallback. | `long-random-test-only-value`     |
| `PLAYWRIGHT_BASE_URL`                  | Optional                                         | Runs Playwright against an already-running frontend instead of starting one.              | `http://127.0.0.1:3100`           |

### Backend

| Variable                                         | Required or optional                            | Purpose                                                                    | Safe example format                                                     |
| ------------------------------------------------ | ----------------------------------------------- | -------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `ENVIRONMENT`                                    | Optional, default `development`                 | Selects development, test, or production validation.                       | `development`                                                           |
| `ENABLE_API_DOCS`                                | Optional, default `false`                       | Enables local Swagger/OpenAPI outside production.                          | `true`                                                                  |
| `SUPABASE_URL`                                   | Required for authenticated API use              | Supabase project used for access-token verification.                       | `https://project-ref.supabase.co`                                       |
| `SUPABASE_PUBLISHABLE_KEY`                       | Required for authenticated API use              | Public key used by the verification client.                                | `sb_publishable_...`                                                    |
| `SUPABASE_SECRET_KEY`                            | Required in production                          | Server-only Supabase administration credential used by account operations. | `secret-from-a-secret-manager`                                          |
| `APP_DATABASE_URL`                               | Required for API data operations                | PostgreSQL SQLAlchemy URL for the restricted application login.            | `postgresql+psycopg://orion_app:password@localhost:5432/orion`          |
| `WORKER_DATABASE_URL`                            | Required for the worker                         | PostgreSQL SQLAlchemy URL for a distinct worker login.                     | `postgresql+psycopg://orion_worker_login:password@localhost:5432/orion` |
| `ADMIN_APP_DATABASE_URL`                         | Required only for the live Reflection E2E test  | Privileged observer URL; the runner forces read-only transactions.         | `postgresql://observer:password@localhost:5432/orion`                   |
| `ORION_MIGRATION_DATABASE_URL`                   | Required only for migrations                    | Migration-owner connection consumed by `scripts/migrate.py`.               | `postgresql://migration_role:password@localhost:5432/orion`             |
| `OPENAI_API_KEY`                                 | Required for voice and AI processing            | Server/worker OpenAI credential.                                           | `sk-...`                                                                |
| `OPENAI_ENTRY_ANALYSIS_MODEL`                    | Optional                                        | Structured entry-analysis model.                                           | `gpt-5.6-luna`                                                          |
| `OPENAI_REFLECTION_SYNTHESIS_MODEL`              | Optional                                        | Reflection synthesis model.                                                | `gpt-5.6-terra`                                                         |
| `OPENAI_REFLECTION_CRITIC_MODEL`                 | Optional                                        | Reflection critic model.                                                   | `gpt-5.6-sol`                                                           |
| `OPENAI_CONNECT_TIMEOUT_SECONDS`                 | Optional, default `10`                          | OpenAI connection timeout.                                                 | `10`                                                                    |
| `OPENAI_RESPONSE_TIMEOUT_SECONDS`                | Optional, default `60`                          | OpenAI response/read timeout.                                              | `60`                                                                    |
| `PROCESSING_TOTAL_TIMEOUT_SECONDS`               | Optional, default `300`                         | Total bound for model operations.                                          | `300`                                                                   |
| `ENTRY_ENCRYPTION_ACTIVE_KEY_ID`                 | Required for content encryption                 | Selects the active key from `ENTRY_ENCRYPTION_KEYS`.                       | `orion-entry-2026-01`                                                   |
| `ENTRY_ENCRYPTION_KEYS`                          | Required for content encryption                 | JSON map of key IDs to padded Base64-encoded 32-byte keys.                 | `{"orion-entry-2026-01":"BASE64_32_BYTE_KEY"}`                          |
| `ENTRY_FINGERPRINT_ACTIVE_KEY_ID`                | Required for fingerprints                       | Selects the active fingerprint key.                                        | `orion-fingerprint-2026-01`                                             |
| `ENTRY_FINGERPRINT_KEYS`                         | Required for fingerprints                       | JSON map of fingerprint key IDs to padded Base64 32-byte keys.             | `{"orion-fingerprint-2026-01":"BASE64_32_BYTE_KEY"}`                    |
| `REFLECTION_REVIEW_THRESHOLD`                    | Optional, production-fixed at `0.80`            | Drops low-confidence per-entry reflection extractions.                     | `0.80`                                                                  |
| `CORS_ALLOW_ORIGINS`                             | Optional, required and HTTPS-only in production | Comma-separated exact browser origins.                                     | `http://localhost:3000,http://127.0.0.1:3000`                           |
| `REQUEST_TIMEOUT_SECONDS`                        | Optional, default `30`                          | General API request timeout; voice upload is exempt.                       | `30`                                                                    |
| `MAX_REQUEST_BODY_BYTES`                         | Optional, default `1048576`                     | General request-body limit; voice has separate limits.                     | `1048576`                                                               |
| `DATABASE_POOL_SIZE`                             | Optional, default `5`                           | SQLAlchemy pool size per configured engine.                                | `5`                                                                     |
| `DATABASE_MAX_OVERFLOW`                          | Optional, default `5`                           | SQLAlchemy overflow connections.                                           | `5`                                                                     |
| `DATABASE_POOL_RECYCLE_SECONDS`                  | Optional, default `300`                         | Connection recycle interval.                                               | `300`                                                                   |
| `STARTUP_READINESS_TIMEOUT_SECONDS`              | Optional, default `10`                          | Database readiness and pool timeout.                                       | `10`                                                                    |
| `PROCESSING_JOB_POLL_SECONDS`                    | Optional, default `1`                           | Worker idle polling interval.                                              | `1`                                                                     |
| `PROCESSING_JOB_HEARTBEAT_SECONDS`               | Optional, default `30`                          | Running-job claim renewal interval.                                        | `30`                                                                    |
| `PROCESSING_JOB_STALE_SECONDS`                   | Optional, default `300`                         | Age after which an unrenewed running job is recoverable.                   | `300`                                                                   |
| `PROCESSING_JOB_RECOVERY_INTERVAL_SECONDS`       | Optional, default `60`                          | Worker stale-job recovery interval.                                        | `60`                                                                    |
| `PROCESSING_BACKFILL_MAX_QUEUE_DEPTH`            | Optional, default `1000`                        | Stops backfill batches when pending depth is too high.                     | `1000`                                                                  |
| `PROCESSING_BACKFILL_MAX_OLDEST_PENDING_SECONDS` | Optional, default `300`                         | Stops backfill batches when foreground work is too old.                    | `300`                                                                   |
| `REFLECTION_ENGINE_ENABLED`                      | Optional, default `false`                       | Allows reflection synthesis jobs to run.                                   | `false`                                                                 |
| `REFLECTION_SCHEDULER_ENABLED`                   | Optional, default `false`                       | Enables worker scheduler sweeps; requires the engine and active rollout.   | `false`                                                                 |
| `REFLECTION_API_ENABLED`                         | Optional, default `false`                       | Serves reflection reads/feedback; requires engine plus `publish` mode.     | `false`                                                                 |
| `REFLECTION_ROLLOUT_MODE`                        | Optional, default `off`                         | `off`, `shadow`, or `publish`; shadow does not create public snapshots.    | `off`                                                                   |
| `REFLECTION_ROLLOUT_USER_IDS`                    | Required for `shadow` or `publish`              | Comma-separated, unique user UUID cohort.                                  | `00000000-0000-4000-8000-000000000001`                                  |
| `REFLECTION_SCHEDULER_POLL_SECONDS`              | Optional, default `60`                          | Interval between scheduler sweeps in the worker loop.                      | `60`                                                                    |
| `REFLECTION_BASIS_DAYS`                          | Optional, fixed at `90`                         | Size of the longitudinal analysis window.                                  | `90`                                                                    |
| `WEB_CONCURRENCY`                                | Optional, production-fixed at `1`               | Keeps the in-process rate limiter correct.                                 | `1`                                                                     |
| `RATE_LIMITING_ENABLED`                          | Optional, production-required `true`            | Enables the process-local request limiter.                                 | `true`                                                                  |
| `LOG_FORMAT`                                     | Optional, default `json`                        | `json` or `text`; production requires JSON.                                | `json`                                                                  |
| `OTEL_ENABLED`                                   | Optional, default `false`                       | Enables OpenTelemetry traces and metric export.                            | `false`                                                                 |
| `OTEL_SERVICE_NAME`                              | Optional                                        | OTLP service name.                                                         | `orion-backend`                                                         |
| `OTEL_EXPORTER_OTLP_ENDPOINT`                    | Required only when OTEL is enabled              | HTTPS collector endpoint.                                                  | `https://otel.example.test:4317`                                        |
| `SUPABASE_TEST_EMAIL`                            | Optional, test-only                             | First live-proof account.                                                  | `orion-test-one@example.test`                                           |
| `SUPABASE_TEST_PASSWORD`                         | Optional, test-only                             | First live-proof account password.                                         | `replace-with-test-password`                                            |
| `SUPABASE_TEST_OTHER_EMAIL`                      | Optional, test-only                             | Second account for isolation proof.                                        | `orion-test-two@example.test`                                           |
| `SUPABASE_TEST_OTHER_PASSWORD`                   | Optional, test-only                             | Second account password.                                                   | `replace-with-test-password`                                            |
| `STAGE2_DISPOSABLE_DATABASE_URL`                 | Optional, test-only                             | Local disposable PostgreSQL database accepted by database tests.           | `postgresql://postgres:password@127.0.0.1:5432/orion_test`              |

## 6. Entry-to-reflection lifecycle

### Entry creation

#### Text

**Input.** `NewEntryScreen` accepts 1–10,000 trimmed characters. `useTextEntryDraft` restores and autosaves through `GET`/`PUT /api/v1/entry/draft`; an empty draft is discarded. Submission flushes the saved draft and sends `{ "content": "..." }` to `POST /api/v1/entry`.

**Processing and storage.** `EntryService` canonicalizes the content, computes an owner-bound fingerprint, encrypts it with AES-GCM, and calls `submit_text_entry_from_draft_for_owner`. The database submits the draft, creates an `entries` row, and enqueues an `entry_processing` job atomically. A matching saved draft is required.

**Output and status.** A new entry returns `201` (`200` for a replay) with an `EntryDetail`. The entry begins at `pending`; the worker moves it to `processing`, then `completed` or `failed`. The job moves `pending → running → completed|failed`, with retryable failures returning to `pending`.

**Relevant code.** `src/features/entries/new-entry-screen.tsx`, `src/features/entries/repository.ts`, `backend/app/modules/entries/service.py`, and migrations `0003`, `0006`, and `0007`.

#### Voice

**Input.** The browser records a `Blob` and sends one multipart field named `audio` to `POST /api/v1/entries/voice` with an `Idempotency-Key`. Supported MIME families are WAV, MP3, MP4/M4A, WebM, and Ogg. The frontend and backend enforce a 25 MB limit; the backend also enforces a 20-minute decoded duration.

**Processing and storage.** The backend streams the upload to a temporary file, validates its signature, runs ffprobe/FFmpeg decoding checks, and calls OpenAI Whisper-1 once with SDK retries disabled. It canonicalizes and encrypts the transcript; the raw audio file is deleted in the controller's cleanup path. The database creates the entry and shared processing job atomically.

**Output and status.** A new action returns `201`; replaying the same key/date returns `200`. Conflicting or concurrent use returns `409`. After transcription, the entry follows the same durable status lifecycle as text.

**Relevant code.** `src/features/entries/use-voice-recorder.ts`, `src/features/entries/repository.ts`, `backend/app/modules/entries/audio.py`, and `backend/app/modules/entries/controller.py`.

Historical entries use `POST /api/v1/past-entries`, return `202` plus a `Location` header, and enter the same shared processing queue. Their legacy review candidates are automatically approved with `decision_source='past_import_auto'` when processing completes.

### Segment extraction

The worker claims an `entry_processing` job with `FOR UPDATE SKIP LOCKED`, decrypts the entry locally, computes deterministic quality features, and runs Presidio/spaCy PII detection locally. PII mappings, the redacted text, and offset maps are encrypted before storage.

`create_source_segments` then splits the redacted journal into paragraphs and sentence-like spans. Each temporary `SourceSegment` has:

- `id`, such as `segment_0001`
- `start` and `end` character offsets
- a `selectable` flag that excludes empty, greeting, microphone-test, and simple-noise spans

The segment catalog is sent with the redacted entry-analysis request. GPT references segment IDs for ideas, memories, and theme evidence. The service resolves those references and translates selected redacted spans back to exact original-source quotes using the encrypted offset map.

There is no generic segment table or segment endpoint. Legacy selected text is materialized in `ideas` and `extracted_memories`; longitudinal atomic evidence is stored separately in `entry_signals` with exact original `source_start` and `source_end` offsets and an encrypted payload containing the quote and interpretation.

### Segment classification

One structured Luna response contains three related outputs:

1. **Quality classification.** The entry is classified as `personal_reflection`, `personal_event`, `personal_observation`, `task_or_note`, `informational_text`, `creative_writing`, `test_or_noise`, `copied_or_quoted_text`, or `unclear`, then finalized as `accepted`, `uncertain`, or `excluded`.
2. **Legacy extraction.** Selectable source segments may become ideas or memories; the response may also emit `filled_energy`, `drained_energy`, and `learned_about_self` per-entry reflections. Reflections below `REFLECTION_REVIEW_THRESHOLD` are omitted.
3. **Longitudinal signals.** Accepted entries may emit atomic `event`, `emotion`, `energy_gain`, `energy_loss`, `desire`, `avoidance`, `belief`, `self_statement`, `action`, `outcome`, `conflict`, `protective_strategy`, or `realization` signals with need tags, optional loop roles, themes, confidence, date, quote, and exact offsets.

Theme classification uses the fixed `default_8` catalog:

- Career
- Money
- Health
- Love Life
- Family & Friends
- Personal Growth
- Fun & Recreation
- Home & Lifestyle

Up to three themes are stored as primary, secondary, and tertiary with deterministic scores. Hard deterministic exclusions—such as empty content, test/noise, exact or near duplicates, repeated n-grams, or no meaningful content—skip the provider call and produce no longitudinal signals.

The combined analysis, signals, legacy candidates, entry completion, and reflection counters are committed atomically by the worker-side database function.

### Review workflow

The backend schema supports review candidates:

- `ideas` and `extracted_memories`: source text plus review lifecycle fields
- entry-level `reflections`: type, activity, confidence, and review lifecycle fields
- status: `pending_approval → approved|rejected`
- decision metadata: `decision_source` and `decided_at`

The authenticated entry-detail endpoint returns those rows, but no backend endpoints list a global review queue or change their status.

The current `/approvals` page uses `MockApprovalsRepository` and `mockOrionStore`. It filters pending fixture items and changes only process-local memory. The UI exposes Approve and Reject (described as “dismiss” in product copy); it does not implement editing. Refreshing/restarting the process can restore fixture state. Entry-detail review mutations are also wired to the mock `EntriesRepository`, not `HttpEntriesRepository`.

Therefore the current review actions do not send approved evidence to the production reflection engine. This is a confirmed implementation gap, not an implied endpoint.

### Reflection engine

The production engine reads accepted `entry_analyses` and their `entry_signals` across a fixed latest 90-day window. It does not read review statuses from legacy idea, memory, or entry-level reflection tables.

The worker's scheduler runs at its configured poll interval, but considers a cohort user only after 18:00 in that user's profile timezone and at most once per local date. It enqueues synthesis when there are at least three new valid entries, or at least two across two local dates, and at least one new accepted signal. The engine/API are off by default and require an explicit rollout cohort; only `publish` creates and serves snapshots, while `shadow` records non-content run counts.

Before any synthesis call, deterministic code:

- requires an overall basis of at least three valid entries, two distinct dates, and 200 reflective words;
- groups signals into hidden-driver, loop, and tension candidates;
- scores recurrence, temporal spread, context diversity, evidence strength, contradiction, duplication, and stability;
- enforces publication gates (`0.68` hidden driver, `0.72` recurring loop, `0.70` inner tension) plus type-specific evidence counts.

Eligible candidates go to GPT-5.6 Terra for constrained wording. A GPT-5.6 Sol critic is used when the candidate's risk/shape requires it. Every proposal is revalidated against allowed candidate IDs, signal IDs, owner and entry relationships, accepted analysis status, basis dates, offsets, evidence roles, date diversity, counterevidence, loop transitions, tension sides, and prohibited diagnostic/fixed-identity language. Invalid, unsupported, or critic-rejected proposals are discarded.

The three public pattern types are:

- **Hidden drivers:** a cautiously framed underlying need supported by repeated signals from multiple entries, dates, and signal types.
- **Recurring loops:** a repeated sequence of three to six supported loop steps, including the protection it offers and a possible interruption.
- **Inner tensions:** two canonically ordered needs, evidence for both sides, and a non-eliminating integration statement.

Selected candidates become a `reflection_snapshots` row and `reflection_snapshot_insights`. `reflection_snapshot_evidence` links every public insight to supporting or counter `entry_signals`, the originating `entries`, and exact source offsets. Public evidence is decrypted only when building the owner-scoped API response and includes date, source label, quote, interpretation, theme, and what it supports.

### Reflection screen

`HttpReflectionsRepository` calls:

```http
GET /api/v1/reflections?range=7d|30d|all
```

The backend always computes from the stored latest 90-day basis; `7d` and `30d` filter the evidence/date view inside that basis. Responses include `reflectionState`, `processingState`, snapshot metadata, analysis-basis counts, and all three sections in one request.

The frontend handles:

- **Loading:** `DataViewStatus` skeleton and retry behavior.
- **Initial processing:** `first_reflection_pending` processing state.
- **Empty:** `insufficient_reflective_content` or per-section `insufficient_evidence` messages.
- **Error:** initial/refresh errors, offline behavior, or `technical_failure` from a failed first synthesis.
- **Stale:** keeps the last snapshot visible while newer entries are pending or after refresh failure.
- **Populated:** client-local tabs render hidden drivers, recurring loops, and inner tensions without another fetch; an evidence drawer shows linked excerpts.
- **No evidence in range:** hides available insights without supporting evidence in the selected range; inner tensions retain only evidence-backed items and show a tab-level no-results state when none remain.

Every authenticated visit requests the aggregate endpoint. Backend rollout and
cohort controls remain authoritative; an unavailable backend returns the normal
technical error and retry state.

Insight feedback uses:

```http
PUT /api/v1/reflections/{snapshot_id}/insights/{insight_id}/feedback
```

with `resonates`, `partly`, or `rejected`. The frontend applies an optimistic update and rolls it back on error. This feedback concerns aggregate insights and is separate from the mock review queue.

## 7. Architecture diagram

```mermaid
flowchart TD
    User[User] --> EntryForm[Next.js entry form]
    EntryForm -->|text draft and submit| EntryAPI[FastAPI entry API]
    EntryForm -->|voice multipart| Voice[FFmpeg checks and Whisper-1]
    Voice --> EntryAPI
    EntryAPI -->|encrypted entry plus pending job| DB[(PostgreSQL / Supabase)]
    DB --> Queue[processing_jobs]
    Queue -->|pending to running| Worker[Shared processing worker]
    Worker --> Privacy[Local decrypt, quality checks, and PII redaction]
    Privacy --> Luna[GPT-5.6 Luna structured analysis]
    Privacy -->|hard exclusion: no provider call| Combined[Validated combined result]
    Luna --> Combined
    Combined --> Legacy[Ideas, memories, and per-entry reflections]
    Legacy --> ReviewRows[(pending_approval review rows)]
    ReviewUI[Approvals screen] --> MockStore[In-memory mock store only]
    MockStore --> MockDecision[Mock approve or reject]
    ReviewRows -. no backend review endpoint .- MockStore
    Combined --> Signals[(accepted entry_analyses and entry_signals)]
    Signals --> Scheduler[18:00 local scheduler and rollout gates]
    Scheduler -->|reflection_synthesis job| Queue
    Worker --> Candidate[Deterministic pattern scoring and evidence gates]
    Candidate --> Terra[GPT-5.6 Terra synthesis]
    Terra --> Sol[Conditional GPT-5.6 Sol critic]
    Sol --> Validation[Evidence and safety validation]
    Validation --> Snapshot[(reflection snapshots, insights, and evidence)]
    Snapshot --> ReflectionAPI[GET /api/v1/reflections]
    ReflectionAPI --> ReflectionScreen[Hidden drivers / Recurring loops / Inner tensions]
```

The dashed review link documents the disconnect: the database review rows and mock review store are not synchronized, and neither approval path feeds `entry_signals`.

## 8. Data models

| Model                                                | Important fields                                                                                                                                                                          | Relationships and lifecycle                                                                                                                                                       |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entry (`entries`)                                    | `id`, `user_id`, encrypted `content_envelope`, `input_type`, `entry_date`, theme config, processing status/token/error, source draft, timestamps                                          | Owner-scoped root record. Status is `pending`, `processing`, `completed`, or `failed`; cascades to analyses and extracted material.                                               |
| Source segment (`SourceSegment`)                     | Temporary `id`, `start`, `end`, `selectable`                                                                                                                                              | In-memory span over redacted text. Used for strict model references and exact source recovery; not persisted as its own table.                                                    |
| Review item                                          | `ideas`/`extracted_memories`: content; entry-level `reflections`: type, activity, confidence; all include owner, entry, status, decision source, and dates                                | Belongs to one entry. Status is `pending_approval`, `approved`, or `rejected`. There is no combined backend `review_items` table or review API.                                   |
| Entry analysis (`entry_analyses`)                    | entry kind, model/final eligibility, deterministic features, semantic scores, exclusion reasons, encrypted redacted text/offset map, word count, model and prompt version, source version | One combined analysis version for an entry; accepted analyses may own many signals.                                                                                               |
| Entry signal (`entry_signals`)                       | type, encrypted label/interpretation/quote payload, themes, need tags, loop role, confidence, exact offsets, date, duplicate cluster                                                      | Belongs to an entry and accepted analysis. This is the actual input evidence for longitudinal reflection.                                                                         |
| Pattern candidate (`pattern_candidates`)             | type, canonical key, encrypted structure/score components, score, status, version, rejection metadata, source version                                                                     | Deterministically constructed from signals; status can be `candidate`, `published`, `weakened`, `superseded`, or `rejected`. Evidence links live in `pattern_candidate_evidence`. |
| Reflection snapshot (`reflection_snapshots`)         | owner, version, source version, 90-day basis bounds/counts, status, timestamps                                                                                                            | Immutable aggregate generation. `reflection_snapshot_insights` holds available or insufficient sections.                                                                          |
| Reflection evidence (`reflection_snapshot_evidence`) | insight, signal, entry, owner, supporting/counter role, ordinal, exact offsets                                                                                                            | Connects each public insight back to an owned signal and entry. The API resolves it into bounded source excerpts.                                                                 |
| Reflection feedback (`reflection_feedback`)          | snapshot, insight, candidate, response, timestamps                                                                                                                                        | Owner-scoped `resonates`, `partly`, or `rejected` response. Rejection affects candidate lifecycle; “partly” is supplied as a future synthesis qualification.                      |
| Processing job (`processing_jobs`)                   | owner, optional entry, job type, execution mode, priority, source version, status, run time, attempts, claim/worker/heartbeat, error, completion                                          | Stores both `entry_processing` and `reflection_synthesis`. Maximum three attempts; retryable failures wait 30 seconds after the first attempt and two minutes thereafter.         |

## 9. API overview

All `/api/v1` operations require a Supabase bearer access token. Ownership comes from the verified token, not a caller-supplied user ID.

| Capability                       | Method and path                                                        | Current behavior                                                                                                            |
| -------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Restore text draft               | `GET /api/v1/entry/draft`                                              | Returns the authenticated user's decrypted active draft.                                                                    |
| Save/clear text draft            | `PUT /api/v1/entry/draft`                                              | Encrypts and replaces the active draft; blank content discards it.                                                          |
| Discard text draft               | `DELETE /api/v1/entry/draft`                                           | Discards the active unsent draft.                                                                                           |
| Create text entry                | `POST /api/v1/entry`                                                   | Submits the matching saved draft, stores an encrypted entry, and enqueues processing.                                       |
| Create voice entry               | `POST /api/v1/entries/voice`                                           | Validates/transcribes multipart audio, stores an encrypted transcript, and enqueues processing. Requires `Idempotency-Key`. |
| Create historical entry          | `POST /api/v1/past-entries`                                            | Returns `202`, an entry ID, status URL, and `Location` header.                                                              |
| Fetch entries                    | `GET /api/v1/entries?page=1&page_size=20`                              | Returns an owner-scoped page with decrypted previews and completed initial themes.                                          |
| Fetch entry detail               | `GET /api/v1/entries/{entry_id}`                                       | Returns source content, status, classification, and legacy extracted candidates.                                            |
| Retry failed entry               | `POST /api/v1/entries/{entry_id}/retry`                                | Requeues only a failed entry and resets its processing state.                                                               |
| Fetch review items               | **Not implemented**                                                    | `/approvals` reads the frontend mock store; there is no backend review-list endpoint.                                       |
| Approve/dismiss/edit review item | **Not implemented**                                                    | Approve/reject is mock-only; edit is absent. No backend mutation endpoint exists.                                           |
| Trigger reflections manually     | **Not implemented**                                                    | The worker's cohort-aware scheduler is the only synthesis enqueuer.                                                         |
| Fetch reflections                | `GET /api/v1/reflections?range={7d,30d,all}`                           | Returns one owner-scoped aggregate snapshot response when rollout/API gates allow it.                                       |
| Save reflection feedback         | `PUT /api/v1/reflections/{snapshot_id}/insights/{insight_id}/feedback` | Upserts `resonates`, `partly`, or `rejected` feedback.                                                                      |
| Backend health                   | `GET /health`                                                          | Anonymous opaque liveness response: `{"status":"ok"}`.                                                                      |
| Frontend health                  | `GET /api/health`                                                      | Next.js health route used by local browser-test startup.                                                                    |

The frozen backend contract is `backend/docs/contracts/profile-entry-v1.openapi.yaml`.

## 10. AI usage

### Model calls

| Step                 | Model                      | Input and output                                                                                                                |
| -------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Voice transcription  | `whisper-1`                | Raw temporary audio to plain transcript. One bounded call; SDK retries disabled.                                                |
| Entry analysis       | `gpt-5.6-luna` by default  | Locally redacted journal text, deterministic features, allowed catalogs, and selectable offsets to strict `ModelEntryAnalysis`. |
| Reflection synthesis | `gpt-5.6-terra` by default | Deterministically eligible candidate/evidence context to strict hidden-driver, loop, tension, or abstention proposals.          |
| Reflection critic    | `gpt-5.6-sol` by default   | Selected higher-risk proposal and evidence context to a strict publish/discard critique.                                        |

Prompts are in `backend/app/modules/processing/prompts.py` and `backend/app/modules/reflection_engine/prompts.py`. Pydantic output schemas are in the corresponding `schemas.py` files. Calls use `responses.parse`, `store=False`, truncation disabled, strict schemas, a pseudonymous safety identifier, explicit timeouts, and SDK `max_retries=0`.

Deterministic code handles segmentation, trivial-span exclusion, duplicate/noise features, final quality gates, fixed theme scores, source-offset translation, candidate construction, scoring, publication thresholds, feedback lifecycle, evidence checks, and snapshot selection. It can exclude an entry without calling a model.

Provider transport failures classified as transient are retried by the durable queue, not the OpenAI SDK. Jobs allow three attempts with database-managed delays. Invalid schemas, malformed offsets, unsupported evidence, safety violations, and other terminal validation failures are not retried as successful content.

Unsupported reflections are prevented through layered controls: basis thresholds; deterministic candidate gates; owner/entry/analysis checks; exact quote offsets; supporting/counterevidence roles; date and entry diversity; loop-transition and tension-side rules; restricted language checks; strict model schemas; and conditional critic approval. Rejected candidates remain suppressed until enough newer evidence exists.

No tracked file or Git history metadata in this checkout verifiably identifies code as generated by Codex. This README therefore makes no claim about how Codex was used to build the project.

## 11. Privacy and security

This section describes implemented controls, not a legal or compliance guarantee.

| Area                            | Implemented behavior                                                                                                                                                                                                                                               |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Raw journal text                | Drafts and entries are canonicalized and stored as application-level AES-GCM envelopes. Authenticated list/detail endpoints decrypt owner-scoped content to serve the user.                                                                                        |
| Voice recordings                | Uploaded audio is streamed to a temporary file, checked for format and duration, sent to Whisper-1 for transcription, and deleted in cleanup. Raw audio is not stored in the Orion database by this code.                                                          |
| Entry-analysis provider request | Presidio/spaCy redaction runs locally first. The request contains redacted text, deterministic features, catalogs, and offsets; OpenAI response storage is disabled.                                                                                               |
| Reflection provider request     | The worker sends selected candidate/evidence context to Terra and sometimes Sol. This can include evidence text derived from decrypted signal payloads; the code disables provider response storage but does not establish a broader provider-retention guarantee. |
| Database storage                | Journal content, PII mappings, redacted text, offset maps, signal payloads, pattern structures, and insight payloads use encrypted envelopes. Metadata, statuses, dates, scores, themes, offsets, and relationships remain queryable.                              |
| Authentication                  | The browser uses Supabase Auth with session persistence in `sessionStorage` and automatic refresh. Backend `/api/v1` routes verify `Authorization: Bearer <access-token>`.                                                                                         |
| User isolation                  | API transactions set the authenticated database role and JWT claims; migrations enable and force RLS on sensitive tables. Worker transactions use a separate `orion_worker` role. Live two-account proof is still listed as pending.                               |
| Logs                            | Structured logging accepts only allowlisted event names and fields. Content, transcripts, prompts, evidence, provider payloads, tokens, envelopes, mappings, and exception strings are not passed through `safe_log`.                                              |
| Secrets                         | Frontend configuration contains only public values. Backend keys and database URLs are read from environment variables. Production validation requires distinct app/worker roles and valid encryption/fingerprint key maps.                                        |
| HTTP boundary                   | Exact-origin CORS, request/body timeouts, body limits, request IDs, owner-scoped no-store reflection responses, and in-process rate limits are implemented.                                                                                                        |

The current encryption master-key maps are environment-held. `backend/docs/DEPLOYMENT.md` identifies a real KMS-backed key source, rotation, and recovery runbook as release blockers.

## 12. MVP limitations

- The review queue is mock-backed. It does not fetch or update PostgreSQL review candidates.
- Approve/reject actions are process-local mock mutations; editing review items is not implemented.
- Approved legacy review items do not feed the production reflection engine. The engine uses accepted atomic signals instead.
- No manual reflection-trigger endpoint exists. Scheduling is worker-only, cohort-scoped, daily after 18:00 local time, and threshold-gated.
- Reflection engine, scheduler, API, and frontend reflection querying all default to disabled. Public serving requires `publish` mode and an explicit UUID cohort.
- The longitudinal window is fixed at 90 days; minimum basis counts and publication thresholds are hard-coded for the MVP.
- The API rate limiter is in-process and settings enforce one API instance/one Uvicorn worker. Horizontal scaling requires a shared limiter.
- OpenAI SDK retries are disabled; the durable queue retries only allowlisted transient failures and stops after three attempts.
- Encryption and fingerprint master keys come from environment JSON maps. Production KMS integration and its rotation/recovery runbook are not implemented.
- The deployment documentation says live Supabase/RLS, authentication cascade, and cross-user decryption proofs remain waived/pending.
- The repository intentionally has no fabricated 100-record consented reflection-evaluation dataset or claimed evaluation result.
- The Next.js `src/app/api/v1/entries/route.ts` is an authenticated fixture route, while production entry screens use `NEXT_PUBLIC_API_BASE_URL` and the FastAPI `HttpEntriesRepository`. Running with an empty API base URL can therefore reach fixture behavior instead of the real backend.
