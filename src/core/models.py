from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from core.enums import (
    ATSCategoryKey,
    ATSIssueSeverity,
    CVContactType,
    ScanStatus,
)

__all__ = [
    "ATSCategoryKey",
    "ATSIssue",
    "ATSIssueSeverity",
    "ATSScanResult",
    "AgentResult",
    "CVContactItem",
    "CVContactType",
    "CVEducationEntry",
    "CVExperienceEntry",
    "CVPreview",
    "ScanCreate",
    "ScanRecord",
    "ScanStatus",
]


class ATSIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    category: str
    severity: ATSIssueSeverity
    description: str
    solution: str


class CVContactItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: CVContactType
    value: str


class CVExperienceEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    company: str
    role: str
    location: str | None = None
    period: str
    bullets: list[str]


class CVEducationEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    institution: str
    degree: str
    period: str


class CVPreview(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    headline: str | None = None
    contact: list[CVContactItem]
    summary: str | None = None
    experience: list[CVExperienceEntry]
    education: list[CVEducationEntry]
    skills: list[str] | None = None


class ATSScanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[ATSCategoryKey, int]
    missing_keywords: list[str]
    found_keywords: list[str]
    issues: list[ATSIssue]
    cv_preview: CVPreview


class AgentResult(BaseModel):
    """Full LLM analysis output including ATS scores and cv_preview."""

    model_config = ConfigDict(frozen=True)

    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[ATSCategoryKey, int]
    missing_keywords: list[str]
    found_keywords: list[str]
    issues: list[ATSIssue]
    job_title_detected: str | None = None
    cv_preview: CVPreview


class ScanCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    scan_id: UUID
    session_id: UUID
    file_key: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)


class ScanRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    session_id: str
    file_key: str
    bucket: str
    original_filename: str
    status: ScanStatus
    ats_score: int | None = Field(default=None, ge=0, le=100)
    job_title_detected: str | None
    failure_reason: str | None
    result: ATSScanResult | None
    webhook_processing_sent: bool
    webhook_terminal_sent: bool
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
