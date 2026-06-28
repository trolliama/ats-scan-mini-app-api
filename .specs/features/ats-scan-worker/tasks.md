# ATS Scan Worker Tasks

**Design**: `.specs/features/ats-scan-worker/design.md`  
**Spec**: `.specs/features/ats-scan-worker/spec.md`  
**Status**: In Progress (P2 complete; test infra polish + manual smoke pending)

---

## Progress

| Task | Status | Notes |
|------|--------|-------|
| T1 | ✅ Done | `src/core/config.py`, `.env.example` |
| T2 | ✅ Done | `pyproject.toml` runtime + dev deps |
| T3 | ✅ Done | `src/infra/db/models.py`, `src/infra/db/engine.py` |
| T4 | 🟡 Partial | Schemas in `src/core/models.py` + `src/infra/http/schemas.py`; `tests/unit/test_schemas.py` missing |
| T5 | ✅ Done | `src/infra/db/scan_repository.py`; 8 integration tests pass |
| T6 | ✅ Done | `src/infra/http/dependencies.py` (`verify_api_key`) |
| T7 | ✅ Done | `src/infra/storage/s3.py`; 2 unit tests pass |
| T8 | ✅ Done | `src/infra/webhooks/client.py`; 3 unit tests pass |
| T9 | ✅ Done | `src/ai/agent.py` returns `AgentResult` stub; 2 unit tests pass |
| T10 | ✅ Done | `extract_cv_preview` P1 stub; 2 unit tests pass |
| T11 | ✅ Done | `src/core/services/scan_service.py`; 4 integration tests |
| T12 | ✅ Done | `POST /scans` in `src/infra/http/routes.py`; 6 route tests |
| T13 | ✅ Done | Lifespan recovery in `src/infra/http/app.py`; 4 recovery tests |
| T14 | ✅ Done | `src/ai/agent.py` LLM-backed `run_agent`; 5 unit tests pass |
| T15 | ⚠️ Superseded | Heuristic `extract_cv_preview` removed — cv_preview now from agent (T19) |
| T16 | ✅ Done | Full suite 37 tests pass; integration conftest mocks LLM boundary |
| T19 | ✅ Done | `cv_preview` moved into `run_agent` single LLM call; `test_cv_preview.py` removed |
| T17 | 🟡 Partial | `tests/conftest.py` + `tests/integration/conftest.py`; `TestClient` fixture local to route tests |
| T18 | ⬜ Pending | `tests/http/start.http` still present; no `scans.http` |

**MVP gate (P1):** ✅ Met (T11–T13). **P2 gate:** ✅ Met (T14–T16, T19). Current suite: 37 tests (`poetry run pytest -q`).

> **Path note:** Post-refactor (`706fbee`), task `Where` paths map to the new layout — e.g. `src/config.py` → `src/core/config.py`, `src/db/` → `src/infra/db/`, `src/scan/` → `src/core/services/` + `src/infra/http/`.

---

## Execution Plan

### Phase 1: Foundation (Sequential)

Config, dependencies, database, schemas, and auth must land before any I/O or pipeline code.

```
T1 → T2 → T3 → T4 → T5 → T6
```

### Phase 2: I/O & Stubs (Parallel)

S3 client, webhook client, and P1 stubs are independent once schemas + settings exist.

```
         ┌→ T7  [P] ─┐
T6 ──────┼→ T8  [P] ─┼──→ T11
         └→ T9  [P] ─┘
         └→ T10 [P] ─┘
```

### Phase 3: Pipeline & API (Sequential)

Service orchestration wires Phase 2 modules; route and lifespan depend on the service.

```
T11 → T12 → T13
```

### Phase 4: P2 Enhancements (Parallel)

Real LLM agent and deterministic cv_preview can ship after P1 is green.

```
         ┌→ T14 [P] ─┐
T13 ─────┼→ T15 [P] ─┼──→ T16
         └───────────┘
```

### Phase 5: Test Infrastructure (Sequential)

Shared fixtures and manual smoke docs after P1 routes exist.

```
T13 → T17 → T18
```

---

## Task Breakdown

### T1: Expand Settings and `.env.example`

**What**: Add ATS worker env fields (`api_key`, `sqlite_path`, `next_webhook_url`, `webhook_secret`, S3 vars) with fail-fast validation; document all vars in `.env.example`.  
**Where**: `src/config.py`, `.env.example`  
**Depends on**: None  
**Reuses**: Existing `Settings` + `pydantic-settings` pattern in `src/config.py`  
**Requirements**: ATS-02 (indirect), edge-case fail-fast for `WEBHOOK_SECRET` / `NEXT_WEBHOOK_URL` / S3 vars

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `Settings` exposes all fields from design § Settings table
- [x] Missing required env vars raise `ValidationError` at startup
- [x] `.env.example` lists every new variable with comments
- [x] `poetry run python -c "from src.config import get_settings; get_settings()"` fails clearly without `.env` (manual smoke)

**Tests**: none (config layer — matrix allows deferral until conftest in T17)  
**Gate**: quick

**Commit**: `feat(config): add ATS scan worker settings`

---

### T2: Update runtime and dev dependencies

**What**: Add `boto3`, `httpx`, and `sqlalchemy` to runtime deps; move `mypy`, `black`, `isort` to `[tool.poetry.group.dev.dependencies]`.  
**Where**: `pyproject.toml`  
**Depends on**: None  
**Reuses**: Existing Poetry layout  
**Requirements**: ATS-28

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `boto3`, `httpx`, and `sqlalchemy` in `[project].dependencies`
- [x] `mypy`, `black`, `isort` only in dev group
- [x] `poetry lock && poetry install` succeeds

**Tests**: none  
**Gate**: build (`poetry install`)

**Commit**: `chore(deps): add boto3/httpx/sqlalchemy and move lint tools to dev`

---

### T3: SQLAlchemy models and schema initialization

**What**: Create `Scan` ORM model, `create_db_engine()`, `init_db()` (`Base.metadata.create_all`), and `get_session_factory()` per design § Data Models.  
**Where**: `src/db/models.py`, `src/db/engine.py`  
**Depends on**: T1, T2  
**Reuses**: `Settings.sqlite_path`; ensure parent directory exists before engine creation  
**Requirements**: ATS-06 (storage foundation)

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `Scan` model maps all columns from design (including webhook idempotency flags)
- [x] Index `idx_scans_status` defined on model
- [x] Calling `init_db()` twice is idempotent (no error)
- [x] Parent dir of `SQLITE_PATH` created if missing

**Tests**: none (tested indirectly via T5 repository tests and T17 conftest)  
**Gate**: quick

**Commit**: `feat(db): add SQLAlchemy Scan model and engine setup`

---

### T4: Pydantic scan and webhook schemas

**What**: Define `CreateScanRequest`, `CreateScanResponse`, domain models (`ATSScanResult`, `CVPreview`, `ATSIssue`, `AgentResult`), and camelCase webhook DTOs mirroring `quiz.ts`.  
**Where**: `src/scan/schemas.py`  
**Depends on**: None  
**Reuses**: Pydantic v2 patterns from legacy `JobCreateResponse` in `src/main.py`  
**Requirements**: ATS-03, ATS-15–18 (payload shapes)

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `CreateScanRequest` validates UUID fields; invalid UUID → validation error
- [x] `ATSScanResult` includes all 8 `ATSCategoryKey` values in stub-friendly defaults
- [x] Webhook DTOs use camelCase field names (`scanId`, `atsScore`, `failureReason`)
- [x] `AgentResult` excludes `cv_preview` (LLM output only)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] `tests/unit/test_schemas.py`: valid/invalid `CreateScanRequest`, `ATSScanResult` serialization round-trip
- [ ] Gate check passes: `poetry run pytest -q tests/unit/test_schemas.py`
- [ ] Test count: ≥3 tests pass

**Commit**: `feat(scan): add Pydantic schemas for scans and webhooks`

---

### T5: ScanRepository CRUD

**What**: Implement `ScanRepository` with `insert_pending`, `get_by_id`, `list_incomplete`, `mark_processing`, `mark_completed`, `mark_failed`, webhook flag markers; raise `DuplicateScanError` on duplicate `scan_id`. Accepts SQLAlchemy `Session`.  
**Where**: `src/db/scan_repository.py`  
**Depends on**: T3, T4  
**Reuses**: `src/db/models.py`, `src/db/engine.py`  
**Requirements**: ATS-01, ATS-04, ATS-06, ATS-12, ATS-13, ATS-21

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `insert_pending` raises `DuplicateScanError` for duplicate PK
- [x] `list_incomplete` returns `pending` + `processing` rows
- [x] `mark_*` methods update timestamps (`started_at`, `completed_at`, `updated_at`)
- [x] `result_json` stores serialized `ATSScanResult`
- [x] `tests/integration/test_scan_repository.py`: insert, duplicate 409 path, list_incomplete, mark lifecycle
- [x] Gate check passes: `poetry run pytest -q tests/integration/test_scan_repository.py`
- [x] Test count: ≥5 tests pass (8 pass)

**Tests**: unit  
**Gate**: quick

**Commit**: `feat(db): add ScanRepository for scan persistence`

---

### T6: API key verification dependency

**What**: Create `verify_api_key` FastAPI dependency checking `X-API-Key` header against `settings.api_key`; raise 401 on mismatch.  
**Where**: `src/deps/api_key.py`  
**Depends on**: T1  
**Reuses**: FastAPI `Header` + `HTTPException` pattern  
**Requirements**: ATS-02

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Missing header → 401
- [x] Wrong key → 401
- [x] Correct key → no exception
- [x] Unit-testable via `app.dependency_overrides`

**Tests**: none (covered in T12 route integration tests)  
**Gate**: quick

**Commit**: `feat(auth): add X-API-Key verification dependency`

---

### T7: S3 object fetch client [P]

**What**: Implement `fetch_object(bucket, file_key) -> bytes` using boto3; raise `S3ObjectNotFoundError` with message `S3 object not found: {file_key}` on 404.  
**Where**: `src/storage/s3.py`  
**Depends on**: T1, T2  
**Reuses**: `Settings` S3 fields  
**Requirements**: ATS-08, S3 404 edge case

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Client built from `endpoint_url`, credentials, region
- [x] 404 `ClientError` wrapped as `S3ObjectNotFoundError`
- [x] `tests/unit/test_s3.py`: mock boto3 — happy path returns bytes; 404 raises typed error
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_s3.py`
- [x] Test count: ≥2 tests pass

**Tests**: unit (mocked boto3)  
**Gate**: quick

**Commit**: `feat(storage): add S3 fetch_object client`

---

### T8: Webhook HMAC client with retry [P]

**What**: Implement `sign_payload`, `send_webhook`, and helpers `send_processing`, `send_completed`, `send_failed` with 3 retries (1s, 3s, 9s backoff).  
**Where**: `src/scan/webhook.py`  
**Depends on**: T1, T2, T4  
**Reuses**: structlog for permanent failure log  
**Requirements**: ATS-15–20

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Header format: `X-Webhook-Signature: sha256=<lowercase hex>`
- [x] Processing payload: `{ scanId, status: "processing" }`
- [x] Completed payload includes `atsScore`, `jobTitleDetected`, full `result`
- [x] Failed payload includes `failureReason`
- [x] Retries 3× on non-2xx / network error; logs error when exhausted; returns `False`
- [x] `tests/unit/test_webhook.py`: HMAC correctness, single success, 3 retries on 500
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_webhook.py`
- [x] Test count: ≥3 tests pass

**Tests**: unit (mock httpx)  
**Gate**: quick

**Commit**: `feat(scan): add HMAC webhook client with retry`

---

### T9: P1 agent stub [P]

**What**: Refactor `run_agent(markdown: str) -> AgentResult` to return deterministic stub (zeros, empty lists, `job_title_detected=None`). Remove old string return type.  
**Where**: `src/agent.py`  
**Depends on**: T4  
**Reuses**: Existing LangChain imports (unused until T14)  
**Requirements**: ATS-10

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Signature returns `AgentResult` Pydantic model
- [x] All 8 category keys present at score 0
- [x] No LLM call in P1 stub
- [x] `tests/unit/test_agent.py`: stub returns valid schema
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_agent.py`
- [x] Test count: ≥1 test passes

**Tests**: unit  
**Gate**: quick

**Commit**: `feat(agent): add P1 stub returning AgentResult`

---

### T10: P1 cv_preview stub [P]

**What**: Add `extract_cv_preview(markdown: str) -> CVPreview` returning empty-safe full model (empty strings/arrays, no LLM).  
**Where**: `src/resume_parser.py`  
**Depends on**: T4  
**Reuses**: Existing `extract_markdown_from_resume` unchanged  
**Requirements**: ATS-11, OQ-1

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Returns full `CVPreview` shape (contact, experience, education arrays)
- [x] Completes synchronously with no network I/O
- [x] `tests/unit/test_cv_preview.py`: required keys present; `name` is str (may be empty)
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_cv_preview.py`
- [x] Test count: ≥2 tests pass

**Tests**: unit  
**Gate**: quick

**Commit**: `feat(parser): add P1 cv_preview stub extractor`

---

### T11: Scan pipeline orchestration

**What**: Implement `process_scan(scan_id, repo, settings)` per design algorithm — processing webhook, S3 fetch, parse, agent, assemble result, terminal webhook, failure handling, recovery skip for processing webhook.  
**Where**: `src/scan/service.py`  
**Depends on**: T5, T7, T8, T9, T10  
**Reuses**: `extract_markdown_from_resume`, structured logging with `scan_id=` binding  
**Requirements**: ATS-06–14, ATS-24

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Skips if scan already `completed` or `failed`
- [x] Sends processing webhook only when `webhook_processing_sent` is false
- [x] On success: SQLite `completed` + terminal completed webhook
- [x] On any exception: SQLite `failed` + terminal failed webhook; `failure_reason=str(exc)`
- [x] Does not revert SQLite on webhook exhaustion (ATS-20)
- [x] No `print(markdown)` — debug log uses length only (ATS-27)
- [x] `tests/integration/test_process_scan.py`: mock S3/agent/webhook; happy path + S3 404 + parse error + recovery skip processing webhook
- [x] Gate check passes: `poetry run pytest -q tests/integration/test_process_scan.py`
- [x] Test count: ≥4 tests pass (4 pass)

**Tests**: integration (mocked externals, real temp SQLite)  
**Gate**: full (`poetry run pytest -v tests/integration/test_process_scan.py`)

**Commit**: `feat(scan): implement process_scan pipeline`

---

### T12: POST /scans route and legacy removal

**What**: Replace legacy `/resume/analyze` routes and `jobs` dict with `POST /scans` (202), wire `BackgroundTasks` → `process_scan`, remove `JobCreateResponse`/`JobStatusResponse` and `process_resume`.  
**Where**: `src/main.py`  
**Depends on**: T5, T6, T11  
**Reuses**: `get_app()`, `BackgroundTasks`  
**Requirements**: ATS-01–05, ATS-25–27

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Valid key + body → 202 `{ scan_id, status: "pending" }`
- [x] Missing/invalid key → 401
- [x] Invalid body / non-UUID → 422
- [x] Duplicate `scan_id` → 409
- [x] `POST /resume/analyze` and `GET /resume/analyze/{id}` return 404
- [x] No module-level `jobs` dict
- [x] `tests/integration/test_scans_route.py`: 202, 401, 409 paths via TestClient + dependency overrides
- [x] Gate check passes: `poetry run pytest -q tests/integration/test_scans_route.py`
- [x] Test count: ≥3 tests pass (6 pass)

**Tests**: integration  
**Gate**: full

**Commit**: `feat(api): add POST /scans and remove legacy analyze routes`

---

### T13: Lifespan startup recovery

**What**: Add `lifespan` to `get_app()` — init DB via `init_db(engine)`, attach `engine` + `session_factory` to `app.state`, re-enqueue incomplete scans on startup.  
**Where**: `src/app.py`, `src/main.py`  
**Depends on**: T3, T5, T11, T12  
**Reuses**: Existing `get_app()` factory  
**Requirements**: ATS-22–24

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Startup calls `init_db(engine)` and logs incomplete scan count
- [x] Each pending/processing scan enqueued via `BackgroundTasks` *(uses `asyncio.create_task` + `to_thread`)*
- [x] Log "No incomplete scans to recover" when none found
- [x] `tests/integration/test_recovery.py`: insert pending + processing scans; simulate lifespan startup; assert re-enqueued (mock `process_scan` or assert eventual terminal state)
- [x] Gate check passes: `poetry run pytest -q tests/integration/test_recovery.py`
- [x] Test count: ≥2 tests pass (4 pass)

**Tests**: integration  
**Gate**: full

**Commit**: `feat(app): add startup recovery for incomplete scans`

---

### T14: Real LLM agent [P]

**What**: Replace P1 stub with LangChain + OpenAI structured JSON output → `AgentResult`; fail fast if `OPENAI_API_KEY` missing; raise on LLM timeout/error.  
**Where**: `src/agent.py`  
**Depends on**: T13  
**Reuses**: Existing LangChain dependency; ATS category keys in prompt  
**Requirements**: ATS-29–32, OQ-2, OQ-3

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `run_agent` invokes LLM with structured prompt listing allowed category keys
- [x] Returns typed `AgentResult` with all required fields
- [x] LLM failure raises exception (pipeline marks scan failed)
- [x] Missing `OPENAI_API_KEY` fails at startup when agent mode requires it
- [x] Issue `id` generated (UUID4) if LLM omits
- [x] `tests/unit/test_agent.py` updated: mock OpenAI/LangChain; schema validation
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_agent.py`
- [x] Test count: ≥3 tests pass (including mock failure path) — 5 pass

**Tests**: unit (mocked LLM)  
**Gate**: quick

**Commit**: `feat(agent): implement LLM-backed run_agent`

---

### T15: Deterministic cv_preview extractor [P]

**What**: Replace P1 stub with heuristics — parse name from first heading, regex contact info, split sections into experience/education/skills.  
**Where**: `src/resume_parser.py`  
**Depends on**: T13  
**Reuses**: MarkItDown markdown structure  
**Requirements**: ATS-33–35

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Extracts `name`, `contact`, `summary`, structured sections from sample markdown fixture
- [x] Returns `name=""` gracefully when not found (not an error)
- [x] Completes in < 100ms on fixture (no LLM, no network)
- [x] `tests/unit/test_cv_preview.py` updated with real resume markdown fixture
- [x] Gate check passes: `poetry run pytest -q tests/unit/test_cv_preview.py`
- [x] Test count: ≥4 tests pass — 6 pass

**Tests**: unit  
**Gate**: quick

**Commit**: `feat(parser): implement deterministic cv_preview extraction`

> **Superseded by T19:** heuristic extractor removed; cv_preview sourced from `run_agent` LLM structured output.

---

### T19: Move cv_preview into agent single LLM call

**What**: Expand `AgentResult` and `run_agent` to return `cv_preview` alongside ATS scores in one structured LLM call; remove `extract_cv_preview` heuristics from `resume_parser.py`.  
**Where**: `src/ai/agent.py`, `src/core/models.py`, `src/core/services/scan_service.py`, `src/ai/resume_parser.py`, tests  
**Depends on**: T14, T15 (supersedes T15 approach)  
**Requirements**: ATS-33–35 (revised)

**Done when**:

- [x] `AgentResult` includes `cv_preview: CVPreview`
- [x] `_AgentResultFromLLM` schema + prompt instruct LLM to extract preview fields
- [x] `scan_service` assembles `ATSScanResult` from agent output only
- [x] `extract_cv_preview` and heuristic helpers removed from `resume_parser.py`
- [x] `tests/unit/test_cv_preview.py` deleted; 2 agent cv_preview tests added
- [x] Gate check passes: `poetry run pytest -q` — 37 tests

**Tests**: unit + integration  
**Gate**: full

**Commit**: `refactor(agent): return cv_preview in single structured LLM call`

---

### T16: P2 integration verification

**What**: Run full pytest suite with P2 agent + cv_preview wired; fix any schema/webhook payload mismatches against `quiz.ts` contract.  
**Where**: `tests/` (adjustments only if needed)  
**Depends on**: T14, T15  
**Reuses**: All existing tests  
**Requirements**: ATS-29–35 (integration validation)

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `poetry run pytest -v` exits 0 with no failures
- [x] Total test count ≥ 15 across all test modules — 41 tests
- [x] No silent test deletions vs post-T13 baseline

**Tests**: integration (full suite)  
**Gate**: full

**Commit**: `test(scan): verify P2 agent and cv_preview integration`

---

### T17: Shared pytest fixtures

**What**: Create `tests/conftest.py` and `tests/integration/conftest.py` with SQLAlchemy session fixtures, temp SQLite DB, settings override, TestClient fixture, and shared sample markdown/PDF fixtures.  
**Where**: `tests/conftest.py`, `tests/integration/conftest.py`, `tests/fixtures/` (if needed)  
**Depends on**: T13  
**Reuses**: Patterns from design § Testing Strategy  
**Requirements**: ATS-37

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] Each test gets isolated SQLAlchemy session (in-memory `StaticPool` or `tmp_path` file DB) — `tests/integration/conftest.py`
- [x] `Settings` overridable via fixture / env monkeypatch — `tests/conftest.py` session `settings` fixture
- [ ] `TestClient` fixture with `app.dependency_overrides` for API key — `api_client` local to `test_scans_route.py`
- [ ] Refactor earlier test files to use shared fixtures (no duplicate setup)
- [x] Gate check passes: `poetry run pytest -q`
- [x] All prior tests still pass

**Tests**: none (infrastructure)  
**Gate**: full

**Commit**: `test: add shared pytest conftest and fixtures`

---

### T18: Manual HTTP smoke file and docs

**What**: Replace `tests/http/start.http` with `tests/http/scans.http` documenting `POST /scans` smoke flow; note required env vars in README if missing.  
**Where**: `tests/http/scans.http`, `README.md` (minimal env section only if absent)  
**Depends on**: T17  
**Reuses**: REST Client variable chaining pattern from `start.http`  
**Requirements**: ATS-36 (manual complement)

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [ ] `scans.http` shows `POST /scans` with `X-API-Key` header
- [ ] Old `start.http` removed or replaced
- [ ] Manual smoke steps documented (server start + sample curl/http)

**Tests**: none (manual)  
**Gate**: manual smoke

**Commit**: `docs(test): add scans.http manual smoke file`

---

## Parallel Execution Map

```
Phase 1 (Sequential):
  T1 ──→ T2 ──→ T3 ──→ T4 ──→ T5 ──→ T6

Phase 2 (Parallel — after T6):
  T6 complete, then concurrently:
    ├── T7  [P]  S3 client
    ├── T8  [P]  Webhook client
    ├── T9  [P]  Agent stub
    └── T10 [P]  cv_preview stub

Phase 3 (Sequential):
  T11 ──→ T12 ──→ T13

Phase 4 (Parallel — after T13):
  T13 complete, then concurrently:
    ├── T14 [P]  LLM agent
    └── T15 [P]  cv_preview heuristics
  T14 + T15 ──→ T16

Phase 5 (Sequential):
  T13 ──→ T17 ──→ T18
```

**Note:** T17 can start after T13 but should refactor tests written in T4–T13. Run T17 before T16 final gate or merge T17 into Phase 3 if fixture duplication becomes painful during Execute.

---

## Task Granularity Check

| Task | Scope | Granularity | Completion |
|------|-------|-------------|------------|
| T1: Settings + .env.example | 2 config files | ✅ Cohesive config deliverable | ✅ Done |
| T2: pyproject.toml deps | 1 file | ✅ Granular | ✅ Done |
| T3: models.py + engine.py | 2 modules | ✅ Granular | ✅ Done |
| T4: schemas.py | 1 module | ✅ Granular | 🟡 Partial (no unit tests) |
| T5: scan_repository.py | 1 class | ✅ Granular | ✅ Done |
| T6: api_key.py | 1 dependency | ✅ Granular | ✅ Done |
| T7: s3.py | 1 client function | ✅ Granular | ✅ Done |
| T8: webhook.py | 1 module | ✅ Granular | ✅ Done |
| T9: agent stub | 1 function refactor | ✅ Granular | ✅ Done |
| T10: cv_preview stub | 1 function | ✅ Granular | ✅ Done |
| T11: service.py pipeline | 1 orchestrator | ✅ Granular | ✅ Done |
| T12: POST /scans + legacy removal | 1 route file refactor | ✅ Granular | ✅ Done |
| T13: lifespan recovery | app.py + main wiring | ✅ Cohesive | ✅ Done |
| T14: LLM agent | 1 function | ✅ Granular | ✅ Done |
| T15: cv_preview heuristics | 1 function | ✅ Granular | ✅ Done |
| T16: P2 integration verify | test adjustments | ✅ Granular | ✅ Done |
| T17: conftest | 1 fixture file | ✅ Granular | 🟡 Partial |
| T18: manual smoke | 1 http file | ✅ Granular | ⬜ Pending |

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram Shows | Status |
|------|-------------------|---------------|--------|
| T1 | None | Phase 1 start | ✅ Match |
| T2 | None | Parallel with T1 in plan (both foundation) | ✅ Match |
| T3 | T1 | T1 → T3 | ✅ Match |
| T4 | None | Early foundation (parallel with T1/T2) | ✅ Match |
| T5 | T3, T4 | T3 → T4 → T5 | ✅ Match |
| T6 | T1 | T1 → … → T6 | ✅ Match |
| T7 | T1, T2 | T6 → T7 [P] | ✅ Match |
| T8 | T1, T2, T4 | T6 → T8 [P] | ✅ Match |
| T9 | T4 | T6 → T9 [P] | ✅ Match |
| T10 | T4 | T6 → T10 [P] | ✅ Match |
| T11 | T5, T7, T8, T9, T10 | T7–T10 → T11 | ✅ Match |
| T12 | T5, T6, T11 | T11 → T12 | ✅ Match |
| T13 | T3, T5, T11, T12 | T12 → T13 | ✅ Match |
| T14 | T13 | T13 → T14 [P] | ✅ Match |
| T15 | T13 | T13 → T15 [P] | ✅ Match |
| T16 | T14, T15 | T14+T15 → T16 | ✅ Match |
| T17 | T13 | T13 → T17 | ✅ Match |
| T18 | T17 | T17 → T18 | ✅ Match |

---

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
|------|------------|-----------------|-----------|--------|
| T1: Settings | Logger/config | unit | none | ✅ OK — no behavior to unit test; validated at import |
| T2: deps | pyproject | none | none | ✅ OK |
| T3: SQLAlchemy schema | db | none | none | ✅ OK — covered via repository tests |
| T4: schemas | domain models | unit (implicit) | unit | ✅ OK |
| T5: scan_repository | db/scan_repository | integration | integration | ✅ OK |
| T6: api_key | auth dep | none | none (T12 covers) | ✅ OK — HTTP auth tested at route layer |
| T7: s3 | storage | unit | unit (mocked) | ✅ OK |
| T8: webhook | scan/webhook | unit | unit | ✅ OK |
| T9: agent stub | agent | unit | unit | ✅ OK |
| T10: cv_preview stub | resume_parser | unit | unit | ✅ OK |
| T11: process_scan | background lifecycle | integration | integration | ✅ OK |
| T12: POST /scans | HTTP routes | integration | integration | ✅ OK |
| T13: recovery | background lifecycle | integration | integration | ✅ OK |
| T14: LLM agent | agent | unit | unit | ✅ OK |
| T15: cv_preview | resume_parser | unit | unit | ✅ OK |
| T16: P2 verify | full suite | integration | integration | ✅ OK |
| T17: conftest | test infra | none | none | ✅ OK |
| T18: scans.http | manual e2e | manual | none | ✅ OK |

---

## Requirement Traceability (tasks mapping)

| Req ID | Task(s) |
|--------|---------|
| ATS-01 | T5, T12 |
| ATS-02 | T6, T12 |
| ATS-03 | T4, T12 |
| ATS-04 | T5, T12 |
| ATS-05 | T11, T12 |
| ATS-06 | T3, T5, T11 |
| ATS-07 | T11 |
| ATS-08 | T7, T11 |
| ATS-09 | T11 |
| ATS-10 | T9, T11 |
| ATS-11 | T10, T11 |
| ATS-12 | T5, T11 |
| ATS-13 | T5, T11 |
| ATS-14 | T11 |
| ATS-15 | T8 |
| ATS-16 | T8 |
| ATS-17 | T8 |
| ATS-18 | T8 |
| ATS-19 | T8 |
| ATS-20 | T8, T11 |
| ATS-21 | T5, T11 |
| ATS-22 | T13 |
| ATS-23 | T13 |
| ATS-24 | T11, T13 |
| ATS-25 | T12 |
| ATS-26 | T12 |
| ATS-27 | T11, T12 |
| ATS-28 | T2 |
| ATS-29 | T14 |
| ATS-30 | T14 |
| ATS-31 | T14, T11 |
| ATS-32 | T1, T14 |
| ATS-33 | T15 |
| ATS-34 | T15 |
| ATS-35 | T15 |
| ATS-36 | T4, T5, T8, T10, T12, T16, T18 |
| ATS-37 | T7, T8, T11, T17 |

**Coverage:** 37 total, 37 mapped to tasks, 0 unmapped ✅

---

## Execute Notes

**Foundation (T1–T6):** Complete. T4 schema unit tests still outstanding.

**P1 pipeline (T11–T13):** Complete. `process_scan`, `POST /scans`, and lifespan recovery are implemented with integration tests.

**P2 enhancements (T14–T16):** Complete. Real LLM agent, deterministic cv_preview, full suite green (41 tests).

**Next session:** T17 polish + T18 manual smoke.

**MVP gate (P1 done):** ✅ Met — `poetry run pytest -v` (34 tests) and manual `POST /scans` returns 202 with stub pipeline reaching SQLite `completed`.

**P2 gate:** ✅ Met — `poetry run pytest -v` (41 tests) with LLM mocked at boundary in integration tests.

**Before Execute — tools check:** Confirm which MCPs/skills to use per task (filesystem-only is sufficient for all tasks in this feature).
