# Reflections API

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
- no-snapshot technical failure: the server returns `503`; the client shows its
  technical error and retry state without fabricating insufficiency.

Both operations are authenticated, return `Cache-Control: private, no-store`,
and perform no synchronous model or provider call. The removed singular
`/api/v1/reflection` Next.js fixture route is not a fallback. Static reflection
copy, builders, adapters, and mock repositories remain test-only infrastructure
and are not exported through the production feature entrypoint.
