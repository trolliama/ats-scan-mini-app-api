import uuid
from unittest.mock import MagicMock, patch

import pytest

from ai.agent import (
    _AgentResultFromLLM,
    _ATSIssueFromLLM,
    _CVContactItemFromLLM,
    _CVPreviewFromLLM,
    run_agent,
)
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
from tests.settings import make_test_settings


def _sample_cv_preview() -> CVPreview:
    return CVPreview(
        name="Jane Doe",
        contact=[
            CVContactItem(type=CVContactType.EMAIL, value="jane.doe@example.com"),
            CVContactItem(type=CVContactType.PHONE, value="(555) 123-4567"),
        ],
        experience=[
            CVExperienceEntry(
                company="Acme Corp",
                role="Senior Software Engineer",
                location="San Francisco, CA",
                period="Jan 2020 – Present",
                bullets=["Led migration to microservices architecture"],
            )
        ],
        education=[
            CVEducationEntry(
                institution="Stanford University",
                degree="B.S. Computer Science",
                period="2012 – 2016",
            )
        ],
        skills=["Python", "Go", "AWS"],
    )


def _sample_cv_preview_from_llm() -> _CVPreviewFromLLM:
    return _CVPreviewFromLLM(
        name="Jane Doe",
        contact=[
            _CVContactItemFromLLM(
                type=CVContactType.EMAIL, value="jane.doe@example.com"
            ),
            _CVContactItemFromLLM(
                type=CVContactType.PHONE, value="(555) 123-4567"
            ),
        ],
        experience=[
            {
                "company": "Acme Corp",
                "role": "Senior Software Engineer",
                "location": "San Francisco, CA",
                "period": "Jan 2020 – Present",
                "bullets": ["Led migration to microservices architecture"],
            }
        ],
        education=[
            {
                "institution": "Stanford University",
                "degree": "B.S. Computer Science",
                "period": "2012 – 2016",
            }
        ],
        skills=["Python", "Go", "AWS"],
    )


def _sample_agent_result() -> AgentResult:
    return AgentResult(
        overall_score=85,
        category_scores={key: 80 for key in ATSCategoryKey.all_keys()},
        missing_keywords=["docker"],
        found_keywords=["python", "aws"],
        issues=[
            ATSIssue(
                id="00000000-0000-4000-8000-000000000001",
                category=ATSCategoryKey.KEYWORDS.value,
                severity=ATSIssueSeverity.WARNING,
                description="Missing docker keyword",
                solution="Add docker to skills section",
            )
        ],
        job_title_detected="Software Engineer",
        cv_preview=_sample_cv_preview(),
    )


def _sample_llm_response() -> _AgentResultFromLLM:
    return _AgentResultFromLLM(
        overall_score=85,
        category_scores={key: 80 for key in ATSCategoryKey.all_keys()},
        missing_keywords=["docker"],
        found_keywords=["python", "aws"],
        issues=[
            _ATSIssueFromLLM(
                category=ATSCategoryKey.KEYWORDS.value,
                severity=ATSIssueSeverity.WARNING,
                description="Missing docker keyword",
                solution="Add docker to skills section",
            )
        ],
        job_title_detected="Software Engineer",
        cv_preview=_sample_cv_preview_from_llm(),
    )


def _mock_chat_openai(llm_response: _AgentResultFromLLM) -> MagicMock:
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = llm_response
    mock_chat_cls = MagicMock()
    mock_chat_cls.return_value.with_structured_output.return_value = mock_structured
    return mock_chat_cls


def test_raises_when_openai_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_agent fails fast with a clear error when OPENAI_API_KEY is not configured."""
    settings = make_test_settings(openai_api_key=None)
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        run_agent("# Jane Doe\n\nSoftware Engineer")


def test_returns_valid_agent_result_when_llm_returns_structured_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent returns a typed AgentResult populated from the LLM structured response."""
    settings = make_test_settings(openai_api_key="sk-test")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    expected = _sample_agent_result()
    fixed_issue_id = uuid.UUID("00000000-0000-4000-8000-000000000001")

    with (
        patch("ai.agent.uuid.uuid4", return_value=fixed_issue_id),
        patch(
            "ai.agent.ChatOpenAI",
            _mock_chat_openai(_sample_llm_response()),
        ),
    ):
        result = run_agent("# Jane Doe\n\nSoftware Engineer")

    assert result == expected


def test_raises_when_llm_call_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM errors propagate so the scan pipeline can mark the scan failed."""
    settings = make_test_settings(openai_api_key="sk-test")
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    mock_structured = MagicMock()
    mock_structured.invoke.side_effect = RuntimeError("LLM timeout")
    mock_chat_cls = MagicMock()
    mock_chat_cls.return_value.with_structured_output.return_value = mock_structured

    with patch("ai.agent.ChatOpenAI", mock_chat_cls):
        with pytest.raises(RuntimeError, match="LLM timeout"):
            run_agent("resume markdown")


def test_maps_cv_preview_with_name_and_contact_from_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent maps cv_preview name and contact items from the LLM structured response."""
    settings = make_test_settings(openai_api_key="sk-test")
    monkeypatch.setattr(config, "get_settings", lambda: settings)

    with patch(
        "ai.agent.ChatOpenAI",
        _mock_chat_openai(_sample_llm_response()),
    ):
        result = run_agent("# Jane Doe\n\nSoftware Engineer")

    assert result.cv_preview.name == "Jane Doe"
    contact_by_type = {item.type: item.value for item in result.cv_preview.contact}
    assert contact_by_type[CVContactType.EMAIL] == "jane.doe@example.com"
    assert contact_by_type[CVContactType.PHONE] == "(555) 123-4567"
