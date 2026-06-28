from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai.agent import _AgentResultFromLLM, _CVPreviewFromLLM
from core.enums import ATSCategoryKey
from infra.db.engine import init_db


def _stub_llm_response() -> _AgentResultFromLLM:
    return _AgentResultFromLLM(
        overall_score=0,
        category_scores={key: 0 for key in ATSCategoryKey.all_keys()},
        missing_keywords=[],
        found_keywords=[],
        issues=[],
        job_title_detected=None,
        cv_preview=_CVPreviewFromLLM(),
    )


def _mock_chat_openai(llm_response: _AgentResultFromLLM) -> MagicMock:
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = llm_response
    mock_chat_cls = MagicMock()
    mock_chat_cls.return_value.with_structured_output.return_value = mock_structured
    return mock_chat_cls


@pytest.fixture(autouse=True)
def mock_llm_at_boundary() -> Generator[None, None, None]:
    """Fake OpenAI at the transport boundary so pipeline integration tests stay offline."""
    with patch(
        "ai.agent.ChatOpenAI",
        _mock_chat_openai(_stub_llm_response()),
    ):
        yield


@pytest.fixture
def db_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()
