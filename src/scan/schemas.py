from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ATSCategoryKey = Literal[
    "keywords",
    "formatting",
    "content",
    "professional_experience",
    "header_contact",
    "professional_summary",
    "skills",
    "education",
]

ALL_CATEGORY_KEYS: tuple[ATSCategoryKey, ...] = (
    "keywords",
    "formatting",
    "content",
    "professional_experience",
    "header_contact",
    "professional_summary",
    "skills",
    "education",
)

ATSIssueSeverity = Literal["critical", "warning", "info"]
CVContactType = Literal[
    "email", "phone", "location", "linkedin", "github", "website", "custom"
]


class CreateScanRequest(BaseModel):
    scan_id: UUID
    session_id: UUID
    file_key: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)
    bucket: str = Field(min_length=1)


class CreateScanResponse(BaseModel):
    scan_id: UUID
    status: Literal["pending"]


class ATSIssue(BaseModel):
    id: str
    category: str
    severity: ATSIssueSeverity
    description: str
    solution: str


class CVContactItem(BaseModel):
    type: CVContactType
    value: str


class CVExperienceEntry(BaseModel):
    company: str
    role: str
    location: str | None = None
    period: str
    bullets: list[str]


class CVEducationEntry(BaseModel):
    institution: str
    degree: str
    period: str


class CVPreview(BaseModel):
    name: str
    headline: str | None = None
    contact: list[CVContactItem]
    summary: str | None = None
    experience: list[CVExperienceEntry]
    education: list[CVEducationEntry]
    skills: list[str] | None = None


class ATSScanResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[ATSCategoryKey, int]
    missing_keywords: list[str]
    found_keywords: list[str]
    issues: list[ATSIssue]
    cv_preview: CVPreview

  


class AgentResult(BaseModel):
    """LLM output only — no cv_preview."""

    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[ATSCategoryKey, int]
    missing_keywords: list[str]
    found_keywords: list[str]
    issues: list[ATSIssue]
    job_title_detected: str | None = None


class WebhookProcessingPayload(BaseModel):
    scanId: str
    status: Literal["processing"]


class WebhookCompletedPayload(BaseModel):
    scanId: str
    status: Literal["completed"]
    atsScore: int
    jobTitleDetected: str | None
    result: ATSScanResult


class WebhookFailedPayload(BaseModel):
    scanId: str
    status: Literal["failed"]
    failureReason: str
