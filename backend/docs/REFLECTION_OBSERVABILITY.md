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

All labels are fixed enums or controlled error/reason codes. User IDs, arbitrary text, routes, UUIDs,
and model responses are never metric labels. Metrics are periodically exported to the configured OTLP
collector; there is no Prometheus or other HTTP metrics endpoint.

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
count, and polarity regressions are zero. No evaluation dataset or claimed pass result is committed.
