# Reflection Algorithm

**evidence-backed hypothesis engine** that identifies:

- recurring motives visible across entries;
- repeated behaviour–emotion–outcome cycles;
- competing needs that repeatedly appear together;
- counterevidence and uncertainty.

### MVP Reflection Architecture

```tsx
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

### Tech Stack

- FastAPI;
- Supabase PostgreSQL;
- `pgvector`;
- one PostgreSQL-backed worker queue;
- OpenAI Responses API with Pydantic Structured Outputs;
- a local PII scrubber;
- scheduled incremental and weekly recalculation.

### User entry

- Dummy entry

  ```json
  {
    "id": "entry-123",
    "input_type": "text",
    "content": "This morning I sat with my coffee longer than usual, watching the light change across the kitchen wall. There was something in that stillness — a kind of permission to exist without producing anything.",
    "processing_status": "processing",
    "created_at": "2026-07-20T14:30:00.000Z"
  }
  ```

---

# Store observations

- EntrySignal class

  ```tsx
  class EntrySignal(BaseModel):
      id: UUID
      user_id: UUID
      entry_id: UUID

      signal_type: Literal[
          "event",
          "emotion",
          "energy_gain",
          "energy_loss",
          "desire",
          "avoidance",
          "belief",
          "self_statement",
          "action",
          "outcome",
          "conflict",
          "protective_strategy",
          "realization",
      ]

      normalized_label: str
      interpretation: str

      # Must be copied exactly from the entry
      source_quote: str
      source_start: int
      source_end: int

      themes: list[str]
      need_tags: list[str]
      loop_role: str | None

      valence: float | None
      agency: float | None
      confidence: float

      occurred_at: datetime
      embedding: list[float] | None
  ```

- Signal extractions for the dummy entry

  ```json
  [
    {
      "signal_type": "emotion",
      "normalized_label": "anticipatory anxiety",
      "source_quote": "I felt nervous beforehand",
      "need_tags": ["competence", "security"],
      "confidence": 0.94
    },
    {
      "signal_type": "energy_gain",
      "normalized_label": "clarity through explanation",
      "source_quote": "explaining it clearly gave me energy",
      "need_tags": ["competence", "contribution"],
      "confidence": 0.96
    },
    {
      "signal_type": "energy_loss",
      "normalized_label": "rushed preparation",
      "source_quote": "The rushed preparation was exhausting",
      "need_tags": ["stability", "competence"],
      "confidence": 0.95
    },
    {
      "signal_type": "realization",
      "normalized_label": "slow preparation increases self-trust",
      "source_quote": "I trust myself more when I prepare slowly",
      "need_tags": ["competence", "autonomy"],
      "confidence": 0.97
    }
  ]
  ```

The reflection engine operates on these signals rather than repeatedly sending hundreds of raw journal entries to an LLM.

---

# Garbage and non-reflective entry detection

## Stage A: deterministic checks

Calculate:

```python
class DeterministicQualityFeatures(BaseModel):
    word_count: int
    meaningful_token_count: int
    unique_token_ratio: float
    repeated_ngram_ratio: float
    alphabetic_character_ratio: float
    exact_duplicate: bool
    near_duplicate_similarity: float | None
    repeated_recent_entry_count: int
```

Examples:

- `"hello testing mic"` → very few meaningful tokens.
- Ten identical entries → normalized hash duplicates.
- Slight variations such as `"hello testing mic one"` → embedding similarity and repeated n-grams.
- Blank transcription or background noise → low meaningful-token count.

Do not reject an entry only because it is short. This is a valid short reflection:

> “Felt dismissed after the call, so I avoided replying.”

## Stage B: semantic quality classifier

Use a small model with this schema:

```python
class EntryQualityResult(BaseModel):
    entry_kind: Literal[
        "personal_reflection",
        "personal_event",
        "personal_observation",
        "task_or_note",
        "informational_text",
        "creative_writing",
        "test_or_noise",
        "copied_or_quoted_text",
        "unclear",
    ]

    lived_experience_score: float
    self_reference_score: float
    emotional_information_score: float
    causal_reasoning_score: float
    personal_relevance_score: float

    safe_for_pattern_analysis: bool
    exclusion_reasons: list[str]
    confidence: float
```

suggested decision

```python
def pattern_eligibility(result: EntryQualityResult) -> str:
    if result.entry_kind in {
        "test_or_noise",
        "informational_text",
        "copied_or_quoted_text",
        "task_or_note",
    } and result.confidence >= 0.80:
        return "excluded"

    reflective_score = (
        0.30 * result.lived_experience_score
        + 0.20 * result.self_reference_score
        + 0.20 * result.emotional_information_score
        + 0.15 * result.causal_reasoning_score
        + 0.15 * result.personal_relevance_score
    )

    if reflective_score >= 0.60:
        return "accepted"

    if reflective_score >= 0.40:
        return "uncertain"

    return "excluded"
```

OpenAI’s Structured Outputs can enforce the JSON schema, but unrelated inputs can still cause fabricated schema-compatible values unless the prompt defines how to return empty or incompatible results. Schema therefore needs explicit `safe_for_pattern_analysis`, `exclusion_reasons` and empty-signal behaviour.

## How test cases behave

### Ten entries saying “hello testing mic”

```json
{
  "status": "excluded",
  "entryKind": "test_or_noise",
  "safeForPatternAnalysis": false,
  "reasons": [
    "No personal experience, emotion, decision or reflection was expressed.",
    "Highly similar content has already been submitted."
  ]
}
```

No signals are created. Reflection counters do not increase.

### Repeated textbook paragraphs

```json
{
  "status": "excluded",
  "entryKind": "informational_text",
  "safeForPatternAnalysis": false,
  "reasons": [
    "The text explains a general subject rather than describing the user's lived experience."
  ]
}
```

---

# 4. Controlled ontology for the MVP

Do not let the LLM invent arbitrary psychological labels.

Use a limited non-clinical need ontology:

```json
NEEDS= ["autonomy","competence","mastery","belonging","recognition","security","stability","novelty","exploration","meaning","contribution","creative_expression","rest","physical_vitality","clarity","control"]
```

Use limited set of loop roles:

```json
LOOP_ROLES= ["trigger","initial_reward","interpretation","emotional_response","action","avoidance","short_term_protection","long_term_cost","recovery","reinforcement",
]
```

The LLM maps evidence into these categories while preserving an exact source quote.

This gives you stable aggregation while still allowing the final wording to feel personal.

# 5. The algorithm

## Separate long-term identity from the selected date range

A serious flaw would be inferring a user’s “hidden driver” from only the last three entries.

Maintain two layers:

```json
Long-term pattern ledger
90 days / all available valid entries
        ↓
Current range activation
Which established or emerging patterns appeared in the selected 7d/30d range?
```

For a seven-day view, say:

> “This week reinforced a longer-running pattern…”

rather than rebuilding the user’s identity from that week.

## Step 1: eligibility

Before running synthesis:

```tsx
eligible= (
	valid_entry_count>=3 and
	distinct_entry_dates>=2 and
	reflective_word_count>=200
)
```

Confidence levels:

```
3–4 valid entries  → preliminary signal
5–9 valid entries  → emerging pattern
10+ valid entries  → recurring pattern
```

These are product thresholds, not scientific cut-offs. Tune them using your evaluation set.

## Step 1.5: retrieve semantic signal neighbors

For each accepted signal in the requested 90-day synthesis basis, retrieve at
most eight same-owner neighbors from the same 1,536-dimension embedding model.
Use exact pgvector cosine distance with a minimum similarity of `0.90`; exclude
the anchor and all signals from its source entry. Null embeddings, different
models, excluded analyses, future source versions, and signals outside the
basis do not participate.

Semantic retrieval augments deterministic grouping; it does not create a new
candidate type or change candidate identity. A retrieved pair may share a
duplicate/support cluster only when signal type, loop role, counterevidence
role, and at least one controlled need or theme are compatible. Resolve ties by
date and opaque IDs, and never extend similarity transitively: `A ~ B` and
`B ~ C` do not imply `A ~ C`.

## Step 2: update the candidate ledger

Maintain candidate rows instead of recreating everything from scratch.

```tsx
class PatternCandidate(BaseModel):
    id: UUID
    user_id: UUID

    pattern_type: Literal[
        "hidden_driver",
        "recurring_loop",
        "inner_tension",
    ]

    canonical_key: str
    status: Literal[
        "candidate",
        "published",
        "weakened",
        "superseded",
        "rejected",
    ]

    first_seen_at: datetime
    last_seen_at: datetime

    supporting_entry_ids: list[UUID]
    contradicting_entry_ids: list[UUID]

    evidence_score: float
    version: int
```

# 6. Hidden-driver detection

A hidden-driver candidate begins with repeated `need_tags`.

Example aggregation:

```
competence
├── energy gain: explaining difficult ideas
├── energy gain: completing a difficult implementation
├── self-knowledge: preparation increases self-trust
├── energy loss: feeling unprepared
└── conflict: wanting recognition without superficial approval
```

Calculate:

```tsx
hidden_driver_score =
  0.3 * recurrence_score +
  0.2 * temporal_spread_score +
  0.15 * context_diversity_score +
  0.15 * evidence_entailment_score +
  0.1 * signal_type_diversity_score +
  0.1 * stability_score -
  0.2 * contradiction_score -
  0.15 * duplicate_evidence_score;
```

Publish only when:

```tsx
supporting_entries >= 3;
distinct_dates >= 2;
supporting_signal_types >= 2;
hidden_driver_score >= 0.68;
```

The synthesis prompt receives:

- candidate need;
- supporting evidence spans;
- contradicting evidence;
- number of dates and contexts;
- previous version of the pattern.

It should not receive the full corpus.

---

# 7. Recurring-loop detection

Extract a small causal chain from each valid entry when present:

```tsx
{
  "trigger":"An interesting new possibility appears",
  "interpretation":"This may be the direction I should pursue",
  "emotion":"Excitement",
  "action":"Explore several related options",
  "shortTermProtection":"Avoid committing before knowing the best option",
  "longTermCost":"Attention fragments and progress feels insufficient"
}
```

Then create transition counts:

```tsx
new possibility → excitement                 7 times
excitement → multiple exploration paths       5 times
multiple paths → fragmented attention         4 times
fragmentation → perceived lack of progress    4 times
lack of progress → urgency/self-doubt         3 times
self-doubt → search for new possibilities     3 times
```

A loop is eligible when:

```
observed_chains>=3supporting_entries>=3supported_transitions>=4distinct_dates>=2loop_score>=0.72
```

Do not force exactly six steps. Return between three and six steps depending on the evidence.

The validator must check:

- each step has evidence;
- adjacent steps are causally plausible from the entries;
- the final step reconnects to the first;
- repeated wording is not being mistaken for repeated behaviour;
- the “protection” is framed as a hypothesis.

# 8. Inner-tension detection

A tension is not merely two different topics. It requires evidence that two valued needs compete.

Candidate:

```
Exploration versus completion
```

Evidence for exploration:

- energy from discovering new concepts;
- repeated new project ideas;
- desire to preserve optionality.

Evidence for completion:

- frustration about insufficient visible progress;
- satisfaction from shipping;
- desire for competence and credibility.

Score:

```tsx
tension_score =
  0.25 * left_side_support +
  0.25 * right_side_support +
  0.2 * direct_conflict_evidence +
  0.15 * temporal_alternation +
  0.15 * cross_context_recurrence -
  0.2 * contradiction_or_unrelatedness;
```

Publish only when:

```tsx
left_supporting_entries>=2right_supporting_entries>=2distinct_dates>=2tension_score>=0.70
```

The integration statement should not say “choose one.” It should describe a practical arrangement that honours both sides.

# 9. Evidence validation

Every published sentence must pass deterministic checks.

```tsx
def validate_evidence(item: EvidenceItem, entries: dict[str, Entry]) -> None:
    entry = entries[item.entry_id]

    assert item.user_id == entry.user_id
    assert item.text in entry.decrypted_content
    assert item.source_start >= 0
    assert item.source_end <= len(entry.decrypted_content)
```

Additional rules:

- no evidence from another user;
- no quote rewritten by the LLM;
- no more than 40% of evidence from one entry;
- at least two distinct dates;
- evidence IDs must exist;
- no diagnosis or disorder labels;
- no “you are…” personality declarations;
- counterevidence must be passed to the validator;
- an unsupported insight is discarded, not repaired creatively.

# 10. Revised reflection response schema

Add explicit abstention and confidence.

```tsx
{
  "userId":"reader-id",
  "range":"7d",
  "analysisBasis": {
    "window":"90d",
    "validEntryCount":18,
    "excludedEntryCount":4,
    "distinctEntryDates":11
  },
  "data": {
    "hiddenDriver": {
      "status":"available",
      "confidence":"emerging",
      "score":0.74,
      "statement":"A possible pattern across your entries...",
      "underlyingNeed":"...",
      "evidence": []
    },
    "recurringLoop": {
      "status":"insufficient_evidence",
      "reasonCode":"LOOP_NOT_REPEATED",
      "message":"Several reactions appeared, but the same sequence has not repeated often enough to call it a recurring loop.",
      "observedEntryCount":2,
      "minimumSuggestedEntryCount":3
    },
    "innerTension": {
      "status":"available",
      "confidence":"preliminary",
      "tensions": []
    }
  }
}
```

## Garbage-only response

```tsx
{
  "status":"insufficient_reflective_content",
  "message":"There is not enough personal reflection to identify a meaningful pattern yet.",
  "details": {
    "submittedEntryCount":10,
    "validReflectiveEntryCount":0,
    "excludedEntryCount":10,
    "excludedReasons": {
      "test_or_noise":10
    }
  },
  "nextRequirement":"Add personal experiences, feelings, decisions or realizations across at least two different days."
}
```

# 11. Incremental scheduling

Use three triggers:

```python
should_recalculate = (
    new_valid_entries_since_snapshot >= 3
    or new_reflective_words_since_snapshot >= 500
    or (
        oldest_pending_valid_entry_age >= timedelta(days=3)
        and new_valid_entries_since_snapshot >= 1
    )
)
```

Execution:

1. Process every entry immediately.
2. Increment `valid_entries_since_reflection`.
3. Run an hourly scheduler.
4. At the user’s local 6 PM, check whether recalculation criteria are met.
5. Skip users with no new valid signals.
6. Perform a full 90-day rebuild weekly to correct incremental drift.

Use a PostgreSQL job table:

```sql
create table processing_jobs (
    id uuid primary key,
    user_id uuid not null,
    job_type text not null,
    status text not null default 'pending',
    run_after timestamptz not null,
    attempts integer not null default 0,
    source_version text not null,
    error text,
    created_at timestamptz not null default now(),

    unique (user_id, job_type, source_version)
);
```

Workers claim jobs using `FOR UPDATE SKIP LOCKED`. This is enough for the MVP and avoids introducing Redis or Celery solely for queueing.

---

# 12. Privacy architecture

## Raw content

Store journal content using application-level envelope encryption:

```tsx
User-specific Data Encryption Key
        ↓ encrypts
Journal content using AES-GCM
        ↓
Encrypted DEK is wrapped by cloud KMS
```

Database administrators should not see plaintext simply by querying the table.

## Before LLM processing

Run local PII replacement:

```
Sneha spoke to Rahul at Acme
        ↓
<USER> spoke to <PERSON_1> at <ORG_1>
```

Keep the mapping encrypted separately. Use stable placeholders within a user so longitudinal relationships remain detectable.

Microsoft Presidio is an open-source starting point for detecting and anonymising PII, but treat it as one layer rather than proof that all PII has been removed. Its repository supports custom NLP and pattern-based recognisers, and recent issues demonstrate why leakage tests remain necessary.

Also:

- disable provider-side storage where supported;
- never log raw prompts;
- redact traces;
- record IDs, latency, token counts and prompt versions only;
- cascade-delete raw entries, signals, embeddings and snapshots;
- use Supabase RLS with `user_id` on every table;
- separate production and evaluation datasets;
- require explicit consent before using anonymised entries for product evaluation.

---

# 13. Model and prompt setup

Use configurable roles:

```python
class ModelConfig(BaseSettings):
    entry_model: str = "gpt-5.6-luna"
    synthesis_model: str = "gpt-5.6-terra"
    difficult_review_model: str = "gpt-5.6-sol"
```

Use the entry_model for quality classification and signal extraction. Use the synthesis_model for cross-entry synthesis. Only escalate difficult or disputed cases to difficult_review_model after evals show a measurable benefit.

Use Responses API Structured Outputs with Pydantic rather than parsing arbitrary JSON.

## Prompt sequence

### Prompt 1: entry analyser

One call returns:

```
quality classification
+ safety-neutral signal extraction
+ exact evidence spans
+ empty signals when unsuitable
```

Include contrastive examples:

- valid emotional reflection;
- short but valid reflection;
- textbook paragraph;
- “hello testing mic”;
- repeated entry;
- fictional first-person passage;
- prompt injection inside a journal entry.

### Prompt 2: candidate generator

Input:

```
previous pattern ledger
new atomic signals
aggregate need counts
candidate transition graph
candidate tensions
retrieved evidence
counterevidence
```

Output three to five candidates, not final UI copy.

### Prompt 3: evidence critic

For each candidate:

```
{
  "entailed":true,
  "overreaches":false,
  "contradictoryEvidenceIgnored":false,
  "diagnosticLanguage":false,
  "evidenceDiversityAdequate":true,
  "recommendedAction":"publish"
}
```

### Prompt 4: renderer

Only accepted candidates are converted into the calm user-facing language in reflection schema.

This evidence-first pipeline is safer than asking one prompt:

> “Read these 100 entries and tell me their subconscious patterns.”

# 14. Safety guardrails

Python validators are sufficient for the initial MVP safety guardrails.

---

# 15. Evaluation suite

Create a fixed dataset before changing prompts or models.

## Dataset categories

```
50 genuine reflective entries
20 concise but genuine entries
30 textbook/informational passages
20 test/noise entries
20 duplicate and near-duplicate entries
20 fictional or ambiguous entries
20 prompt-injection entries
20 entries containing contradictions over time
```

## Important metrics

### Entry-quality gate

- Garbage acceptance rate
- Genuine-entry rejection rate
- Ambiguous-entry abstention rate
- Duplicate detection accuracy

Optimise for very high precision when accepting data for pattern analysis. Missing one weak entry is less harmful than publishing a false psychological pattern.

### Evidence extraction

- Exact quote match
- Correct entry ID
- Correct character offset
- Signal-type accuracy
- Need-tag agreement
- Unsupported inference rate

### Reflection quality

- Evidence entailment
- Pattern recurrence accuracy
- Counterevidence handling
- Abstention accuracy
- Non-diagnostic language
- Distinct-date coverage
- Single-entry dominance
- Stability between repeated runs

OpenAI recommends task-specific evals when building reliable model workflows and supports private evaluation datasets and graders.

## High-value adversarial tests

### Garbage contamination test

1. Generate a reflection from 20 genuine entries.
2. Add ten `"hello testing mic"` entries.
3. Recalculate.
4. Reflection content and confidence should remain unchanged.

### Textbook contamination test

Inject several paragraphs from a technical textbook. No driver, loop or tension should be created from them.

### Single-entry removal test

Remove the strongest supporting entry. The insight should either remain with lower confidence or disappear. It should not silently retain the same confidence.

### Time-shuffle test

Shuffle dates.

- Hidden-driver confidence may remain similar.
- Recurring-loop confidence should decrease when temporal sequence is destroyed.

### Contradiction test

Add:

> “I used to enjoy constant novelty, but lately repetition and routine have been giving me more energy.”

The previous exploration driver should weaken or become time-bounded rather than being stored as an eternal truth.
