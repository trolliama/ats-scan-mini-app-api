from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate(
    input_variables=["input"],
    template="""
    You are a helpful assistant. Answer the following question:

    {input}
    """,
)


def run_agent(query: str) -> str:
    # Deferred: return AgentResult stub per ATS design
    return "Hello, world from the agent!"
