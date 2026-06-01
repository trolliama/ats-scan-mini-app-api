# Tech Stack

**Analyzed:** 2026-05-31

## Core

- **Language:** Python >=3.14.5,<4.0.0 (`.python-version`: 3.14.5)
- **Framework:** FastAPI 0.136.1
- **ASGI server:** Uvicorn 0.47.0
- **Package manager:** Poetry (`pyproject.toml`, `poetry.lock`); `uv.lock` also present
- **Validation/settings:** Pydantic 2.13.4, pydantic-settings 2.x

## Backend

- **API style:** REST (FastAPI async routes)
- **Background work:** FastAPI `BackgroundTasks` (in-process, no queue)
- **Job state:** SQLAlchemy 2.x + SQLite file (`SQLITE_PATH`, default `data/scans.db`)
- **File parsing:** MarkItDown 0.1.x (PDF, DOCX → markdown)
- **Object storage (declared):** boto3 1.35+ for S3/MinIO fetch (not wired yet)
- **Outbound HTTP (declared):** httpx 0.28+ for HMAC webhooks to Next.js (not wired yet)
- **LLM orchestration:** LangChain 1.3.1 (declared; agent is currently a stub)
- **Authentication:** `X-API-Key` header via settings (`API_KEY`) — planned for `POST /scans`

## Testing

- **Unit/integration:** pytest 9.0.3 (dev dependency)
- **Test data:** Factory Boy 3.3.3 — factories in `tests/factories/` (e.g. `ScanCreateFactory`)
- **Integration DB:** in-memory SQLite via SQLAlchemy `StaticPool` (`tests/integration/conftest.py`)
- **E2E:** None
- **Coverage:** None configured

## External Services

- **LLM provider:** Optional `OPENAI_API_KEY` in settings; `run_agent()` returns hardcoded string
- **Object storage:** S3/MinIO env vars in `.env.example`; no client code yet
- **Next.js webhooks:** `NEXT_WEBHOOK_URL` + `WEBHOOK_SECRET` in settings; no client code yet
- **Database:** SQLite file persistence (schema + model defined; repository stub only)

## Development Tools

- **Linting/formatting:** Black 26.5.1, isort 8.0.1, mypy 2.1.0 (dev group only)
- **Test data factories:** Factory Boy 3.3.3 (dev group only)
- **Logging:** structlog 25.5.0 (dev: colored console; prod: JSON)
- **Env config:** `.env` via pydantic-settings (`LOG_*`, S3/webhook vars)

## Entry Point

```bash
uvicorn src.main:app --reload
```

Routes and app instance are defined in `src/main.py`; `src/app.py` provides the FastAPI factory. `POST /scans`, lifespan recovery, and the scan pipeline are in progress per `.specs/features/ats-scan-worker/`.
