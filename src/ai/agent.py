import uuid

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from core import config
from core.enums import ATSCategoryKey, ATSIssueSeverity, CVContactType
from core.models import (
    AgentResult,
    ATSIssue,
    CVContactItem,
    CVEducationEntry,
    CVExperienceEntry,
    CVPreview,
)


class _ATSIssueFromLLM(BaseModel):
    category: str
    severity: ATSIssueSeverity
    description: str
    solution: str


class _CVContactItemFromLLM(BaseModel):
    type: CVContactType
    value: str


class _CVExperienceEntryFromLLM(BaseModel):
    company: str = ""
    role: str = ""
    location: str | None = None
    period: str = ""
    bullets: list[str] = Field(default_factory=list)


class _CVEducationEntryFromLLM(BaseModel):
    institution: str = ""
    degree: str = ""
    period: str = ""


class _CVPreviewFromLLM(BaseModel):
    name: str = ""
    headline: str | None = None
    contact: list[_CVContactItemFromLLM] = Field(default_factory=list)
    summary: str | None = None
    experience: list[_CVExperienceEntryFromLLM] = Field(default_factory=list)
    education: list[_CVEducationEntryFromLLM] = Field(default_factory=list)
    skills: list[str] | None = None


class _AgentResultFromLLM(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    category_scores: dict[ATSCategoryKey, int]
    missing_keywords: list[str]
    found_keywords: list[str]
    issues: list[_ATSIssueFromLLM]
    job_title_detected: str | None = None
    cv_preview: _CVPreviewFromLLM


def _category_keys_label() -> str:
    return ", ".join(key.value for key in ATSCategoryKey.all_keys())


def _contact_types_label() -> str:
    return ", ".join(contact_type.value for contact_type in CVContactType)


def _get_structured_llm():
    settings = config.get_settings()
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        api_key=settings.openai_api_key,
    )
    return llm.with_structured_output(_AgentResultFromLLM)


def _to_cv_preview(raw: _CVPreviewFromLLM) -> CVPreview:
    return CVPreview(
        name=raw.name,
        headline=raw.headline,
        contact=[
            CVContactItem(type=item.type, value=item.value)
            for item in raw.contact
        ],
        summary=raw.summary,
        experience=[
            CVExperienceEntry(
                company=entry.company,
                role=entry.role,
                location=entry.location,
                period=entry.period,
                bullets=entry.bullets,
            )
            for entry in raw.experience
        ],
        education=[
            CVEducationEntry(
                institution=entry.institution,
                degree=entry.degree,
                period=entry.period,
            )
            for entry in raw.education
        ],
        skills=raw.skills,
    )


def _to_agent_result(raw: _AgentResultFromLLM) -> AgentResult:
    return AgentResult(
        overall_score=raw.overall_score,
        category_scores=raw.category_scores,
        missing_keywords=raw.missing_keywords,
        found_keywords=raw.found_keywords,
        issues=[
            ATSIssue(
                id=str(uuid.uuid4()),
                category=issue.category,
                severity=issue.severity,
                description=issue.description,
                solution=issue.solution,
            )
            for issue in raw.issues
        ],
        job_title_detected=raw.job_title_detected,
        cv_preview=_to_cv_preview(raw.cv_preview),
    )


def run_agent(markdown: str) -> AgentResult:
    """Analyze resume markdown via LLM and return ATS scoring plus cv_preview."""
    settings = config.get_settings()
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required to run the ATS agent")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an ATS resume analyzer. Analyze the resume markdown and "
                "return structured scores and a cv_preview extracted from the "
                "document.\n\n"
                "Allowed category keys for category_scores and issue category: "
                "{category_keys}\n\n"
                "Each issue must include category, severity (critical, warning, or "
                "info), description, and solution.\n\n"
                "For cv_preview, extract candidate fields from the resume markdown "
                "regardless of layout. Allowed contact item types: "
                "{contact_types}. Use empty string or empty lists for fields not "
                "found in the resume — never invent data.",
            ),
            ("human", "{markdown}"),
        ]
    )
    messages = prompt.format_messages(
        markdown=markdown,
        category_keys=_category_keys_label(),
        contact_types=_contact_types_label(),
    )
    raw = _get_structured_llm().invoke(messages)
    return _to_agent_result(raw)
