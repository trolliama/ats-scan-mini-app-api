# Project Structure

**Root:** `/home/caiow/Documents/CopiVaga/mini-app-api`

## Directory Tree

```
mini-app-api/
├── .cursor/              # Cursor IDE config, plans, skills
│   ├── plans/            # Architecture/feature plans
│   └── skills/           # Agent skills (tlc-spec-driven, tdd, diagnose, …)
├── .specs/               # Spec-driven project docs
│   ├── codebase/         # Brownfield analysis (7 files)
│   └── features/
│       └── ats-scan-worker/   # spec.md, design.md, tasks.md
├── src/                  # Application source
│   ├── main.py           # Routes, lifespan, app bootstrap
│   ├── app.py            # FastAPI factory
│   ├── config.py         # Settings (logging + S3/webhook)
│   ├── logger.py         # structlog setup
│   ├── resume_parser.py  # PDF/DOCX → markdown
│   ├── agent.py          # LLM stub
│   ├── db/               # SQLAlchemy persistence
│   │   ├── engine.py
│   │   ├── models.py
│   │   └── scan_repository.py   # stub
│   └── scan/             # Scan domain schemas
│       └── schemas.py
├── tests/
│   ├── factories/        # Factory Boy test data builders
│   │   ├── __init__.py
│   │   └── scan.py       # ScanCreateFactory, ATSScanResultFactory, …
│   └── integration/      # Repository + DB tests
│       ├── conftest.py
│       └── test_scan_repository.py
├── pyproject.toml        # Poetry deps + Python version
├── poetry.lock
├── uv.lock               # uv lockfile (alongside Poetry)
├── .env.example          # Logging + worker env vars
├── .gitignore
└── AGENTS.md             # Empty placeholder
```

## Module Organization

### Application (`src/`)

**Purpose:** All runtime Python code for the FastAPI scan worker.
**Location:** `src/`
**Key files:**
- `main.py` — HTTP API (`POST /scans`), lifespan, background task scheduling
- `app.py` — FastAPI instance factory
- `config.py` — Environment-driven settings
- `logger.py` — Logging infrastructure
- `resume_parser.py` — Document parsing
- `agent.py` — AI analysis (stub)

### Database layer (`src/db/`)

**Purpose:** SQLite persistence for scan lifecycle.
**Location:** `src/db/`
**Key files:**
- `models.py` — `Scan` SQLAlchemy model (complete)
- `engine.py` — Engine creation, directory ensure, `init_db`
- `scan_repository.py` — Repository stub (implementation pending)

### Scan domain (`src/scan/`)

**Purpose:** Pydantic schemas for scan requests, results, and webhooks.
**Location:** `src/scan/schemas.py`

### Tests (`tests/`)

**Purpose:** Automated testing.
**Location:** `tests/integration/`, `tests/factories/`
**Key files:**
- `factories/scan.py` — Factory Boy builders for scan domain test data
- `integration/conftest.py` — `db_session` fixture (in-memory SQLite)
- `integration/test_scan_repository.py` — Repository contract tests (TDD)

### Specs (`.specs/`)

**Purpose:** Persistent project documentation for spec-driven development.
**Location:** `.specs/codebase/` (brownfield), `.specs/features/ats-scan-worker/` (active feature)

### Cursor metadata (`.cursor/`)

**Purpose:** IDE plans and agent skills — not part of runtime.
**Location:** `.cursor/plans/`, `.cursor/skills/`

## Where Things Live

**Scan worker:**
- HTTP routes: `src/main.py` (planned: `POST /scans`)
- Persistence model: `src/db/models.py`
- Engine / schema init: `src/db/engine.py`
- Repository: `src/db/scan_repository.py` (stub)
- Request/result schemas: `src/scan/schemas.py`
- Pipeline: planned `scan/service.py`
- S3 client: planned `storage/s3.py`
- Webhook client: planned `scan/webhook.py`
- API key auth: planned `deps/api_key.py`

**Document parsing & analysis:**
- Markdown extraction: `src/resume_parser.py`
- LLM analysis: `src/agent.py`

**Logging:**
- Configuration: `src/logger.py`
- Settings: `src/config.py` (`LOG_LEVEL`, `LOG_ENV`, `LOG_COLOR`)

**App bootstrap:**
- Factory: `src/app.py`
- Entry (uvicorn target): `src/main:app`

**Configuration:**
- Env template: `.env.example`
- Runtime loader: `src/config.py` (reads `.env` at project root)

## Special Directories

**`.specs/features/ats-scan-worker/`:**
Active feature specification for the background scan worker.

**`.cursor/plans/`:**
Architecture plans. Planning artifacts, not executable code.

**`.specs/codebase/`:**
Brownfield mapping output — load on-demand when working in this repo.
