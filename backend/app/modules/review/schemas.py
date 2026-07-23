from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

from app.modules.review.types import (
    ENTRY_INSIGHT_CATEGORY_BY_TYPE,
    PATTERN_CATEGORY_BY_TYPE,
    EntryInsightCategory,
    EntryInsightType,
    EntryInsightVerdict,
    EvidenceWeight,
    FeedbackDecision,
    PatternCategory,
    PatternType,
    PatternVerdict,
    ReviewCategoryFilter,
    ReviewScope,
    ReviewStatus,
    ReviewVerdict,
    category_allowed_for_scope,
    feedback_decision,
)


REVIEW_PAGE_SIZE_DEFAULT = 20
REVIEW_PAGE_SIZE_MAX = 100
REVIEW_STATEMENT_MAX_LENGTH = 1000
REVIEW_SOURCE_QUOTE_MAX_LENGTH = 4000
REVIEW_CORRECTION_MAX_LENGTH = 1000
REVIEW_NOTE_MAX_LENGTH = 1000


class StrictReviewModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class StrictReviewQueryModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ReviewListQuery(StrictReviewQueryModel):
    scope: ReviewScope
    category: ReviewCategoryFilter = "all"
    status: ReviewStatus = "pending"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=REVIEW_PAGE_SIZE_DEFAULT,
        ge=1,
        le=REVIEW_PAGE_SIZE_MAX,
    )

    @model_validator(mode="after")
    def validate_category_scope(self) -> Self:
        if not category_allowed_for_scope(
            scope=self.scope,
            category=self.category,
        ):
            raise ValueError("category is not valid for the selected scope")
        return self


class ReviewFeedbackRequest(StrictReviewModel):
    verdict: ReviewVerdict
    corrected_statement: str | None = Field(
        default=None,
        min_length=1,
        max_length=REVIEW_CORRECTION_MAX_LENGTH,
    )
    note: str | None = Field(
        default=None,
        min_length=1,
        max_length=REVIEW_NOTE_MAX_LENGTH,
    )

    @field_validator("corrected_statement", "note", mode="before")
    @classmethod
    def normalize_blank_optional_text(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def decision_for_scope(self, scope: ReviewScope) -> FeedbackDecision:
        return feedback_decision(scope=scope, verdict=self.verdict)


class ReviewFeedbackBase(StrictReviewModel):
    corrected_statement: str | None = Field(
        default=None,
        min_length=1,
        max_length=REVIEW_CORRECTION_MAX_LENGTH,
    )
    note: str | None = Field(
        default=None,
        min_length=1,
        max_length=REVIEW_NOTE_MAX_LENGTH,
    )
    evidence_weight: EvidenceWeight = Field(ge=0, le=1, allow_inf_nan=False)
    updated_at: datetime


class EntryInsightFeedback(ReviewFeedbackBase):
    verdict: EntryInsightVerdict

    @model_validator(mode="after")
    def validate_weight(self) -> Self:
        expected = feedback_decision(
            scope="entry_insight",
            verdict=self.verdict,
        )
        if self.evidence_weight != expected.evidence_weight:
            raise ValueError("evidence weight does not match the verdict")
        return self


class PatternFeedback(ReviewFeedbackBase):
    verdict: PatternVerdict

    @model_validator(mode="after")
    def validate_weight(self) -> Self:
        expected = feedback_decision(scope="pattern", verdict=self.verdict)
        if self.evidence_weight != expected.evidence_weight:
            raise ValueError("evidence weight does not match the verdict")
        return self


class ReviewItemBase(StrictReviewModel):
    id: UUID
    statement: str = Field(min_length=1, max_length=REVIEW_STATEMENT_MAX_LENGTH)
    source_entry_ids: list[UUID] = Field(min_length=1, max_length=100)
    source_dates: list[date] = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    status: ReviewStatus

    @model_validator(mode="after")
    def validate_sources(self) -> Self:
        if len(self.source_entry_ids) != len(set(self.source_entry_ids)):
            raise ValueError("source entry IDs must be distinct")
        if len(self.source_dates) != len(set(self.source_dates)):
            raise ValueError("source dates must be distinct")
        return self


class EntryInsightReviewItem(ReviewItemBase):
    scope: Literal["entry_insight"]
    item_type: EntryInsightType = Field(alias="type")
    category: EntryInsightCategory
    source_quote: str | None = Field(
        default=None,
        min_length=1,
        max_length=REVIEW_SOURCE_QUOTE_MAX_LENGTH,
    )
    source_entry_ids: list[UUID] = Field(min_length=1, max_length=1)
    source_dates: list[date] = Field(min_length=1, max_length=1)
    inference_level: Literal["direct", "inferred"]
    feedback: EntryInsightFeedback | None

    @model_validator(mode="after")
    def validate_category_and_feedback(self) -> Self:
        if self.category != ENTRY_INSIGHT_CATEGORY_BY_TYPE[self.item_type]:
            raise ValueError("category does not match the entry insight type")
        self._validate_feedback_status()
        return self

    def _validate_feedback_status(self) -> None:
        if self.feedback is None:
            if self.status != "pending":
                raise ValueError("a non-pending item must include feedback")
            return
        expected = feedback_decision(
            scope="entry_insight",
            verdict=self.feedback.verdict,
        )
        if self.status != expected.status:
            raise ValueError("review status does not match feedback")


class PatternReviewItem(ReviewItemBase):
    scope: Literal["pattern"]
    item_type: PatternType = Field(alias="type")
    category: PatternCategory
    source_quote: None = None
    inference_level: Literal["synthesized"]
    feedback: PatternFeedback | None

    @model_validator(mode="after")
    def validate_category_and_feedback(self) -> Self:
        if self.category != PATTERN_CATEGORY_BY_TYPE[self.item_type]:
            raise ValueError("category does not match the pattern type")
        if self.feedback is None:
            if self.status != "pending":
                raise ValueError("a non-pending item must include feedback")
            return self
        expected = feedback_decision(
            scope="pattern",
            verdict=self.feedback.verdict,
        )
        if self.status != expected.status:
            raise ValueError("review status does not match feedback")
        return self


ReviewItem = Annotated[
    EntryInsightReviewItem | PatternReviewItem,
    Field(discriminator="scope"),
]


class ReviewPagination(StrictReviewModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=REVIEW_PAGE_SIZE_MAX)
    total: int = Field(ge=0)


class ReviewItemsResponse(StrictReviewModel):
    items: list[ReviewItem] = Field(max_length=REVIEW_PAGE_SIZE_MAX)
    pagination: ReviewPagination
