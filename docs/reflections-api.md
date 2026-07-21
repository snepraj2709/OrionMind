# Reflections screen-data API

## Endpoint

`GET /api/v1/reflection?userId={id}&reflectionTab={tab}&range={range}`

The endpoint requires the mock authenticated session and accepts:

- `reflectionTab`: `all`, `hiddenDriver`, `recurringLoop`, or `innerTension`.
- `range`: `7d`, `30d`, or `all`.
- `userId`: the authenticated user's ID. A different ID receives `403`.

Missing or invalid parameters receive `400`; an unauthenticated request receives `401`.

## Response contract

Every response contains the authenticated `userId`, requested `reflectionTab`, requested `range`, a `period`, and `data`:

```ts
interface ReflectionPeriod {
  entryCount: number;
  totalAvailable: number;
  from: string | null;
  to: string | null;
}
```

Specific-tab requests return that tab's screen-ready payload directly. `all` returns `{ hiddenDriver, recurringLoop, innerTension }`. The discriminated Zod union in `src/features/reflections/api-schema.ts` is the executable wire contract.

The current Reflections screen intentionally requests only its active tab. Its TanStack Query key contains the user ID, API tab, and date range. Feedback selections, labels, icons, and diagram geometry remain client-owned UI state and are not part of this read endpoint.

## Client configuration and authentication

`src/config/api.ts` is the single backend-base configuration. It reads `NEXT_PUBLIC_API_BASE_URL`; an empty value keeps requests on the same origin and therefore uses this Next.js fixture route. Setting the variable to a backend origin sends the unchanged `/api/v1/reflection` request to that origin. Restart or rebuild Next.js after changing a public environment value.

The shared API request includes browser session credentials and never sends a body with `GET`. The current contract explicitly requires `userId` as a query parameter, but the endpoint still derives the authenticated user from the signed session and rejects a mismatched ID. The query parameter is not trusted as authorization.

For a cross-origin backend, that backend must allow the frontend origin with credentialed CORS and the `Authorization` header. The shared API client reads the current Supabase session and supplies its access token as a bearer credential; Reflection components and schemas do not own authentication details.

## Temporary fixture boundary

The handler derives its response from the eight static entries and screenshot copy in `src/features/reflections/fixtures.ts`. Authentication and user matching are production-shaped, but every authenticated user currently receives the same fixture content.

Approved items in Review do not update this endpoint. Review still records approved reflection evidence in the local mock store, but Reflections remains static until a persistent backend connects both features. The injectable mock repository can supply alternate data in unit tests; it is not the default screen data path.
