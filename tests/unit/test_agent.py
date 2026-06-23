from core.enums import ATSCategoryKey
from core.models import AgentResult
from ai.agent import run_agent


def test_returns_agent_result_when_markdown_provided():
    """run_agent returns an AgentResult instance for any markdown input."""
    result = run_agent("# Jane Doe\n\nSoftware Engineer")

    assert isinstance(result, AgentResult)


def test_category_scores_contain_all_keys_at_zero_when_stub():
    """Stub AgentResult includes every category key scored at zero with empty lists."""
    result = run_agent("resume markdown")

    assert result.overall_score == 0
    assert set(result.category_scores.keys()) == set(ATSCategoryKey.all_keys())
    assert all(score == 0 for score in result.category_scores.values())
    assert result.missing_keywords == []
    assert result.found_keywords == []
    assert result.issues == []
    assert result.job_title_detected is None
