# Reflection Engine 30-entry breakdown

## Live end-to-end result — 22 July 2026

The 30 June 2026 sample entries completed the production path against the live
Supabase database and deployed Railway worker. All 30 entry jobs had already
completed with Luna before the synthesis defect was fixed. The controlled
source-version `76` retry reused those persisted analyses and signals; it did
not resubmit entries or call Luna again.

| Measurement                           |                                         Live result |
| ------------------------------------- | --------------------------------------------------: |
| Entry jobs                            |                                        30 completed |
| Accepted analyses                     |                                                  30 |
| Persisted signals reused by synthesis |                                                 394 |
| Deterministic candidates              |                                                 169 |
| Publication-gate candidates           |                                                  80 |
| Terra calls during retry              |                                        1 successful |
| Sol calls during retry                |                                        1 successful |
| Luna calls during retry               |                                                   0 |
| Snapshot                              |             version 1, source version 76, available |
| Available snapshot insights           | 1 hidden driver, 1 recurring loop, 4 inner tensions |
| Snapshot evidence links               |                                                 684 |
| Authenticated aggregate read          |                HTTP 200, available, idle, not stale |

### Live per-entry processing

This table is derived from persisted live rows. It intentionally excludes raw
journal content, quotes, PII, prompts, credentials, and model output text.

|   # | Entry date | Luna classification | Words | Final eligibility | Signals |
| --: | ---------- | ------------------- | ----: | ----------------- | ------: |
|   1 | 2026-06-01 | personal_reflection |   159 | accepted          |      11 |
|   2 | 2026-06-02 | personal_reflection |   157 | accepted          |      13 |
|   3 | 2026-06-03 | personal_reflection |   161 | accepted          |      14 |
|   4 | 2026-06-04 | personal_reflection |   156 | accepted          |      15 |
|   5 | 2026-06-05 | personal_reflection |    93 | accepted          |      10 |
|   6 | 2026-06-06 | personal_reflection |   159 | accepted          |      14 |
|   7 | 2026-06-07 | personal_reflection |   200 | accepted          |      11 |
|   8 | 2026-06-08 | personal_reflection |   160 | accepted          |       7 |
|   9 | 2026-06-09 | personal_reflection |   156 | accepted          |      14 |
|  10 | 2026-06-10 | personal_reflection |   171 | accepted          |      13 |
|  11 | 2026-06-11 | personal_reflection |   160 | accepted          |      14 |
|  12 | 2026-06-12 | personal_reflection |    85 | accepted          |      10 |
|  13 | 2026-06-13 | personal_reflection |   158 | accepted          |      14 |
|  14 | 2026-06-14 | personal_reflection |   160 | accepted          |      14 |
|  15 | 2026-06-15 | personal_reflection |   148 | accepted          |      13 |
|  16 | 2026-06-16 | personal_reflection |   167 | accepted          |      12 |
|  17 | 2026-06-17 | personal_reflection |   222 | accepted          |      16 |
|  18 | 2026-06-18 | personal_reflection |    89 | accepted          |      12 |
|  19 | 2026-06-19 | personal_reflection |   162 | accepted          |      15 |
|  20 | 2026-06-20 | personal_reflection |   233 | accepted          |      16 |
|  21 | 2026-06-21 | personal_reflection |   156 | accepted          |      15 |
|  22 | 2026-06-22 | personal_reflection |   157 | accepted          |      11 |
|  23 | 2026-06-23 | personal_reflection |   102 | accepted          |      11 |
|  24 | 2026-06-24 | personal_reflection |   160 | accepted          |      15 |
|  25 | 2026-06-25 | personal_reflection |   154 | accepted          |      14 |
|  26 | 2026-06-26 | personal_reflection |   162 | accepted          |      11 |
|  27 | 2026-06-27 | personal_reflection |   193 | accepted          |      15 |
|  28 | 2026-06-28 | personal_reflection |   212 | accepted          |      20 |
|  29 | 2026-06-29 | personal_reflection |    68 | accepted          |       9 |
|  30 | 2026-06-30 | personal_reflection |   165 | accepted          |      15 |

Every entry was processed exactly once by Luna and ended accepted. The signal
counts total 394, matching the basis loaded by the successful synthesis.

### Live synthesis and aggregate response

The first synthesis attempt failed before any provider call because a
recurring-loop step had an empty support-ID list. After the cycle-edge evidence
fix was deployed, the one approved retry completed in 43.124 seconds:

| Role      | Model           | Calls | Input tokens | Cache-write input tokens | Output tokens | Result  |
| --------- | --------------- | ----: | -----------: | -----------------------: | ------------: | ------- |
| Synthesis | `gpt-5.6-terra` |     1 |       50,204 |                   50,201 |         4,892 | success |
| Critic    | `gpt-5.6-sol`   |     1 |        3,510 |                    3,507 |           304 | success |

The additional synthesis/critic usage estimate is `$0.261319375`; together
with the earlier 30 Luna calls, the measured run estimate is `$1.007730625`.
These are response-usage estimates using the harness pricing table; the OpenAI
billing dashboard remains authoritative.

The deployed authenticated `GET /api/v1/reflections?range=all` returned:

- hidden driver: “A possible pattern across your entries may involve
  contribution through helping, taking responsibility, and repairing
  connection, while the value you place on the work may not depend only on
  praise.”
- recurring loop: “Managing pressure through more activity”
- inner tensions: control/rest, clarity/control, belonging/stability, and
  recognition/security.

The GET returned the already-current snapshot and created no new job or model
call.

## Offline fixture reference

### Offline proof boundary

The offline fixture run passed for all 30 entries in
`data/sample-entries.json`. It exercised the real deterministic quality,
candidate construction, scoring, synthesis materialization, evidence
validation, critic routing, snapshot, insight, and evidence-row code paths.

This is **not live OpenAI or Supabase proof**. Entry-analysis signals and
synthesis language came from deterministic local fixtures. The run made zero
external model calls and zero external database writes. It does not establish
model quality, token usage, latency, cost, deployed RLS, queue behavior, or
networking.

Machine-readable evidence is in
`data/sample-reflection-offline-result.json`.

### Offline aggregate outcome

| Measurement                   | Result            |
| ----------------------------- | ----------------- |
| Proof mode                    | `offline_fixture` |
| Input entries                 | 30                |
| Deterministically accepted    | 30                |
| Deterministically excluded    | 0                 |
| Reflective words              | 4,685             |
| Fixture signals               | 96                |
| Constructed candidates        | 6                 |
| Publication-gate candidates   | 4                 |
| Snapshot-published candidates | 3                 |
| Snapshot evidence rows        | 88                |
| External model calls          | 0                 |
| External database writes      | 0                 |
| Fixture synthesis calls       | 1                 |
| Fixture critic calls          | 1                 |

The snapshot contains one available hidden driver, one available recurring
loop, and one available inner tension. A second publishable hidden-driver
candidate was correctly retained but not selected because a snapshot publishes
at most one hidden driver.

### Offline per-entry breakdown

The table intentionally excludes journal content, quotes, PII, credentials,
and model prompts. `Signals` are deterministic fixture records and must not be
interpreted as semantic findings about the entries.

|   # | Entry date | Words | Meaningful tokens | Fixture signals | Controlled signal types                    | Hard exclusions |
| --: | ---------- | ----: | ----------------: | --------------: | ------------------------------------------ | --------------- |
|   1 | 2026-06-01 |   159 |               104 |               8 | avoidance, event, self_statement           | None            |
|   2 | 2026-06-02 |   157 |               108 |               1 | desire                                     | None            |
|   3 | 2026-06-03 |   161 |               106 |               1 | action                                     | None            |
|   4 | 2026-06-04 |   156 |               101 |               1 | self_statement                             | None            |
|   5 | 2026-06-05 |    93 |                73 |               8 | avoidance, desire, event                   | None            |
|   6 | 2026-06-06 |   159 |               105 |               1 | action                                     | None            |
|   7 | 2026-06-07 |   200 |               142 |               1 | self_statement                             | None            |
|   8 | 2026-06-08 |   160 |               104 |               1 | desire                                     | None            |
|   9 | 2026-06-09 |   156 |               104 |               9 | action, avoidance, conflict, event         | None            |
|  10 | 2026-06-10 |   171 |               119 |               2 | conflict, self_statement                   | None            |
|  11 | 2026-06-11 |   160 |               103 |               2 | conflict, desire                           | None            |
|  12 | 2026-06-12 |    85 |                66 |               2 | action, conflict                           | None            |
|  13 | 2026-06-13 |   158 |               114 |               9 | avoidance, conflict, event, self_statement | None            |
|  14 | 2026-06-14 |   160 |               109 |               2 | conflict, desire                           | None            |
|  15 | 2026-06-15 |   148 |               106 |               2 | action, conflict                           | None            |
|  16 | 2026-06-16 |   167 |               112 |               2 | conflict, self_statement                   | None            |
|  17 | 2026-06-17 |   222 |               157 |               9 | avoidance, conflict, desire, event         | None            |
|  18 | 2026-06-18 |    89 |                66 |               2 | action, conflict                           | None            |
|  19 | 2026-06-19 |   162 |               112 |               1 | self_statement                             | None            |
|  20 | 2026-06-20 |   233 |               165 |               1 | desire                                     | None            |
|  21 | 2026-06-21 |   156 |               113 |               8 | action, avoidance, event                   | None            |
|  22 | 2026-06-22 |   157 |               108 |               1 | self_statement                             | None            |
|  23 | 2026-06-23 |   102 |                76 |               1 | desire                                     | None            |
|  24 | 2026-06-24 |   160 |               112 |               1 | action                                     | None            |
|  25 | 2026-06-25 |   154 |               102 |               8 | avoidance, event, self_statement           | None            |
|  26 | 2026-06-26 |   162 |               115 |               1 | desire                                     | None            |
|  27 | 2026-06-27 |   193 |               139 |               1 | action                                     | None            |
|  28 | 2026-06-28 |   212 |               156 |               1 | self_statement                             | None            |
|  29 | 2026-06-29 |    68 |                50 |               8 | avoidance, desire, event                   | None            |
|  30 | 2026-06-30 |   165 |               115 |               1 | action                                     | None            |

Every entry produced a deterministic quality record. The fixture deliberately
adds a repeated six-transition loop across eight dates, a repeated competence
signal across the month, and bilateral autonomy/belonging evidence across ten
dates. This makes each pattern gate testable without pretending a local ruleset
understands the journal's meaning.

### Offline candidate and snapshot outcome

| Pattern type   | Candidate status | Score | Gate | Snapshot result |
| -------------- | ---------------- | ----: | ---- | --------------- |
| Hidden driver  | Published        | 0.838 | Pass | Available       |
| Hidden driver  | Candidate        | 0.721 | Pass | Not selected    |
| Hidden driver  | Candidate        | 0.778 | Fail | Not eligible    |
| Hidden driver  | Candidate        | 0.778 | Fail | Not eligible    |
| Recurring loop | Published        | 0.734 | Pass | Available       |
| Inner tension  | Published        | 0.767 | Pass | Available       |

The critic was invoked once because at least one selected score was within the
production borderline-routing band. The fixture critic returned a strict
publish decision and did not rewrite evidence or scores.

### Offline diagnosis outcome

The offline feedback loop initially produced only two available sections. The
recurring-loop fixture scored `0.619`, below the documented `0.72` publication
gate. Instrumentation showed that the fixture had compressed a four-transition
cycle into the first eight days. After changing only the fixture to a
six-transition cycle distributed across the month, the same production scoring
path produced `0.734` and published the loop.

This falsified a deterministic recurring-loop validator defect for the tested
case. It also demonstrated that the local candidate, proposal, evidence, critic,
and snapshot boundaries can publish valid fixtures for all three pattern types.

The retained historical live result remains unexplained at its provider
boundary: it contains 45 publication-gate candidates but an all-insufficient
snapshot. Because that run did not capture proposal discard reasons, offline
fixtures cannot prove whether Terra omitted references, changed a controlled
field, used rejected phrasing, or abstained. No production synthesis fix is
justified without that missing trace.

### Offline provisional implementation score

The current implementation receives a provisional **80/100 offline-confidence
score**. This is not a production-readiness score.

| Area                                  | Earned | Weight | Offline evidence and remaining gap                                     |
| ------------------------------------- | -----: | -----: | ---------------------------------------------------------------------- |
| Ingestion, encryption and ownership   |     11 |     15 | Automated coverage exists; no fresh deployed write proof               |
| Queue, retries and worker lifecycle   |     11 |     15 | Backend suite covers lifecycle; offline fixture bypasses live queue    |
| Quality, PII and exact offsets        |     15 |     20 | Real deterministic quality; semantic analysis and live PII path absent |
| Candidate algorithms and thresholds   |     15 |     15 | All three candidate types and score gates exercised                    |
| Synthesis, critic and evidence safety |     10 |     15 | Real validators with fixture proposals; model behavior unproven        |
| Scheduler and snapshot integrity      |      8 |     10 | Snapshot path plus scheduler tests; no deployed scheduling proof       |
| Aggregate API contract                |      5 |      5 | Strict API state matrix covered by backend tests                       |
| Observability and reproducibility     |      5 |      5 | Deterministic artifact, per-entry breakdown, explicit limitations      |

### Recommended next steps

1. Keep `data/sample-reflection-result.json` labeled as historical and
   non-canonical; do not replace it with this fixture artifact.
2. Run the canonical harness only in an approved environment using an empty
   test account. Preserve its safe proposal-discard events.
3. If the live run is all-insufficient, rank the captured reason codes and add
   a regression at the exact proposal/validator seam before changing
   production logic or prompts.
4. Rotate the test-account password that was shared during setup.
