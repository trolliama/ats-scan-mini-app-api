# Code Conventions

Observed patterns from the existing codebase (not aspirational style guides).

## Deep Modules

From "A Philosophy of Software Design":

**Deep module** = small interface + lots of implementation

```
┌─────────────────────┐
│   Small Interface   │  ← Few methods, simple params
├─────────────────────┤
│                     │
│                     │
│  Deep Implementation│  ← Complex logic hidden
│                     │
│                     │
└─────────────────────┘
```

**Shallow module** = large interface + little implementation (avoid)

```
┌─────────────────────────────────┐
│       Large Interface           │  ← Many methods, complex params
├─────────────────────────────────┤
│  Thin Implementation            │  ← Just passes through
└─────────────────────────────────┘
```

When designing interfaces, ask:

- Can I reduce the number of methods?
- Can I simplify the parameters?
- Can I hide more complexity inside?

## Naming Conventions

**Files:**
- snake_case module names
- Examples: `main.py`, `resume_parser.py`, `scan_repository.py`, `schemas.py`

**Packages:**
- Short domain names under `src/`
- Examples: `src/db/`, `src/scan/`

**Functions/Methods:**
- snake_case, verb-led for actions
- Examples: `get_app()`, `run_agent()`, `process_scan()`, `extract_markdown_from_resume()`, `init_db()`, `insert_pending()`, `mark_completed()`

**Variables:**
- snake_case
- Examples: `scan_id`, `session_id`, `file_key`, `markdown`, `filename`

**Constants:**
- UPPER_SNAKE_CASE for module-level constants
- Examples: `SUPPORTED_EXTENSIONS`, `ALL_CATEGORY_KEYS`, `APP_LOGGER`, `PROJECT_ROOT`

**Types/Models:**
- PascalCase for Pydantic models, SQLAlchemy models, and custom classes
- Examples: `Scan`, `CreateScanRequest`, `ATSScanResult`, `Settings`, `DevRenderer`
- Type aliases via assignment: `LogLevel = Literal[...]`, `ATSCategoryKey = Literal[...]`
- Exception classes: PascalCase with `Error` suffix — e.g. `DuplicateScanError`
- Dataclass-like inputs: PascalCase nouns — e.g. `ScanCreate`

**Tests:**
- Test modules: `test_<subject>.py` under `tests/unit/` or `tests/integration/`
- Test functions: `test_<behaviour>_when_<context>` — behaviour first, triggering context second
- **Docstrings: required** on every test function — one sentence stating the expected outcome
- **Verification: do not round-trip through the component under test** — assert persistence via raw SQL (`_fetch_scan`), not via another repository method on the same class
- Examples: `test_persists_retrievable_scan_when_insert_pending`, `test_raises_duplicate_scan_error_when_scan_already_exists`
- Test classes (optional grouping): `Test<Subject>` — e.g. `TestScanRepository`
- **Test data: Factory Boy** — build domain objects via factories in `tests/factories/`, not inline helpers or manual dict assembly
- Factory modules: `tests/factories/<domain>.py` — e.g. `scan.py`
- Factory classes: `<Model>Factory` — e.g. `ScanCreateFactory`, `ATSScanResultFactory`
- Use `Factory.build()` for a single instance; `Factory.build_batch(n)` for multiple unique instances
- Override fields at call site: `ScanCreateFactory.build(file_key="custom/path.pdf")`
- Private test helpers: leading underscore — e.g. `_fetch_scan` (assertion/query helpers only, not data builders)

## Code Organization

**Import ordering:**
1. Standard library
2. Third-party packages
3. Local `src.*` imports

Example from `tests/integration/test_scan_repository.py`:

```python
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.db.scan_repository import DuplicateScanError, ScanNotFound, ScanRepository
from src.scan.schemas import ATSScanResult
from tests.factories import ATSScanResultFactory, ScanCreateFactory
```

**File structure within modules:**
- Imports
- Module-level constants / singletons / type aliases
- Exception classes / dataclasses
- Classes / models
- Functions
- Route handlers (in `main.py` only)

**Package imports:** Always absolute from `src.` (e.g. `from src.config import settings`), never relative imports observed.

## Type Safety

**Approach:** Python type hints throughout; Pydantic for request/response schemas; SQLAlchemy 2.x `Mapped[]` annotations; `Literal` for constrained string enums; no mypy config file in repo (mypy in dev deps).

Examples:
- `def extract_markdown_from_resume(content: bytes, filename: str) -> str`
- `id: Mapped[str] = mapped_column(String, primary_key=True)`
- `overall_score: int = Field(ge=0, le=100)`
- Webhook DTOs use camelCase field names matching Next.js contract (`scanId`, `atsScore`)

## Error Handling

**HTTP layer:** Raise `HTTPException` with appropriate status codes (401 unauthorized, 409 duplicate, 422 validation).

**Validation layer:** Raise `ValueError` with user-facing messages; caught at service/route level and mapped to HTTP or scan failure state.

**Repository layer:** Raise domain exceptions — e.g. `DuplicateScanError` on duplicate `scan_id` insert.

**Background tasks:** Broad `except Exception` — mark scan `failed`, store `failure_reason`, send terminal webhook, log with `exc_info=True`.

## Logging

**Pattern:** Domain-scoped loggers via `get_logger("scan")`; contextual binding with `.bind(scan_id=...)`.
**Events:** Short past-tense or state phrases — `"Scan accepted"`, `"Processing started"`, `"Scan not found"`.
**Structured fields:** Passed as kwargs — `file=filename`, `size=format_bytes(...)`.

## Comments/Documentation

**Style:** Minimal. Docstrings only where behavior is non-obvious (e.g. `log_color_enabled` property, `DevRenderer` class, `AgentResult` class docstring).
**Tests:** Every test function must have a one-line docstring describing the expected behaviour.
**No** module-level docstrings on most files.

## Configuration

**Pattern:** `pydantic-settings` `BaseSettings` with `.env` file at project root; cached via `@lru_cache` on `get_settings()`.
**Env vars:** Lowercase field names map to uppercase env vars (`log_level` → `LOG_LEVEL`, `sqlite_path` → `SQLITE_PATH`).
**Required vars:** `api_key`, webhook, and S3 credentials are required — app import fails without a complete `.env`.

## Formatting Tools

Black, isort, and mypy are in the dev dependency group. No `[tool.black]`, `[tool.isort]`, or `[tool.mypy]` sections in `pyproject.toml`. Formatting conventions appear hand-applied (4-space indent, double quotes, trailing commas in multi-line structures).
