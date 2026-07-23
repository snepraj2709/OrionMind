# Reflection observability and preflight

This is the P0-09C operator contract. It adds no public route and does not authorize a deployment,
provider call, shared-database mutation, backfill, or production flag change.

## OTLP instruments

The required metrics are:

- `reflection_jobs_total{type,status,error_code}`
- `reflection_job_duration_seconds{type}`
- `reflection_queue_depth{type}`
- `reflection_entry_eligibility_total{result,kind}`
- `reflection_signals_total{signal_type}`
- `reflection_candidates_total{pattern_type,outcome}`
- `reflection_validator_discards_total{reason_code}`
- `reflection_api_responses_total{reflection_state,processing_state}`
- `reflection_feedback_total{response}`

Two operational instruments complete the P0-09C queue and scheduler requirements:

- `reflection_queue_oldest_pending_age_seconds{type}`
- `reflection_scheduler_users_total{outcome}` where outcome is `checked`, `eligible`, or `enqueued`

Stage 12 adds three Review-to-Reflection health instruments:

- `reflection_review_feedback_total{scope,weight_bucket,outcome}` where the
  buckets are `zero`, `half`, and `full`, and the outcome is `changed` or
  `replayed`
- `reflection_synthesis_sections_total{pattern_type,execution_mode,outcome}`
  where execution mode is `shadow` or `publish` and outcome is `available` or
  `abstained`
- `reflection_job_retries_total{type,outcome}` where outcome is `attempted`,
  `scheduled`, or `terminal`

Use `reflection_queue_oldest_pending_age_seconds` as the bounded queue-wait
signal and `reflection_job_duration_seconds{type="reflection_synthesis"}` as
the end-to-end synthesis duration. Retry counters are events rather than
unique-job counts: one retried terminal attempt contributes both `attempted`
and `terminal`. Feedback replay is measured separately so idempotent client
retries are not mistaken for changed user decisions.

All labels are fixed enums or controlled error/reason codes. User IDs, arbitrary text, routes, UUIDs,
and model responses are never metric labels. Metrics are periodically exported to the configured OTLP
collector; there is no Prometheus or other HTTP metrics endpoint.

### Stage 12 inventory and privacy classification

| Signal family                      | Interpretation                                           | Privacy classification         |
| ---------------------------------- | -------------------------------------------------------- | ------------------------------ |
| Job outcome/duration               | Worker health and processing or synthesis duration       | Aggregate operational metadata |
| Queue depth/oldest age             | Backlog size and upper-bound queue wait                  | Aggregate operational metadata |
| Entry/candidate/validator outcomes | Pipeline acceptance, selection, and discard counts       | Closed taxonomy metadata       |
| API state                          | Cached Reflection state combinations returned to clients | Closed state metadata          |
| Review weight/outcome              | Scope-level decision weight and changed/replayed counts  | Closed decision metadata       |
| Synthesis section outcome          | Available versus abstained section counts                | Closed outcome metadata        |
| Retry outcome                      | Retry attempts, scheduling, and terminal outcomes        | Closed lifecycle metadata      |

Every family forbids entry/user/job/snapshot/candidate IDs as metric labels.
It also forbids journal text, Review statements, source quotes, corrections,
notes, evidence payloads, model output, prompts, and exception strings.

## Logs and traces

Reflection code emits events only through the structured allowlist. Permitted values include opaque
record UUIDs, controlled states/codes, counts, safe durations, configured model role/ID, prompt
version, token counts returned by the provider, and retry class. A matched HTTP route template may be
logged; the raw URL is not used.

Never record raw or redacted journal text, prompts containing journal/evidence content, quotes,
interpretations, PII or placeholder mappings, encrypted envelopes, provider responses, bearer tokens,
or exception strings. Manual model spans disable automatic exception recording and carry the same
allowlisted model-attempt fields. The sentinel regression test injects private text into both input and
an exception and asserts that neither logs nor exported spans contain it.

## Offline privacy startup

`en_core_web_sm` is installed as a pinned dependency. Startup initializes Presidio locally and
configures `tldextract` with `suffix_list_urls=()`, `cache_dir=None`, and the packaged suffix snapshot.
No home-directory cache or network suffix fetch is permitted. Initialization failure stops startup.

## Model access preflight

Run only after network access is authorized:

```bash
cd backend
.venv/bin/python scripts/check_reflection_model_access.py
```

The command reuses the configured `OPENAI_API_KEY` without printing it. It calls Models `retrieve`
once for each configured entry-analysis, synthesis, and critic model. It never accesses the Responses
API. Output contains only role, configured model ID, and available/unavailable status. Failure text
from the provider is discarded.

## Frozen evaluation gate

The evaluation input contains no journal text. Its top-level schema is:

```json
{
  "version": 1,
  "records": [
    {
      "entry_id": "00000000-0000-4000-8000-000000000000",
      "consent_granted": true,
      "expected": {
        "idea_spans": [{ "start": 0, "end": 12 }],
        "memory_spans": [],
        "top_theme": "career",
        "invalid_structured_output": false,
        "reflection_polarity": {
          "filled_energy": "positive",
          "drained_energy": "negative",
          "learned_about_self": "neutral"
        }
      },
      "combined_analyzer": {
        "idea_spans": [{ "start": 0, "end": 12 }],
        "memory_spans": [],
        "top_theme": "career",
        "invalid_structured_output": false,
        "reflection_polarity": {
          "filled_energy": "positive",
          "drained_energy": "negative",
          "learned_about_self": "neutral"
        }
      },
      "legacy_invalid_structured_output": false
    }
  ]
}
```

Run:

```bash
cd backend
.venv/bin/python scripts/run_reflection_evaluation.py /authorized/path/results.json
```

The harness rejects duplicate IDs, unknown fields, any unconsented record, and fewer than 100
records. It emits aggregate results only and passes only when exact-span precision is at least `0.90`,
top-theme agreement is at least `0.95`, combined invalid structured outputs do not exceed the legacy
count, and polarity regressions are zero. No consented frozen dataset or
claimed production-quality result is committed.

## Synthetic Review-to-Reflection evaluation

Stage 12 includes a strict, metadata-only synthetic fixture with 24 cases
across four correctness dimensions. It covers the accepted control plus both
excluded and uncertain garbage boundaries; exact evidence plus missing,
each individual signal/entry/analysis owner mismatch, entry mismatch, both
non-accepted analysis states, out-of-basis and unavailable-basis cases, and
out-of-bounds and offset-mismatched evidence; available and abstaining outcomes
for all three section types; and feedback sensitivity across weights `1`, `.5`,
and `0`. It contains no journal text, Review text, UUID, or stable user
identity.

Run it offline:

```bash
cd backend
.venv/bin/python scripts/run_reflection_evaluation.py \
  --review-reflection tests/fixtures/review_reflection_evaluation_v1.json
```

The report contains only aggregate case counts by dimension. Evaluation inputs
are expected outcomes, while observed outcomes are computed by production-owned
Review materialization, evidence validation, section-status, and
review-weighted-confidence rules. A passing result therefore means accepted
input retains its proposed Review items while excluded or uncertain input
creates none; evidence validation returns the exact expected closed reason-code
set for each identity, entry, eligibility, basis, and offset boundary; only the
fully local exact-span case is valid; unsupported sections abstain
independently; and effective confidence matches the closed `1/.5/0`
calculation.

This fixture is a regression contract, not a production-quality benchmark.
Do not derive rollout thresholds, model-quality claims, or user-level
decisions from it. Production quality thresholds require a separately
authorized, representative, consented evaluation design.
