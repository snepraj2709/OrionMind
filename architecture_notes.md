# Reflection endpoint design

## Build order

Entry-quality gate and exact evidence extraction.
Atomic signal storage and embeddings.
Controlled need aggregation.
Hidden-driver synthesis.
Inner-tension synthesis.
Recurring-loop transition detection.
Evidence critic and abstention responses.
Incremental scheduling.
Privacy deletion and evaluation harness.

## MVP Architecture

```
                          ┌────────────────────────┐
                          │ POST /entries          │
                          └───────────┬────────────┘
                                      │
                               Store encrypted raw
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Entry processing worker  │
                         └───────────┬──────────────┘
                                     │
             ┌───────────────────────┼─────────────────────────┐
             ▼                       ▼                         ▼
      Safety screening       Quality/garbage gate       PII redaction
             │                       │                         │
             └─────────────── accepted entry ──────────────────┘
                                     │
                                     ▼
                         Atomic signal extraction
                                     │
                         Store signals + embeddings
                                     │
                                     ▼
                       Increment reflection counters
                                     │
                          Should reflection update?
                                     │
                                     ▼
                       Reflection synthesis worker
                                     │
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
       Hidden drivers        Recurring loops        Inner tensions
              │                      │                      │
              └──────────── evidence validation ────────────┘
                                     │
                                     ▼
                      Versioned reflection snapshot
```

## tools and tech stack

FastAPI;
Supabase PostgreSQL;
pgvector;
one PostgreSQL-backed worker queue;
OpenAI Responses API with Pydantic Structured Outputs;
a local PII scrubber;
scheduled incremental and weekly recalculation.
