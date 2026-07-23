from __future__ import annotations

from app.modules.reflections.schemas import (
    InsufficientInsight,
    ProcessingInsight,
    ReasonCode,
    UnavailableInsight,
)


MESSAGES: dict[ReasonCode, str] = {
    "NOT_ENOUGH_REFLECTIVE_CONTENT": (
        "There is not enough personal reflection to identify a meaningful pattern yet."
    ),
    "MINIMUM_BASIS_NOT_MET": (
        "Add more reflective entries before Orion draws this pattern."
    ),
    "DRIVER_NOT_REPEATED": (
        "A possible underlying driver has not repeated enough yet."
    ),
    "LOOP_NOT_REPEATED": "The same sequence has not repeated enough yet.",
    "BOTH_SIDES_NOT_SUPPORTED": (
        "There is not enough evidence for two competing needs yet."
    ),
    "INSUFFICIENT_EVIDENCE": (
        "There is not enough evidence in this range to show this pattern yet."
    ),
}


def insufficient(reason_code: ReasonCode) -> InsufficientInsight:
    return InsufficientInsight(reason_code=reason_code, message=MESSAGES[reason_code])


def processing() -> ProcessingInsight:
    return ProcessingInsight(message="Your reflection is being recalculated.")


def unavailable() -> UnavailableInsight:
    return UnavailableInsight(
        reason_code="TECHNICAL_FAILURE",
        message="This section is temporarily unavailable.",
        retryable=True,
    )
