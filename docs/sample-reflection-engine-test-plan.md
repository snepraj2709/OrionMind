# Sample Reflection Engine test plan

## Outcome

Add one live, authenticated test runner that consumes
`data/sample-entries.json`, exercises the production Reflection Engine path, and
writes a concise result to `data/sample-reflection-result.json`.

The local runner and its non-billable tests are implemented. A result is valid
only after the live command completes; `sample-reflection-result.json` must
never be populated with invented or fixture-derived measurements.

## Dataset findings

- The input is an array of 30 journal entries dated 1–30 June 2026.
- Every entry has one non-empty string in `content`.
- The dataset contains approximately 4,715 words and 26,713 characters.
- Convert each human-readable `entry_date` to ISO `YYYY-MM-DD` before calling
  the API.
- Join `content` items with two newlines. This preserves a future multi-part
  entry without changing the current one-item records.
- Reject unknown fields, duplicate dates, blank content, invalid dates, future
  dates, and entries outside the backend's ten-year historical-import window.

## Implemented model architecture

| Stage                         | Model           | Invocation                                                                                                  | Responsibility                                                                                                                                     |
| ----------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entry processing              | `gpt-5.6-luna`  | Once for each entry that passes deterministic exclusion                                                     | Classify entry quality, preserve the existing idea/memory/reflection extraction, and extract the controlled signals used by the Reflection Engine. |
| Deterministic aggregation     | No model        | Once after accepted entry signals are available                                                             | Build and score hidden-driver, recurring-loop, and inner-tension candidates from the bounded 90-day basis.                                         |
| Reflection synthesis          | `gpt-5.6-terra` | Once when at least one deterministic candidate passes its publication gate                                  | Turn eligible cross-entry candidates into non-diagnostic, evidence-bound reflection wording.                                                       |
| Conditional critic            | `gpt-5.6-sol`   | Once per synthesized candidate when `abs(score - publication_threshold) <= 0.05` or `contradiction >= 0.20` | Return a publish/discard judgment. It cannot rewrite the candidate, add evidence, or raise its score.                                              |
| Local validation and snapshot | No model        | After Terra and any required Sol calls                                                                      | Validate ownership, evidence spans, counterevidence, language, thresholds, and persist the immutable snapshot.                                     |
| Reflections API and frontend  | No model        | On authenticated reads                                                                                      | Return and render the persisted aggregate. Reads never invoke Luna, Terra, or Sol.                                                                 |

The configured defaults are:

```text
OPENAI_ENTRY_ANALYSIS_MODEL=gpt-5.6-luna
OPENAI_REFLECTION_SYNTHESIS_MODEL=gpt-5.6-terra
OPENAI_REFLECTION_CRITIC_MODEL=gpt-5.6-sol
```

The live result must report actual calls, token counts, durations, and outcomes
from the existing safe model-attempt logs. In particular, zero Sol calls is a
valid measured result when no candidate meets the deterministic critic rule; it
must be reported as `not_invoked`, not treated as evidence that Sol is broken.

## Authentication and configuration

The root `.env` is the frontend/Playwright environment. Its
`SUPABASE_TEST_EMAIL` and `SUPABASE_TEST_PASSWORD` are already consumed by the
authenticated browser tests.

`backend/.env` is loaded by backend `Settings`, but the test credential names
are intentionally not backend application settings. The proposed runner must
explicitly read those two test-only values from both files, verify that both
pairs are present and identical, and never print or store them.

The runner will then:

1. Sign in to Supabase with the test email and password.
2. retain the access token only in process memory;
3. obtain the authenticated user UUID from the session;
4. use the bearer token for every protected API request; and
5. configure that UUID as the sole Reflection rollout cohort for the run.

The Reflection Engine flags are absent from the current `backend/.env`, so
their defaults are off. The runner should override them in process without
editing either environment file:

```text
REFLECTION_ENGINE_ENABLED=true
REFLECTION_SCHEDULER_ENABLED=true
REFLECTION_API_ENABLED=true
REFLECTION_ROLLOUT_MODE=publish
REFLECTION_ROLLOUT_USER_IDS=<authenticated test user UUID>
```

The production model IDs remain explicit in the run metadata. Before journal
content is submitted, run the existing Models API preflight for all three IDs.
That check retrieves model metadata only and does not create Responses.

## Isolation rule

The run fails closed unless every Reflection-owned data table is empty for the
test user. Existing entries, imports, jobs, analyses, signals, candidates,
snapshots, evidence, or feedback could change behavior or make the result
impossible to attribute exclusively to `sample-entries.json`.

Do not automatically delete user data. A later implementation may support an
explicit `--reset-test-user` option, but it must resolve the exact test-user UUID,
show the affected record counts, and require separate authorization before any
destructive cleanup. The safe default is a dedicated empty Supabase test user.

## Implemented runner

`backend/scripts/run_sample_reflection_e2e.py` has this interface:

```bash
backend/.venv/bin/python backend/scripts/run_sample_reflection_e2e.py \
  --input data/sample-entries.json \
  --output data/sample-reflection-result.json \
  --frontend-env .env \
  --backend-env backend/.env
```

The runner should use the real application boundaries while remaining
deterministic and one-shot:

1. Validate the input and compute its SHA-256 digest.
2. Validate credential parity without logging secret values.
3. Sign in and run the three-model access preflight.
4. Build the FastAPI application with the test user as a one-user `publish`
   cohort.
5. Use the authenticated protected route
   `POST /api/v1/past-entries` for all 30 entries. Keep rate limiting enabled
   and pace submissions to no more than two per second.
6. Run the real `ProcessingWorker.run_one` loop until all 30
   `entry_processing` jobs reach a terminal state. This invokes Luna for every
   entry that passes deterministic exclusion.
7. Assert the account now contains exactly the submitted dataset and that
   failed entry jobs are zero.
8. Invoke the real scheduler once with a controlled timestamp after 18:00 in
   the test user's stored timezone. Assert that exactly one
   `reflection_synthesis` job is enqueued for the latest accepted source
   version.
9. Run the same worker loop until that synthesis job is terminal. This invokes
   Terra once when publishable candidates exist and invokes Sol only for
   candidates matching the production critic rule.
10. Call `GET /api/v1/reflections?range=all` with the same bearer token and
    validate the strict public response schema.
11. Summarize the API response and safe model-attempt records, then write the
    result atomically through a temporary file followed by a same-directory
    rename.
12. Remove the access token, credentials, raw user UUID, raw prompts, and raw
    provider responses from all report and error paths.

This in-process route/worker approach exercises authentication, protected API
routes, encryption, the real Supabase database, queue claims, Luna analysis,
deterministic candidate construction, Terra synthesis, conditional Sol review,
snapshot persistence, and the public read model. It avoids waiting for wall
clock 18:00 or managing long-running development processes.

## Result contract

`data/sample-reflection-result.json` contains a concise run summary plus the
canonical public API result:

- `run`: dataset digest, timestamps, entry count, execution boundaries, rollout
  mode, and a one-way test-user hash;
- `timingSeconds`: authentication, model preflight, submission, entry
  processing, scheduling, synthesis, final GET, and total wall time;
- `modelUsage.pricing`: the official pricing source and estimation caveats;
- `modelUsage.roles`: Luna, Terra, and Sol routing, calls, success counts,
  tokens, model wall time, latency distribution, and estimated USD;
- `modelUsage.calls`: one safe measurement per provider attempt, including
  service tier, cached input, cache-write input, reasoning output, status, and
  retry class;
- `databaseEffects`: exact per-user row counts and grouped entry, analysis,
  signal, job, candidate, and insight states;
- `reflectionGetResponse`: the schema-validated body returned by authenticated
  `GET /api/v1/reflections?range=all`;
- `checks`, `errors`, and `operationalNuances`: succinct pass/fail evidence and
  behavior that materially affects interpretation.

Cost is estimated from the response usage and the actual returned service tier.
If a tier cannot be priced, the runner sets `pricingComplete` to `false` and
the total to `null` rather than silently undercounting it. OpenAI billing remains
the authoritative amount.

On failure, still write a valid report with `status: "failed"`, completed checks,
and controlled error codes. Never include credentials, tokens, email addresses,
raw user IDs, provider exception text, or full journal entries.

## Pass criteria

- Input validation succeeds for all 30 entries.
- The two environment files contain an identical test credential pair.
- Supabase sign-in succeeds and the bearer token is accepted by protected
  routes.
- Model access preflight succeeds for Luna, Terra, and Sol.
- Exactly 30 historical imports are accepted and all entry jobs terminate
  without failure.
- Luna attempts equal the number of entries that reached semantic analysis;
  for this reflective dataset, the expected count is 30.
- The scheduler enqueues exactly one synthesis job for the latest source
  version.
- Terra is called exactly once when at least one publishable candidate exists.
- Sol calls equal the number of synthesized candidates satisfying the critic
  rule. Zero is allowed only when `eligibleCandidates` is zero.
- The final aggregate is `available` and `idle`, its evidence belongs only to
  the submitted June dates, and every quote is an exact span of its source
  entry.
- The result passes its JSON schema, contains no secret material, and is written
  to `data/sample-reflection-result.json`.

## Verification for the implementation change

```bash
cd backend && .venv/bin/python -m pytest tests/test_sample_reflection_e2e.py -q
cd ..
npm run typecheck
npm run lint
npm test
npm run build
```

Run the live command only after confirming the test account is isolated and
authorizing the expected provider usage: approximately 30 Luna Responses, one
Terra Response when candidates are publishable, and zero or more conditional
Sol Responses.
