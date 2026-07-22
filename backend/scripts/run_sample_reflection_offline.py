from __future__ import annotations

import argparse
import hashlib
import json
import sys
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, UUID, uuid5


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.jobs.types import JobClaim
from app.modules.processing.quality import QualityHistory, compute_quality_features
from app.modules.reflection_engine.schemas import ReflectionCriticOutput
from app.modules.reflection_engine.service import ReflectionEngineService
from app.shared.security.encryption import AesGcmContentCipher
from scripts.run_sample_reflection_e2e import load_sample_entries


USER_ID = UUID("a1111111-1111-4111-8111-111111111111")
LOOP_ROLES = (
    "trigger",
    "interpretation",
    "emotional_response",
    "avoidance",
    "short_term_protection",
    "long_term_cost",
    "trigger",
)
LOOP_ENTRY_INDEXES = frozenset({0, 4, 8, 12, 16, 20, 24, 28})
LOOP_THEMES = ("career", "health", "family_friends", "personal_growth")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the 30-entry Reflection Engine with local fixtures only."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def _cipher() -> AesGcmContentCipher:
    return AesGcmContentCipher(
        encryption_keys={"offline-entry-key": b"e" * 32},
        active_encryption_key_id="offline-entry-key",
        fingerprint_keys={"offline-fingerprint-key": b"f" * 32},
        active_fingerprint_key_id="offline-fingerprint-key",
    )


def _stable_uuid(label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"orion-offline-reflection:{label}")


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _word_spans(content: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    for index, character in enumerate(content):
        if character.isalpha() and start is None:
            start = index
        elif not character.isalpha() and start is not None:
            spans.append((start, index))
            start = None
    if start is not None:
        spans.append((start, len(content)))
    return spans


def _signal(
    *,
    entry_index: int,
    signal_index: int,
    entry_date: date,
    entry_id: UUID,
    analysis_id: UUID,
    content: str,
    entry_envelope: dict[str, str],
    signal_type: str,
    normalized_label: str,
    interpretation: str,
    themes: list[str],
    need_tags: list[str],
    loop_role: str | None,
    cipher: AesGcmContentCipher,
) -> dict[str, object]:
    spans = _word_spans(content)
    if signal_index >= len(spans):
        raise ValueError("fixture entry has too few words")
    start, end = spans[signal_index]
    signal_id = _stable_uuid(f"signal:{entry_index}:{signal_index}")
    quote = content[start:end]
    return {
        "id": str(signal_id),
        "user_id": str(USER_ID),
        "entry_id": str(entry_id),
        "entry_user_id": str(USER_ID),
        "analysis_id": str(analysis_id),
        "analysis_user_id": str(USER_ID),
        "analysis_entry_id": str(entry_id),
        "analysis_source_version": entry_index + 1,
        "analysis_eligibility": "accepted",
        "entry_date": entry_date.isoformat(),
        "signal_type": signal_type,
        "normalized_label_fingerprint": _fingerprint(normalized_label),
        "payload_envelope": cipher.encrypt_json(
            {
                "normalized_label": normalized_label,
                "interpretation": interpretation,
                "source_quote": quote,
            },
            user_id=USER_ID,
            record_id=signal_id,
            purpose="entry_signal_payload",
        ),
        "entry_content_envelope": entry_envelope,
        "themes": themes,
        "need_tags": need_tags,
        "loop_role": loop_role,
        "confidence": 0.92,
        "source_start": start,
        "source_end": end,
        "occurred_on": entry_date.isoformat(),
        "duplicate_cluster_key": _fingerprint(f"entry:{entry_index}"),
    }


def _entry_signals(
    *,
    entry_index: int,
    entry_date: date,
    content: str,
    cipher: AesGcmContentCipher,
) -> tuple[UUID, list[dict[str, object]]]:
    entry_id = _stable_uuid(f"entry:{entry_date.isoformat()}")
    analysis_id = _stable_uuid(f"analysis:{entry_date.isoformat()}")
    entry_envelope = cipher.encrypt(content, user_id=USER_ID, record_id=entry_id)
    primary_types = ("self_statement", "desire", "action")
    signals = [
        _signal(
            entry_index=entry_index,
            signal_index=8,
            entry_date=entry_date,
            entry_id=entry_id,
            analysis_id=analysis_id,
            content=content,
            entry_envelope=entry_envelope,
            signal_type=primary_types[entry_index % len(primary_types)],
            normalized_label="capability through responsible work",
            interpretation="The fixture marks a recurring competence-related signal.",
            themes=["career", "personal_growth"],
            need_tags=["competence"],
            loop_role=None,
            cipher=cipher,
        )
    ]
    if entry_index in LOOP_ENTRY_INDEXES:
        for offset, role in enumerate(LOOP_ROLES):
            signals.append(
                _signal(
                    entry_index=entry_index,
                    signal_index=offset,
                    entry_date=entry_date,
                    entry_id=entry_id,
                    analysis_id=analysis_id,
                    content=content,
                    entry_envelope=entry_envelope,
                    signal_type="avoidance" if role == "avoidance" else "event",
                    normalized_label=f"fixture loop {role}",
                    interpretation=f"The fixture marks the {role.replace('_', ' ')} step.",
                    themes=[LOOP_THEMES[(entry_index // 4) % len(LOOP_THEMES)]],
                    need_tags=["control"],
                    loop_role=role,
                    cipher=cipher,
                )
            )
    if 8 <= entry_index < 18:
        signals.append(
            _signal(
                entry_index=entry_index,
                signal_index=9,
                entry_date=entry_date,
                entry_id=entry_id,
                analysis_id=analysis_id,
                content=content,
                entry_envelope=entry_envelope,
                signal_type="conflict",
                normalized_label="independence alongside connection",
                interpretation="The fixture marks evidence for autonomy and belonging.",
                themes=["career", "family_friends"],
                need_tags=["autonomy", "belonging"],
                loop_role=None,
                cipher=cipher,
            )
        )
    return entry_id, signals


class OfflineReflectionProvider:
    kind = "deterministic_fixture"

    def __init__(self) -> None:
        self.synthesis_calls = 0
        self.critic_calls = 0

    def synthesize(self, *, payload: str, safety_identifier: str) -> dict[str, object]:
        if len(safety_identifier) != 64:
            raise ValueError("fixture safety identifier is invalid")
        self.synthesis_calls += 1
        decoded = json.loads(payload.split("\n", 1)[1])
        candidates = decoded["candidates"]
        chosen: dict[str, dict[str, object]] = {}
        for candidate in candidates:
            chosen.setdefault(candidate["pattern_type"], candidate)

        hidden: list[dict[str, object]] = []
        loops: list[dict[str, object]] = []
        tensions: list[dict[str, object]] = []
        selected_ids: set[str] = set()

        if candidate := chosen.get("hidden_driver"):
            selected_ids.add(candidate["candidate_id"])
            structure = candidate["deterministic_structure"]
            hidden.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "canonical_need": structure["canonical_need"],
                    "statement": "A possible pattern across your entries may involve competence.",
                    "underlying_need": structure["canonical_need"].replace("_", " "),
                    "evidence": [
                        {
                            "signal_id": item["signal_id"],
                            "evidence_role": item["evidence_role"],
                        }
                        for item in candidate["evidence"]
                    ],
                }
            )

        if candidate := chosen.get("recurring_loop"):
            selected_ids.add(candidate["candidate_id"])
            structure = candidate["deterministic_structure"]
            loops.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "canonical_key": candidate["canonical_key"],
                    "title": "A possible recurring work loop",
                    "description": "A possible loop may connect a trigger, interpretation, avoidance, and later cost.",
                    "steps": [
                        {
                            "loop_role": step["loop_role"],
                            "statement": f"The fixture represents the {step['loop_role'].replace('_', ' ')} step.",
                            "evidence": [
                                {
                                    "signal_id": signal_id,
                                    "evidence_role": "supporting",
                                }
                                for signal_id in step["support_signal_ids"]
                            ],
                        }
                        for step in structure["steps"]
                    ],
                    "protection": "The loop may offer short-term protection from uncertainty.",
                    "interruption": "A small pause may create room for a different response.",
                    "counterevidence": [
                        {
                            "signal_id": item["signal_id"],
                            "evidence_role": "counter",
                        }
                        for item in candidate["evidence"]
                        if item["evidence_role"] == "counter"
                    ],
                }
            )

        if candidate := chosen.get("inner_tension"):
            selected_ids.add(candidate["candidate_id"])
            structure = candidate["deterministic_structure"]
            left = structure["left_need"].replace("_", " ")
            right = structure["right_need"].replace("_", " ")
            tensions.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "left_need": structure["left_need"],
                    "right_need": structure["right_need"],
                    "left_statement": f"Some entries support the need for {left}.",
                    "right_statement": f"Some entries support the need for {right}.",
                    "integration": f"You may be trying to hold both {left} and {right}; a workable arrangement could make room for each.",
                    "evidence": [
                        {
                            "signal_id": item["signal_id"],
                            "evidence_role": item["evidence_role"],
                        }
                        for item in candidate["evidence"]
                    ],
                }
            )

        abstentions = [
            {
                "candidate_id": item["candidate_id"],
                "pattern_type": item["pattern_type"],
                "reason_code": "INSUFFICIENT_EVIDENCE",
            }
            for item in candidates
            if item["candidate_id"] not in selected_ids
        ]
        return {
            "hidden_drivers": hidden,
            "recurring_loops": loops,
            "inner_tensions": tensions,
            "abstentions": abstentions,
        }

    def critique(self, *, payload: str, safety_identifier: str) -> ReflectionCriticOutput:
        del payload
        if len(safety_identifier) != 64:
            raise ValueError("fixture safety identifier is invalid")
        self.critic_calls += 1
        return ReflectionCriticOutput(
            entailed=True,
            overreaches=False,
            contradictory_evidence_ignored=False,
            diagnostic_language=False,
            evidence_diversity_adequate=True,
            recommended_action="publish",
        )


class OfflineRepository:
    def __init__(self, raw: dict[str, object]) -> None:
        self.raw = raw
        self.applied: dict[str, object] | None = None

    def load_synthesis_basis(self, _session: object, **_kwargs: object) -> dict[str, object]:
        return self.raw

    def apply_snapshot(self, _session: object, **kwargs: object) -> UUID:
        self.applied = kwargs
        return UUID(str(kwargs["snapshot"]["id"]))  # type: ignore[index]


class OfflineUnitOfWork:
    @contextmanager
    def for_worker(self):
        yield SimpleNamespace(session=object())


def run_offline(input_path: Path) -> dict[str, object]:
    entries, dataset_hash = load_sample_entries(input_path)
    if len(entries) != 30:
        raise ValueError("offline fixture requires exactly 30 entries")
    cipher = _cipher()
    history: list[QualityHistory] = []
    raw_signals: list[dict[str, object]] = []
    entry_breakdown: list[dict[str, object]] = []
    reflective_words = 0

    for index, entry in enumerate(entries):
        quality = compute_quality_features(
            entry.content,
            user_id=USER_ID,
            cipher=cipher,
            history=tuple(history),
        )
        entry_id, signals = _entry_signals(
            entry_index=index,
            entry_date=entry.entry_date,
            content=entry.content,
            cipher=cipher,
        )
        raw_signals.extend(signals)
        reflective_words += quality.features.word_count
        history.append(
            QualityHistory(
                duplicate_cluster_key=quality.duplicate_cluster_key,
                ngram_sketch=quality.ngram_sketch,
                eligibility="accepted",
            )
        )
        entry_breakdown.append(
            {
                "ordinal": index + 1,
                "entryDate": entry.entry_date.isoformat(),
                "entryId": str(entry_id),
                "wordCount": quality.features.word_count,
                "meaningfulTokenCount": quality.features.meaningful_token_count,
                "hardExclusionCodes": list(quality.features.hard_exclusion_codes),
                "duplicateDetected": bool(
                    quality.features.exact_duplicate
                    or quality.features.near_duplicate_similarity is not None
                    and quality.features.near_duplicate_similarity >= 0.90
                ),
                "analysisProvider": OfflineReflectionProvider.kind,
                "analysisEligibility": "accepted",
                "signalCount": len(signals),
                "signalTypes": sorted({str(item["signal_type"]) for item in signals}),
                "modelCalls": 0,
            }
        )

    raw: dict[str, object] = {
        "source_version": 30,
        "basis_start": (entries[-1].entry_date - timedelta(days=89)).isoformat(),
        "basis_end": entries[-1].entry_date.isoformat(),
        "valid_entry_count": 30,
        "excluded_entry_count": 0,
        "distinct_entry_dates": 30,
        "reflective_word_count": reflective_words,
        "signals": raw_signals,
        "candidates": [],
        "next_snapshot_version": 1,
        "feedback_qualifications": {},
    }
    repository = OfflineRepository(raw)
    provider = OfflineReflectionProvider()
    service = ReflectionEngineService(
        repository=repository,  # type: ignore[arg-type]
        provider=provider,  # type: ignore[arg-type]
        cipher=cipher,
    )
    claim = JobClaim(
        job_id=_stable_uuid("synthesis-job"),
        user_id=USER_ID,
        entry_id=None,
        job_type="reflection_synthesis",
        execution_mode="publish",
        source_version="30",
        claim_token=_stable_uuid("claim-token"),
        attempts=1,
    )
    service.run_synthesis_job(
        claim=claim,
        worker_id="offline-fixture-worker",
        uow=OfflineUnitOfWork(),  # type: ignore[arg-type]
    )
    if repository.applied is None:
        raise RuntimeError("offline snapshot was not materialized")

    candidates = repository.applied["candidates"]
    insights = repository.applied["insights"]
    snapshot_evidence = repository.applied["snapshot_evidence"]
    candidate_summary = [
        {
            "candidateId": item["id"],
            "patternType": item["pattern_type"],
            "status": item["status"],
            "score": item["score"],
            "publicationGatePassed": item["publication_gate_passed"],
        }
        for item in candidates
    ]
    insight_summary = [
        {
            "insightId": item["id"],
            "patternType": item["pattern_type"],
            "status": item["status"],
            "reasonCode": item.get("reason_code"),
            "score": item.get("score"),
        }
        for item in insights
    ]
    return {
        "schemaVersion": 1,
        "status": "passed",
        "proofMode": "offline_fixture",
        "dataset": {
            "path": input_path.name,
            "sha256": dataset_hash,
            "entryCount": len(entries),
        },
        "providerBoundary": {
            "entryAnalysis": OfflineReflectionProvider.kind,
            "synthesis": OfflineReflectionProvider.kind,
            "critic": OfflineReflectionProvider.kind,
            "externalModelCalls": 0,
            "externalDatabaseWrites": 0,
            "synthesisCalls": provider.synthesis_calls,
            "criticCalls": provider.critic_calls,
        },
        "entryBreakdown": entry_breakdown,
        "pipeline": {
            "acceptedEntries": 30,
            "excludedEntries": 0,
            "reflectiveWordCount": reflective_words,
            "signalCount": len(raw_signals),
            "candidateCount": len(candidates),
            "publishableCandidateCount": sum(
                bool(item["publication_gate_passed"]) for item in candidates
            ),
            "publishedCandidateCount": sum(
                item["status"] == "published" for item in candidates
            ),
            "snapshotEvidenceCount": len(snapshot_evidence),
        },
        "candidates": candidate_summary,
        "snapshot": repository.applied["snapshot"],
        "insights": insight_summary,
        "limitations": [
            "No OpenAI request was made; model quality, latency, token use, and cost are unproven.",
            "No Supabase write was made; migrations, RLS, queue claiming, and deployed networking are unproven.",
            "Fixture signals and proposal wording are deterministic test data, not semantic findings about the journal text.",
        ],
    }


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = run_offline(args.input)
    atomic_write_json(args.output, result)
    print(
        json.dumps(
            {
                "status": result["status"],
                "proofMode": result["proofMode"],
                "entries": result["dataset"]["entryCount"],  # type: ignore[index]
                "output": str(args.output),
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
