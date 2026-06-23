from langchain_core.prompts import PromptTemplate

from core.enums import ATSCategoryKey
from core.models import AgentResult

prompt = PromptTemplate(
    input_variables=["input"],
    template="""
    You are a helpful assistant. Answer the following question:

    {input}
    """,
)


def run_agent(markdown: str) -> AgentResult:
    return AgentResult(
        overall_score=0,
        category_scores={key: 0 for key in ATSCategoryKey.all_keys()},
        missing_keywords=[],
        found_keywords=[],
        issues=[],
        job_title_detected=None,
    )
