# Testing Infrastructure

## Test Frameworks

**Unit/Integration:** pytest 9.0.3 (dev dependency in `pyproject.toml`)
**Test data:** Factory Boy 3.3.3 (dev dependency in `pyproject.toml`)
**E2E:** None
**Coverage:** None configured

## Test Organization

**Location:**

- `tests/integration/` — repository, DB, and cross-module tests
- `tests/unit/` — pure unit tests (S3, webhook, agent, cv_preview)

**Naming:**

- Modules: `test_<subject>.py` (pytest discovery)
- Functions: `test_<behaviour>_when_<context>` — state the outcome first, then the setup or trigger
- **Docstrings: required** — one sentence per test function; state what must hold, not how the test is wired

**Examples:**

| Test                                                        | Docstring                                                                      |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `test_persists_retrievable_scan_when_insert_pending`        | Inserting a pending scan persists input fields and default lifecycle values.   |
| `test_raises_duplicate_scan_error_when_scan_already_exists` | Inserting the same scan_id twice raises DuplicateScanError and leaves one row. |
| `test_returns_none_when_getting_unknown_scan`               | get_by_id returns None when no scan exists for the given id.                   |

**Structure:** Integration tests use a shared `conftest.py` fixture (`db_session`) and `Test<Subject>` classes for grouping related cases.

## Test Data (Factory Boy)

**Purpose:** Centralize realistic defaults for domain objects used in tests.

**Location:** `tests/factories/` — one module per domain (e.g. `tests/factories/scan.py`).

**Naming:** `<Model>Factory` classes targeting Pydantic models, dataclasses, or repository input types.

**Usage:**

| Need                     | Call                                           |
| ------------------------ | ---------------------------------------------- |
| One object with defaults | `ScanCreateFactory.build()`                    |
| Several unique objects   | `ScanCreateFactory.build_batch(4)`             |
| Override a field         | `ATSScanResultFactory.build(overall_score=85)` |

**Rules:**

- Do not add private `_model_create()` helpers in test modules — add or extend a factory instead
- Keep assertion/query helpers (e.g. `_fetch_scan`) separate from data factories
- Nested objects use `factory.SubFactory` or `factory.LazyFunction` — avoid shared mutable defaults

**Current factories:** `ScanCreateFactory`, `ATSScanResultFactory` (with `CVPreviewFactory`, `ATSIssueFactory`).

## Verification Rules

**Do not round-trip through the component under test.** When a test exercises method A, assert its side effects via an independent path — not via method B on the same class.

| Under test                      | Avoid                       | Prefer                                                       |
| ------------------------------- | --------------------------- | ------------------------------------------------------------ |
| `ScanRepository.insert_pending` | `repository.get_by_id(...)` | Raw SQL via test helper (`_fetch_scan`)                      |
| `ScanRepository.mark_completed` | `repository.get_by_id(...)` | Raw SQL via test helper                                      |
| `ScanRepository.get_by_id`      | —                           | Call `get_by_id` directly (it _is_ the behaviour under test) |

Shared implementation bugs in write and read paths would pass a test that writes with one method and reads with another on the same object. Bypassing the repository for assertions keeps persistence tests honest.

## Testing Patterns

### Unit Tests

**Approach:** pytest with mocked external deps (boto3, httpx); no DB or network.
**Location:** `tests/unit/`

### Integration Tests

**Approach:** pytest with in-memory SQLite (`StaticPool`) and SQLAlchemy session fixtures.
**Location:** `tests/integration/`
**Fixtures:** `tests/integration/conftest.py` provides `db_session` (creates schema via `init_db`, yields session, disposes engine).
**Assertion path:** Repository write/lifecycle tests verify rows with `_fetch_scan` (raw `SELECT *`); only tests whose behaviour _is_ the read API call `get_by_id` / `list_incomplete` directly.
**Current status:** Tests are written (TDD); `src/db/scan_repository.py` is a stub — tests fail on import until repository is implemented.

## Test Execution

**Commands:**

```bash
# Install dependencies
poetry install

# Run all pytest
poetry run pytest

# Run unit tests only
poetry run pytest tests/unit/ -v

# Run integration tests only
poetry run pytest tests/integration/ -v
```

**Configuration:** `tests/integration/conftest.py` provides DB session fixture. No root `pytest.ini` yet.

## Parallelism Assessment

| Test Type   | Parallel-Safe? | Isolation Model                                         | Evidence                                                      |
| ----------- | -------------- | ------------------------------------------------------- | ------------------------------------------------------------- |
| Integration | Yes            | Fresh in-memory SQLite engine per `db_session` fixture  | `conftest.py` — `StaticPool`, engine disposed after each test |
| Unit        | Yes            | Pure functions, mock external deps                      | `resume_parser.py` singleton is read-only after init          |
| Route tests | Yes            | TestClient with dependency overrides; fresh DB per test | Planned in tasks — mock S3/agent/webhook                      |

## Gate Check Commands

| Gate Level | When to Use                  | Command                                                                   |
| ---------- | ---------------------------- | ------------------------------------------------------------------------- |
| Quick      | After unit-test tasks        | `poetry run pytest -q`                                                    |
| Repository | After scan repository task   | `poetry run pytest -q tests/integration/test_scan_repository.py`          |
| Full       | After integration tasks      | `poetry run pytest -v`                                                    |
| Build      | Before merge (not automated) | `poetry run pytest && poetry run mypy src/` (mypy config not yet defined) |
