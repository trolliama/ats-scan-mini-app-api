from langchain_core.prompts import PromptTemplate

from core.models import ALL_CATEGORY_KEYS, AgentResult

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
        category_scores={key: 0 for key in ALL_CATEGORY_KEYS},
        missing_keywords=[],
        found_keywords=[],
        issues=[],
        job_title_detected=None,
    )
