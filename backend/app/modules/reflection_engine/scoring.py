from __future__ import annotations

from collections.abc import Collection, Iterable
from statistics import fmean

from app.modules.reflection_engine.schemas import (
    ConfidenceLabel,
    HiddenDriverScoreComponents,
    LoopScoreComponents,
    TensionScoreComponents,
)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def progress(value: int | float, minimum: float, strong: float) -> float:
    if value <= 0:
        return 0.0
    if value < minimum:
        return 0.60 * value / minimum
    if strong == minimum:
        return 1.0
    return clamp01(0.60 + 0.40 * (value - minimum) / (strong - minimum))


def temporal_spread(distinct_dates: int, span_days: int) -> float:
    return clamp01(
        0.60 * progress(distinct_dates, 2, 6)
        + 0.40 * progress(span_days, 7, 45)
    )


def context_diversity(theme_keys: Collection[str]) -> float:
    nonempty = {key for key in theme_keys if key}
    return progress(len(nonempty), 2, 4) if nonempty else 0.0


def evidence_strength(confidences: Iterable[float]) -> float:
    values = tuple(confidences)
    return clamp01(fmean(values)) if values else 0.0


def contradiction(
    support_confidences: Iterable[float], counter_confidences: Iterable[float]
) -> float:
    support_sum = sum(support_confidences)
    counter_sum = sum(counter_confidences)
    return clamp01(counter_sum / max(support_sum + counter_sum, 1e-9))


def duplication(unique_duplicate_clusters: int, raw_support_signal_count: int) -> float:
    return clamp01(
        1
        - unique_duplicate_clusters
        / max(raw_support_signal_count, 1)
    )


def candidate_stability(
    *,
    previous_support_clusters: Collection[str] | None,
    current_support_clusters: Collection[str],
    previous_score: float | None,
    deterministic_score_before_stability: float,
) -> float:
    if previous_support_clusters is None or previous_score is None:
        return 0.50
    previous = set(previous_support_clusters)
    current = set(current_support_clusters)
    union = previous | current
    jaccard = len(previous & current) / len(union) if union else 1.0
    score_consistency = 1 - abs(previous_score - deterministic_score_before_stability)
    return clamp01(0.50 * jaccard + 0.50 * score_consistency)


def score_hidden_driver(
    *,
    supporting_entries: int,
    distinct_dates: int,
    span_days: int,
    theme_keys: Collection[str],
    support_confidences: Collection[float],
    counter_confidences: Collection[float],
    distinct_signal_types: int,
    unique_duplicate_clusters: int,
    raw_support_signal_count: int,
    current_support_clusters: Collection[str],
    previous_support_clusters: Collection[str] | None = None,
    previous_score: float | None = None,
) -> tuple[float, HiddenDriverScoreComponents]:
    recurrence = progress(supporting_entries, 3, 10)
    spread = temporal_spread(distinct_dates, span_days)
    contexts = context_diversity(theme_keys)
    strength = evidence_strength(support_confidences)
    type_diversity = progress(distinct_signal_types, 2, 5)
    opposition = contradiction(support_confidences, counter_confidences)
    duplicate_penalty = duplication(
        unique_duplicate_clusters, raw_support_signal_count
    )
    before_stability = clamp01(
        0.30 * recurrence
        + 0.20 * spread
        + 0.15 * contexts
        + 0.15 * strength
        + 0.10 * type_diversity
        - 0.20 * opposition
        - 0.15 * duplicate_penalty
    )
    stability = candidate_stability(
        previous_support_clusters=previous_support_clusters,
        current_support_clusters=current_support_clusters,
        previous_score=previous_score,
        deterministic_score_before_stability=before_stability,
    )
    score = clamp01(before_stability + 0.10 * stability)
    components = HiddenDriverScoreComponents(
        recurrence=recurrence,
        temporal_spread=spread,
        context_diversity=contexts,
        evidence_strength=strength,
        signal_type_diversity=type_diversity,
        stability=stability,
        contradiction=opposition,
        duplication=duplicate_penalty,
        deterministic_score_before_stability=before_stability,
    )
    return score, components


def score_recurring_loop(
    *,
    observed_chains: int,
    supported_transitions: int,
    distinct_dates: int,
    span_days: int,
    theme_keys: Collection[str],
    support_confidences: Collection[float],
    counter_confidences: Collection[float],
    unique_duplicate_clusters: int,
    raw_support_signal_count: int,
    current_support_clusters: Collection[str],
    previous_support_clusters: Collection[str] | None = None,
    previous_score: float | None = None,
) -> tuple[float, LoopScoreComponents]:
    recurrence = progress(observed_chains, 3, 8)
    coverage = progress(supported_transitions, 4, 8)
    spread = temporal_spread(distinct_dates, span_days)
    contexts = context_diversity(theme_keys)
    strength = evidence_strength(support_confidences)
    opposition = contradiction(support_confidences, counter_confidences)
    duplicate_penalty = duplication(
        unique_duplicate_clusters, raw_support_signal_count
    )
    before_stability = clamp01(
        0.25 * recurrence
        + 0.20 * coverage
        + 0.15 * spread
        + 0.10 * contexts
        + 0.15 * strength
        - 0.20 * opposition
        - 0.15 * duplicate_penalty
    )
    stability = candidate_stability(
        previous_support_clusters=previous_support_clusters,
        current_support_clusters=current_support_clusters,
        previous_score=previous_score,
        deterministic_score_before_stability=before_stability,
    )
    score = clamp01(before_stability + 0.15 * stability)
    components = LoopScoreComponents(
        recurrence=recurrence,
        transition_coverage=coverage,
        temporal_spread=spread,
        context_diversity=contexts,
        evidence_strength=strength,
        stability=stability,
        contradiction=opposition,
        duplication=duplicate_penalty,
        deterministic_score_before_stability=before_stability,
    )
    return score, components


def score_inner_tension(
    *,
    left_supporting_entries: int,
    right_supporting_entries: int,
    left_mean_confidence: float,
    right_mean_confidence: float,
    direct_conflict_entry_count: int,
    need_side_switches: int,
    theme_keys: Collection[str],
    support_confidences: Collection[float],
    counter_confidences: Collection[float],
    unique_duplicate_clusters: int,
    raw_support_signal_count: int,
    current_support_clusters: Collection[str],
    previous_support_clusters: Collection[str] | None = None,
    previous_score: float | None = None,
) -> tuple[float, TensionScoreComponents]:
    left_support = clamp01(
        0.70 * progress(left_supporting_entries, 2, 6)
        + 0.30 * clamp01(left_mean_confidence)
    )
    right_support = clamp01(
        0.70 * progress(right_supporting_entries, 2, 6)
        + 0.30 * clamp01(right_mean_confidence)
    )
    direct_conflict = progress(direct_conflict_entry_count, 1, 4)
    alternation = progress(need_side_switches, 1, 4)
    contexts = context_diversity(theme_keys)
    strength = evidence_strength(support_confidences)
    opposition = contradiction(support_confidences, counter_confidences)
    duplicate_penalty = duplication(
        unique_duplicate_clusters, raw_support_signal_count
    )
    before_stability = clamp01(
        0.20 * left_support
        + 0.20 * right_support
        + 0.15 * direct_conflict
        + 0.10 * alternation
        + 0.10 * contexts
        + 0.10 * strength
        - 0.15 * opposition
        - 0.10 * duplicate_penalty
    )
    stability = candidate_stability(
        previous_support_clusters=previous_support_clusters,
        current_support_clusters=current_support_clusters,
        previous_score=previous_score,
        deterministic_score_before_stability=before_stability,
    )
    score = clamp01(before_stability + 0.15 * stability)
    components = TensionScoreComponents(
        left_support=left_support,
        right_support=right_support,
        direct_conflict=direct_conflict,
        temporal_alternation=alternation,
        context_diversity=contexts,
        evidence_strength=strength,
        stability=stability,
        contradiction=opposition,
        duplication=duplicate_penalty,
        deterministic_score_before_stability=before_stability,
    )
    return score, components


def overall_basis_eligible(
    *, valid_entry_count: int, distinct_entry_dates: int, reflective_word_count: int
) -> bool:
    return (
        valid_entry_count >= 3
        and distinct_entry_dates >= 2
        and reflective_word_count >= 150
    )


def hidden_driver_publishable(
    *, supporting_entries: int, distinct_dates: int, distinct_signal_types: int, score: float
) -> bool:
    return (
        supporting_entries >= 3
        and distinct_dates >= 2
        and distinct_signal_types >= 2
        and score >= 0.68
    )


def recurring_loop_publishable(
    *,
    observed_chains: int,
    supporting_entries: int,
    supported_transitions: int,
    distinct_dates: int,
    score: float,
) -> bool:
    return (
        observed_chains >= 2
        and supporting_entries >= 3
        and supported_transitions >= 3
        and distinct_dates >= 2
        and score >= 0.72
    )


def inner_tension_publishable(
    *,
    left_supporting_entries: int,
    right_supporting_entries: int,
    distinct_dates: int,
    score: float,
) -> bool:
    return (
        left_supporting_entries >= 2
        and right_supporting_entries >= 2
        and distinct_dates >= 2
        and score >= 0.70
    )


def confidence_label(supporting_entries: int) -> ConfidenceLabel:
    if supporting_entries >= 10:
        return "recurring"
    if supporting_entries >= 5:
        return "emerging"
    return "preliminary"
