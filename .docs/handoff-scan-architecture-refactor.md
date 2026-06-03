# Handoff: Scan Repository & ATS Architecture Refactor

**Created:** 2026-06-02  
**Status:** Design complete — implementation not started  
**Origin:** Grill-me session refining a refactor of `src/db/scan_repository.py` into a layered architecture with Unit of Work, domain separation, and full ATS vertical slice.

---

## Problem

The scan persistence layer lives in a single file (`src/db/scan_repository.py`) that mixes concerns:

- Domain exceptions (`DuplicateScanError`, `ScanNotFound`) inside the repository
- Input/output dataclasses (`ScanCreate`, `ScanRecord`) colocated with SQLAlchemy access
- Every repository method calls `session.commit()` — callers cannot compose atomic multi-step transactions
- HTTP schemas (`src/scan/schemas.py`) mix domain types (`ATSScanResult`) with API contracts (`CreateScanRequest`, webhook payloads)
- No service layer, no S3/webhook clients, no `POST /scans` route — legacy in-memory `/resume/analyze` endpoints remain in `main.py`

The ATS scan worker feature (see linked specs below) requires a production-ready pipeline: accept jobs, persist state in SQLite, fetch PDFs from S3, run analysis, push HMAC webhooks to Next.js, and recover incomplete scans on restart.

---

## Solution

Restructure the codebase into layer-centric packages with clear dependency rules, module-level UoW functions, Pydantic domain models, a service orchestration layer, and a dedicated HTTP package. Deliver the full vertical slice in one implementation pass.

### Target directory layout

```
src/
  ai/
    agent.py                 # run_agent() → AgentResult (P1 stub)
    resume_parser.py         # extract_markdown_from_resume, extract_cv_preview (P1 stub)
  core/
    exceptions.py            # Domain errors (DuplicateScanError, ScanNotFound, S3ObjectNotFoundError, …)
    models.py                # All domain Pydantic models (frozen, strict validation)
    services/
      scan_service.py        # create_scan, process_scan (module-level functions)
  infra/
    db/
      models.py              # SQLAlchemy ORM Scan model
      engine.py              # create_db_engine, init_db, get_session_factory
      scan_repository.py     # Persistence only; no commit(); masks IntegrityError
      unit_of_work.py        # unit_of_work(), commit(); UoWContext NamedTuple
    storage/
      s3.py                  # fetch_object(bucket, key) → bytes
    webhooks/
      client.py              # HMAC sign + send + retry
  http/
    dependencies.py          # get_uow, verify_api_key
    schemas.py               # HTTP-only contracts
    routes.py                # POST /scans router
    exception_handlers.py    # Domain exception → HTTP status mapping
  app.py                     # FastAPI app + lifespan (DB init, recovery, dispose)
  main.py                    # Bootstrap: logging, mount router
  config.py
  logger.py
```

### Dependency flow

```
http          → core/services, core/exceptions, core/models (via schemas import)
core/services → infra/*, ai/*, core/models, core/exceptions
infra         → core/*
ai            → core/models
core          → (nothing outward — innermost layer)
```

**No Protocol/interfaces** unless a second implementation exists.

---

## Decisions log

| # | Topic | Decision | Rationale |
|---|-------|----------|-----------|
| 1 | Folder layout | Layer-centric (`core/`, `infra/`, `http/`) | Single cut across the app; not feature-centric `scan/core/` |
| 2 | UoW motivation | Transaction correctness + multi-repo session sharing | Atomic multi-step ops; future repos share one session |
| 3 | FastAPI integration | `Depends(get_uow)` in `http/dependencies.py` | Routes use injection; background tasks call same helper |
| 4 | Domain errors | `core/exceptions.py` separate from `core/models.py` | Clear split by kind |
| 5 | Domain types location | All domain Pydantic models in `core/models.py` | `ATSScanResult` and composed types move out of HTTP schemas |
| 6 | HTTP schemas | `http/schemas.py` — request/response/webhook DTOs only | Imports `ATSScanResult` from core when needed |
| 7 | Infra layout | Sub-packages: `infra/db/`, `infra/storage/`, `infra/webhooks/` | One integration per sub-package |
| 8 | UoW commit | Explicit `commit()`; auto-rollback on exception | Transaction boundary visible at call site |
| 9 | Domain type migration | Move all types `ATSScanResult` depends on to `core/models.py` | Avoid core → http dependency violation |
| 10 | Model technology | Everything Pydantic (no dataclasses) | Consistent validation and serialization |
| 11 | Validation strictness | Domain invariants enforced (`ScanStatus` Literal, score bounds) | Invalid states caught at model boundary |
| 12 | Immutability | All `core/models.py` models frozen (`ConfigDict(frozen=True)`) | State changes only via repository/service |
| 13 | UoW class location | Module-level functions in `infra/db/unit_of_work.py` | No behaviour class; functions + NamedTuple bundle |
| 14 | UoW API | `UoWContext` NamedTuple + `unit_of_work()` context manager + `commit(uow)` | Ergonomic `uow.scans` without a UoW class |
| 15 | `get_uow` location | `http/dependencies.py` imports from `infra/db/unit_of_work` | HTTP wiring separate from infra implementation |
| 16 | HTTP package name | `http/` not `scan/` | Everything inside is HTTP-facing |
| 17 | Routes ownership | `http/routes.py` owns all route handlers; `main.py` is bootstrap only | HTTP surface co-located |
| 18 | Business logic | `core/services/scan_service.py` — routes call services, not UoW directly | Reusable from background tasks without importing http |
| 19 | Services location | `core/services/` (not top-level `services/`) | User preference — orchestration under core |
| 20 | Implementation scope | Full vertical slice | Structure + POST /scans + process_scan + S3 + webhooks + recovery |
| 21 | Legacy endpoints | Remove `/resume/analyze` and in-memory `jobs` dict | Replaced by POST /scans + webhooks |
| 22 | Exception → HTTP | Global handlers in `http/exception_handlers.py` | Centralized mapping; services raise domain errors |
| 23 | Service style | Module-level functions (no service class) | Matches existing patterns; no polymorphism needed |
| 24 | AI libs location | `src/ai/agent.py`, `src/ai/resume_parser.py` | Group LLM + parsing adapters |
| 25 | Startup recovery | Lifespan re-enqueues incomplete scans on boot | ATS-24; crash recovery is production requirement |

---

## Key implementation patterns

### Unit of Work (module-level)

```python
# infra/db/unit_of_work.py
class UoWContext(NamedTuple):
    session: Session
    scans: ScanRepository

@contextmanager
def unit_of_work(session_factory) -> Generator[UoWContext, None, None]:
    session = session_factory()
    try:
        yield UoWContext(session=session, scans=ScanRepository(session))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def commit(ctx: UoWContext) -> None:
    ctx.session.commit()
```

Usage:

```python
with unit_of_work(session_factory) as uow:
    uow.scans.insert_pending(record)
    commit(uow)
```

### FastAPI dependency

```python
# http/dependencies.py
def get_uow(request: Request) -> Generator[UoWContext, None, None]:
    factory = request.app.state.session_factory
    with unit_of_work(factory) as uow:
        yield uow
```

Note: route handlers must call `commit(uow)` before the dependency context exits. Background tasks open their own `unit_of_work(session_factory)`.

### Domain models (Pydantic, frozen, strict)

```python
ScanStatus = Literal["pending", "processing", "completed", "failed"]

class ScanCreate(BaseModel):
    model_config = ConfigDict(frozen=True)
    scan_id: UUID
    session_id: UUID
    file_key: str = Field(min_length=1)
    bucket: str = Field(min_length=1)
    original_filename: str = Field(min_length=1)

class ScanRecord(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    session_id: str
    status: ScanStatus
    ats_score: int | None = Field(default=None, ge=0, le=100)
    # ... remaining fields
```

### Repository (no commit)

- Remove all `self._session.commit()` calls from `ScanRepository`
- Keep `IntegrityError → DuplicateScanError` translation in repository
- Keep `ScanNotFound` raised from `_require_scan` / `get_by_id`

### process_scan pipeline

1. Open `unit_of_work`, `mark_processing`, `commit`
2. Send processing webhook (skip if `webhook_processing_sent`); mark flag + `commit`
3. S3 fetch → parse markdown → cv_preview stub → agent stub
4. `mark_completed` or `mark_failed` + `commit`
5. Send terminal webhook + mark `webhook_terminal_sent` + `commit`
6. On any pipeline failure: broad `except Exception`, mark failed, send failed webhook, log with `exc_info=True`

P1 stubs per design spec:
- `run_agent()` → deterministic `AgentResult` (zeros, empty lists)
- `extract_cv_preview()` → empty-safe `CVPreview`

### HTTP surface

| Endpoint | Auth | Status | Notes |
|----------|------|--------|-------|
| `POST /scans` | `X-API-Key` | 202 | Enqueues `process_scan` via BackgroundTasks |
| — | — | 401 | Missing/invalid API key |
| — | — | 409 | `DuplicateScanError` |
| — | — | 422 | Validation errors |

Remove: `POST /resume/analyze`, `GET /resume/analyze/{job_id}`.

### Lifespan (app.py)

1. Create engine + session_factory → `app.state`
2. `init_db(engine)`
3. List incomplete scans; enqueue `process_scan` for each
4. On shutdown: `engine.dispose()`

---

## Implementation tasks

Execute in roughly this order. Each task should be a reviewable unit.

### Phase 1 — Core layer

- [ ] **T1** Create `src/core/exceptions.py` — move `DuplicateScanError`, `ScanNotFound`; add `S3ObjectNotFoundError`
- [ ] **T2** Create `src/core/models.py` — migrate all domain Pydantic models from `src/scan/schemas.py` plus `ScanCreate`/`ScanRecord` from repository; apply frozen + strict validation
- [ ] **T3** Slim `src/scan/schemas.py` → `src/http/schemas.py` — HTTP-only DTOs; import domain types from core

### Phase 2 — Infra layer

- [ ] **T4** Move `src/db/models.py` → `src/infra/db/models.py`
- [ ] **T5** Move `src/db/engine.py` → `src/infra/db/engine.py`; fix imports
- [ ] **T6** Refactor repository → `src/infra/db/scan_repository.py` — remove commits; import from `core.*`; update `_to_record()` for Pydantic `ScanRecord`
- [ ] **T7** Implement `src/infra/db/unit_of_work.py` — `UoWContext`, `unit_of_work()`, `commit()`
- [ ] **T8** Implement `src/infra/storage/s3.py` — `fetch_object()`; wrap boto3 `ClientError` 404 → `S3ObjectNotFoundError`
- [ ] **T9** Implement `src/infra/webhooks/client.py` — HMAC sign, httpx POST, retry 1s/3s/9s

### Phase 3 — AI layer

- [ ] **T10** Move `src/agent.py` → `src/ai/agent.py`; update `run_agent()` to return `AgentResult` stub
- [ ] **T11** Move `src/resume_parser.py` → `src/ai/resume_parser.py`; add `extract_cv_preview()` P1 stub

### Phase 4 — Service layer

- [ ] **T12** Implement `src/core/services/scan_service.py`:
  - `create_scan(uow, body) → CreateScanResponse`
  - `process_scan(scan_id, session_factory) → None`
  - `recover_incomplete_scans(session_factory) → list[str]` (scan IDs to enqueue)

### Phase 5 — HTTP layer

- [ ] **T13** Implement `src/http/dependencies.py` — `get_uow`, `verify_api_key`
- [ ] **T14** Implement `src/http/exception_handlers.py` — register on app
- [ ] **T15** Implement `src/http/routes.py` — `POST /scans` router
- [ ] **T16** Update `src/app.py` — lifespan with DB init + recovery
- [ ] **T17** Update `src/main.py` — logging bootstrap, mount router, remove legacy routes

### Phase 6 — Cleanup

- [ ] **T18** Delete `src/db/` package (after all imports updated)
- [ ] **T19** Delete `src/scan/` package (after migration to http/core)

### Phase 7 — Tests

- [ ] **T20** Update `tests/integration/test_scan_repository.py` — use `unit_of_work` + `commit`; update import paths
- [ ] **T21** Update `tests/factories/scan.py` — import from `core.models`
- [ ] **T22** Update `tests/integration/conftest.py` — import from `infra.db.engine`
- [ ] **T23** Add unit tests: webhook signing, exception handlers (per `.specs/features/ats-scan-worker/design.md`)
- [ ] **T24** Add integration test: `POST /scans` → mock S3/agent/webhook → verify DB state via raw SQL
- [ ] **T25** Run full test suite + fix import paths project-wide

---

## Current state (before implementation)

| Path | Status |
|------|--------|
| `src/db/scan_repository.py` | Exists — monolithic repo with commits, errors, dataclasses |
| `src/db/models.py`, `src/db/engine.py` | Exists |
| `src/scan/schemas.py` | Exists — mixed domain + HTTP types |
| `src/main.py` | Legacy `/resume/analyze` in-memory job poller |
| `src/app.py` | Bare `FastAPI()` factory, no lifespan |
| `src/agent.py`, `src/resume_parser.py` | At src root; agent returns string stub |
| S3 / webhook clients | Not implemented (boto3/httpx declared in pyproject.toml) |
| `tests/integration/test_scan_repository.py` | 8 tests against current repository |

---

## References (do not duplicate — read these for detail)

| Document | Path | Use for |
|----------|------|---------|
| ATS feature spec | `.specs/features/ats-scan-worker/spec.md` | Acceptance criteria |
| ATS design | `.specs/features/ats-scan-worker/design.md` | Pipeline steps, webhook contract, error matrix, P1 stubs |
| ATS tasks | `.specs/features/ats-scan-worker/tasks.md` | Existing task breakdown (may need realignment with this handoff) |
| Architecture plan | `.cursor/plans/ats_backend_architecture_a67b1165.plan.md` | End-to-end system context |
| Testing conventions | `.specs/codebase/TESTING.md`, `AGENTS.md` | Test naming, factories, no round-trip verification |
| Code conventions | `.specs/codebase/CONVENTIONS.md` | Import style, naming |
| Integrations | `.specs/codebase/INTEGRATIONS.md` | S3/webhook env vars and contracts |

---

## Suggested skills for implementing agent

| Skill | Path | When to use |
|-------|------|-------------|
| **TDD** | `.cursor/skills/tdd/SKILL.md` | Repository + service + pipeline tests (red-green-refactor) |
| **TLC spec-driven** | `.cursor/skills/tlc-spec-driven/SKILL.md` | Track tasks, atomic commits, verification criteria |
| **Agent guidelines** | `AGENTS.md` | Deep modules, error design, test conventions |

---

## Verification checklist (definition of done)

- [ ] All imports use new paths; `src/db/` and `src/scan/` deleted
- [ ] `pytest` passes (integration + new unit tests)
- [ ] `POST /scans` returns 202 with valid API key; 401/409/422 for error cases
- [ ] Repository methods do not call `commit()` — only `commit(uow)` at service/route level
- [ ] Domain models in `core/models.py` are Pydantic, frozen, with `ScanStatus` Literal
- [ ] `http/schemas.py` contains no domain logic — only HTTP DTOs
- [ ] Legacy `/resume/analyze` endpoints removed
- [ ] App lifespan recovers incomplete scans on startup
- [ ] No Protocol/interfaces added

---

## Open items / deferred

- Move `agent.py` / `resume_parser.py` deeper under `infra/` — explicitly deferred; `ai/` is the agreed home for now
- P2 LLM integration and full `extract_cv_preview` heuristics
- Webhook reconciler / orphan S3 cleanup
- Update `.specs/codebase/STRUCTURE.md` and `CONVENTIONS.md` to reflect new layout (optional follow-up)
