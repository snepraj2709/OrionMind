# Reflections API

## Release controls

Reflections are fail-closed. The backend settings
`REFLECTION_ENGINE_ENABLED`, `REFLECTION_SCHEDULER_ENABLED`, and
`REFLECTION_API_ENABLED` all default to `false`; `REFLECTION_ROLLOUT_MODE`
defaults to `off`, with an empty `REFLECTION_ROLLOUT_USER_IDS` cohort. Enabling
the scheduler requires the engine, `shadow` or `publish` mode, and an explicit
UUID cohort. The public API requires the engine and `publish`; it does not
require the scheduler because an eligible aggregate GET can request an
immediately claimable synthesis job through the same worker queue.

When `REFLECTION_API_ENABLED=false`, both operations below return the same
opaque `503 SERVICE_UNAVAILABLE` envelope with `Cache-Control: private,
no-store`. The service gate runs before any Reflection repository read,
feedback write, or provider call. The routes remain in the frozen inventory
and OpenAPI contract.

The same gate applies to authenticated users outside the configured rollout
cohort, so cohort membership cannot be inferred from a different response.
Shadow mode runs synthesis and validation in the worker but never writes a
public snapshot, candidate, insight, or evidence row.

The authenticated Reflections screen always requests this API. Backend release
and cohort controls remain authoritative: disabled or out-of-cohort reads return
the opaque `503` response above, which the screen presents as a technical error
with Retry. The client query key remains
`['reflections', user.id, range]`.

These controls do not change entry ingestion or processing. Text, voice,
historical import, retry, and operator backfill continue through the shared
`processing_jobs` queue. Production Reflections must remain disabled until the
P0-09D release blocker is resolved with a real KMS-backed key source, rotation,
and recovery procedure; environment-held key maps do not satisfy that
requirement.

## Aggregate read

`GET /api/v1/reflections?range=7d|30d|all`

`range` is required and closed to `7d`, `30d`, or `all`. The request has no
client-supplied owner and no active-tab parameter. Ownership comes only from
the authenticated Supabase bearer token. The client keeps the user ID in its
TanStack Query key (`['reflections', user.id, range]`) to isolate browser cache
state, but never sends it in the URL.

The response is one strict aggregate containing:

- `range`, `reflectionState`, and `processingState`;
- nullable immutable snapshot metadata;
- the capped 90-day `analysisBasis`;
- hidden-driver, recurring-loop, and inner-tensions sections.

Each section is a closed discriminated union: `available` or
`insufficient_evidence`. Available insights carry opaque IDs, confidence,
score, persisted feedback, and their own evidence. Inner tensions contain one
to five available tension insights; zero tensions use the insufficient union.
Unknown fields and enum values are rejected by the client schema.

The screen requests the aggregate once per range. Switching Reflection tabs is
local UI state and makes no request. `all` means all eligible evidence within
the bounded 90-day basis, not lifetime history.

Before reading the aggregate, the service checks the latest accepted source
version and the deterministic minimum basis: three accepted entries, two
distinct dates, and 200 reflective words. When eligible work is newer than the
latest snapshot, GET idempotently inserts one publish-mode synthesis job with
`run_after=now()`. If the scheduler already created the same pending job for a
future time, GET moves only that pending job forward to `now()`. Running,
completed, and terminal failed jobs are never reset by repeated reads. The
unique `(user_id, job_type, source_version)` constraint prevents duplicate
model calls for the same source version.

## Feedback write

`PUT /api/v1/reflections/{snapshotId}/insights/{insightId}/feedback`

```json
{ "response": "resonates" }
```

`response` is closed to `resonates`, `partly`, or `rejected`. Success returns
`snapshotId`, `insightId`, `response`, and `updatedAt`. Repeating the same
selection is idempotent; a different valid selection replaces it. The client
optimistically updates only that insight, suppresses duplicate submissions
while it is pending, rolls back on failure, and then reconciles the current
user/range cache.

The server verifies ownership from authentication and returns an opaque `404`
for a cross-owner or mismatched snapshot/insight pair. Feedback is preference
and correction context; it is never journal evidence.

## States and caching

- `available`: render the latest snapshot.
- `first_reflection_pending`: keep controls and show a calm processing state.
- `stale` plus `pending` or `failed`: keep the last snapshot visible with an
  update or failure status.
- `insufficient_reflective_content`: show the server-safe message and a New
  Entry action.
- section-level `insufficient_evidence`: keep the tabs and show the section's
  server-safe no-results message.
- an available insight with no evidence in the selected range: show a
  tab-level no-results state; for inner tensions, retain only tensions with
  range evidence and show no results if none remain.
- no-snapshot technical failure: the server returns `503`; the client shows its
  technical error and retry state without fabricating insufficiency.

Missing sections, empty response objects, empty `available` tension arrays,
unknown fields, and unknown enum values are contract violations. Strict client
validation routes them to the same technical error and retry state rather than
interpreting them as empty reflection data.

Both operations are authenticated and return `Cache-Control: private,
no-store`. Aggregate GET may request asynchronous synthesis, but performs no
model or provider call inside the HTTP request. The removed singular
`/api/v1/reflection` Next.js fixture route is not a fallback. Static reflection
copy, builders, adapters, and mock repositories remain test-only infrastructure
and are not exported through the production feature entrypoint.
