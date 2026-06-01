# ATS Scan Worker — Feature Specification

**Scope:** FastAPI backend (`mini-app-api`) only. Frontend (Next.js) changes are out of scope for this feature.

**Source plan:** `.cursor/plans/ats_backend_architecture_a67b1165.plan.md` — Fase 3 (FastAPI scan worker) + Fase 5 (tests).

---

## Problem Statement

The current FastAPI service accepts resume uploads via multipart form-data, stores job state in an in-memory dict, and returns a non-functional analysis stub. This breaks in production (no durability on restart, no real LLM output) and cannot integrate with the planned Next.js + Supabase + S3 architecture where Next.js owns file uploads and Supabase is the source of truth.

FastAPI must be reborn as a dedicated **background scan worker**: it receives scan instructions from Next.js via a secure REST endpoint, fetches the PDF from S3/MinIO directly, runs the ATS analysis pipeline, persists state to SQLite, and notifies Next.js of status transitions via HMAC-authenticated webhooks.

---

## Goals

- [ ] Replace in-memory job state with SQLite persistence — scans survive restarts
- [ ] Replace multipart upload endpoint with `POST /scans` — FastAPI fetches from S3
- [ ] Implement real ATS analysis pipeline: S3 fetch → PDF parse → LLM agent → result
- [ ] Notify Next.js of scan lifecycle events (processing, completed, failed) via signed webhooks
- [ ] Re-enqueue incomplete scans automatically on startup
- [ ] Wire a real (partial) LLM agent producing structured ATSScanResult
- [ ] Extract `cv_preview` deterministically from markdown (no LLM)

---

## Out of Scope

Explicitly excluded from this feature.

| Feature | Reason |
|---------|---------|
| Next.js routes (`/api/ats/*`) | Separate feature — frontend-owned |
| Supabase migration (`ats_scans` table) | Separate feature — frontend-owned |
| Next.js S3 presigned URL generation | Separate feature — frontend-owned |
| Frontend report page changes | Separate feature — frontend-owned |
| Mock ATS API (`mock-ats-api/server.js`) | No changes needed — dev-only |
| LGPD delete route removal | Different repo (Next.js) |
| Multi-worker horizontal scaling | Out of MVP scope |
| S3 bucket lifecycle rules (orphan cleanup) | Out of MVP scope |
| Full quiz context in LLM agent | Deferred to post-MVP |
| FastAPI result query endpoint (GET /scans/{id}) | Not required — Next.js reads from Supabase |

---

## User Stories

### P1: Scan Registration ⭐ MVP

**User Story:** As the Next.js app, I want to register a scan job at FastAPI so that background processing begins immediately without blocking the user response.

**Why P1:** This is the entry point of the entire worker. Without it nothing else runs.

**Acceptance Criteria:**

1. WHEN Next.js POSTs to `POST /scans` with a valid `X-API-Key` header and a complete body (`scan_id`, `session_id`, `file_key`, `original_filename`, `bucket`) THEN FastAPI SHALL persist a scan record to SQLite with `status=pending` and respond with HTTP 202 `{ "scan_id": "...", "status": "pending" }`.
2. WHEN the `X-API-Key` header is missing or does not match `API_KEY` config THEN FastAPI SHALL return HTTP 401.
3. WHEN required body fields are missing or invalid THEN FastAPI SHALL return HTTP 422.
4. WHEN `scan_id` already exists in SQLite THEN FastAPI SHALL return HTTP 409 (idempotency guard).
5. WHEN the record is persisted THEN FastAPI SHALL enqueue `process_scan(scan_id)` via `BackgroundTasks` before returning the 202 response.

**Independent Test:** POST `/scans` with valid key and body → assert 202 + SQLite row with `status=pending`; POST same `scan_id` again → assert 409.

---

### P1: Scan Pipeline ⭐ MVP

**User Story:** As the system, I want FastAPI to automatically process an enqueued scan so that the result is available in SQLite for webhook delivery.

**Why P1:** Core value delivery — without this the worker is a dead endpoint.

**Acceptance Criteria:**

1. WHEN `process_scan` starts THEN FastAPI SHALL update SQLite `status=processing` and record `started_at=now()`.
2. WHEN status changes to `processing` THEN FastAPI SHALL send the `processing` webhook to Next.js before proceeding with the pipeline.
3. WHEN FastAPI fetches the PDF from S3 using `bucket` and `file_key` THEN it SHALL use its own S3 credentials (`S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`) — not proxy through Next.js.
4. WHEN the PDF bytes are available THEN FastAPI SHALL extract markdown text using the existing `extract_markdown_from_resume()` function.
5. WHEN markdown is extracted THEN FastAPI SHALL call `run_agent(markdown)` to produce scores, keywords, issues, and `job_title_detected`.
6. WHEN `cv_preview` is needed THEN FastAPI SHALL extract it **deterministically** from the markdown (regex/heuristics — no LLM call for this field).
7. WHEN all steps succeed THEN FastAPI SHALL persist `status=completed`, `result_json`, `ats_score`, `job_title_detected`, `scanned_at=now()` to SQLite.
8. WHEN any step raises an exception THEN FastAPI SHALL persist `status=failed` and `failure_reason=str(exc)` to SQLite.
9. WHEN pipeline completes (success or failure) THEN FastAPI SHALL send the terminal webhook to Next.js with the full result or failure reason.

**Independent Test:** Insert a pending scan in SQLite with a known `file_key`; mock S3 to return a real PDF; call `process_scan()` directly; assert SQLite row has `status=completed` and `result_json` is a valid ATSScanResult JSON.

---

### P1: Webhook Client ⭐ MVP

**User Story:** As the Next.js app, I want to receive signed webhook notifications so that I can update Supabase with the scan status without polling FastAPI.

**Why P1:** The entire async sync architecture depends on webhooks. Without them Next.js/Supabase will never update.

**Acceptance Criteria:**

1. WHEN FastAPI sends a webhook THEN the request SHALL include an `X-Webhook-Signature: sha256=<hex>` header computed as `HMAC-SHA256(request_body_bytes, WEBHOOK_SECRET)`.
2. WHEN FastAPI sends the `processing` webhook THEN the payload SHALL be `{ "scanId": "...", "status": "processing" }`.
3. WHEN FastAPI sends the `completed` webhook THEN the payload SHALL include `scanId`, `status`, `atsScore`, `jobTitleDetected`, and the full `result` object.
4. WHEN FastAPI sends the `failed` webhook THEN the payload SHALL include `scanId`, `status: "failed"`, and `failureReason`.
5. WHEN a webhook POST fails (non-2xx or network error) THEN FastAPI SHALL retry up to 3 times with exponential backoff (delays: 1s, 3s, 9s).
6. WHEN all retries are exhausted THEN FastAPI SHALL log the failure as an error and continue — the scan status in SQLite is **not** reverted.
7. WHEN a webhook for a given `scanId` and `status` has already been sent successfully THEN FastAPI SHALL NOT resend it (idempotency via `webhook_processing_sent` / `webhook_terminal_sent` columns).

**Independent Test:** Mock the Next.js webhook endpoint; call the webhook client with a completed result; assert: correct HMAC header, correct payload, single request on success; assert: 3 retries on 500 then permanent failure log.

---

### P1: Startup Recovery ⭐ MVP

**User Story:** As the ops team, I want FastAPI to automatically resume incomplete scans after a restart so that no scans are silently lost.

**Why P1:** Without this, any crash or redeploy leaves scans stuck in `pending`/`processing` forever.

**Acceptance Criteria:**

1. WHEN FastAPI starts (lifespan startup event) THEN it SHALL query SQLite for all scans with `status IN ('pending', 'processing')`.
2. WHEN incomplete scans exist THEN FastAPI SHALL log the count and re-enqueue each one via `BackgroundTasks`.
3. WHEN no incomplete scans exist THEN FastAPI SHALL log "No incomplete scans to recover" and proceed normally.
4. WHEN a recovered scan had `status=processing` (webhook_processing_sent=true) THEN the pipeline SHALL skip the `processing` webhook (already sent before crash) and continue from the S3 fetch step.

**Independent Test:** Insert a `pending` scan and a `processing` scan in SQLite; restart the app; assert both are eventually `completed` or `failed` with no manual intervention.

---

### P1: Legacy Route Removal ⭐ MVP

**User Story:** As the development team, I want to remove the legacy `/resume/analyze` routes and in-memory job store so that the codebase has no dead code and no confusing dual-API surface.

**Why P1:** The legacy routes create a false API surface; the in-memory dict causes the RAM-growth and restart-loss bugs documented in CONCERNS.md.

**Acceptance Criteria:**

1. WHEN the new service starts THEN `POST /resume/analyze` SHALL return 404 (route does not exist).
2. WHEN the new service starts THEN `GET /resume/analyze/{job_id}` SHALL return 404 (route does not exist).
3. WHEN the new service starts THEN there SHALL be no module-level `jobs: dict` in `src/main.py`.
4. WHEN the debug `print(markdown)` in the background task is encountered during review THEN it SHALL have been removed and replaced with a structured debug log.
5. WHEN linting tools (`mypy`, `black`, `isort`) are inspected in `pyproject.toml` THEN they SHALL be under `[tool.poetry.group.dev.dependencies]`, not in `[project]`.

**Independent Test:** Start the app; GET `/resume/analyze/any-id` → 404; confirm `jobs` dict is not present via code review.

---

### P2: Real LLM Agent

**User Story:** As the hiring manager reviewing ATS results, I want the agent to produce structured scores, keyword analysis, and issues so that the report page shows real actionable data.

**Why P2:** Critical for product value, but the system can technically function (pipeline runs, webhooks fire) with a stub returning zeros/empty arrays as a P1 baseline.

**Acceptance Criteria:**

1. WHEN `run_agent(markdown)` is called THEN it SHALL invoke an LLM (OpenAI or configured provider) with a structured prompt.
2. WHEN the LLM responds THEN `run_agent` SHALL return a Pydantic object with: `overall_score` (int 0–100), `category_scores` (dict), `missing_keywords` (list[str]), `found_keywords` (list[str]), `issues` (list of issue dicts with `severity` and `description`), `job_title_detected` (str or None).
3. WHEN the LLM call fails or times out THEN `run_agent` SHALL raise an exception (caught by pipeline → `status=failed`).
4. WHEN `OPENAI_API_KEY` is not set THEN the app SHALL fail fast at startup with a clear config error.

**Independent Test:** Mock OpenAI API; call `run_agent("markdown text")` → assert returned Pydantic object matches schema; all required fields present and typed correctly.

---

### P2: Deterministic cv_preview Extractor

**User Story:** As the frontend rendering the report, I want a `cv_preview` object with the candidate's basic info extracted without LLM so that the preview always renders even if LLM is slow.

**Why P2:** Enhances report quality without LLM latency/cost; deterministic = testable and reliable.

**Acceptance Criteria:**

1. WHEN `extract_cv_preview(markdown)` is called THEN it SHALL return a dict with at minimum: `name` (str or None), `contact` (list[str]), `summary` (str or None), `sections` (list with section headings).
2. WHEN the markdown has no identifiable name THEN `name` SHALL be `null` (not an error).
3. WHEN `extract_cv_preview` is called THEN it SHALL complete in < 100ms (no LLM, no network I/O).
4. WHEN the full ATSScanResult is assembled THEN `cv_preview` SHALL come from `extract_cv_preview()`, not from the LLM response.

**Independent Test:** Call `extract_cv_preview(sample_markdown)` with a real resume markdown fixture → assert dict has required keys; `name` is a string or None; runs in < 100ms.

---

### P3: Basic Automated Tests

**User Story:** As a developer, I want a test suite covering the critical paths so that I can safely refactor and CI can catch regressions.

**Why P3:** Test coverage is essential long-term but does not block the feature from functioning. `pytest` is already declared as a dev dependency.

**Acceptance Criteria:**

1. WHEN `pytest` is run THEN tests SHALL cover: `POST /scans` happy path, `POST /scans` missing auth (401), `POST /scans` duplicate scan_id (409), webhook HMAC signing correctness, `extract_cv_preview` with sample markdown.
2. WHEN tests run THEN they SHALL NOT require a real S3 endpoint, real LLM API, or a real Next.js instance (all mocked).
3. WHEN tests run THEN zero failures SHALL be the gate for merging.

**Independent Test:** `pytest --tb=short` exits with code 0.

---

## Edge Cases

- WHEN S3 returns a non-existent key (404) THEN pipeline SHALL fail the scan with `failure_reason="S3 object not found: {file_key}"`.
- WHEN the PDF has no extractable text (scanned image) THEN `extract_markdown_from_resume` raises `ValueError`; pipeline SHALL catch it and mark scan `failed`.
- WHEN the HMAC webhook signature does not match on the Next.js side, that is Next.js's concern — FastAPI only needs to sign correctly.
- WHEN `WEBHOOK_SECRET` is not set THEN FastAPI SHALL fail fast at startup with a clear config error.
- WHEN `NEXT_WEBHOOK_URL` is not set THEN FastAPI SHALL fail fast at startup.
- WHEN a background task is still running during shutdown THEN the task SHALL complete because Uvicorn/BackgroundTasks drains before exit; startup recovery handles the rare crash case.
- WHEN `scan_id` from Next.js is not a valid UUID THEN FastAPI SHALL return 422 before touching SQLite.

---

## ATSScanResult Contract

The Pydantic schema in FastAPI MUST mirror `ATSScanResult` from `mini-app-front/src/types/quiz.ts`. The canonical shape (from the plan):

```json
{
  "scan_id": "uuid",
  "overall_score": 72,
  "job_title_detected": "Engenheiro de Software",
  "category_scores": {
    "keywords": 80,
    "format": 65,
    "sections": 70,
    "experience": 75
  },
  "missing_keywords": ["Docker", "Kubernetes"],
  "found_keywords": ["Python", "FastAPI", "REST"],
  "issues": [
    { "severity": "high", "description": "Missing summary section" }
  ],
  "cv_preview": {
    "name": "João Silva",
    "contact": ["joao@email.com", "+55 11 99999-9999"],
    "summary": null,
    "sections": ["Experiência", "Formação", "Habilidades"]
  }
}
```

---

## New Environment Variables

FastAPI must support (and fail fast if required ones are absent):

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | ✅ | `X-API-Key` value expected from Next.js |
| `SQLITE_PATH` | optional | Path for SQLite file (default: `data/scans.db`) |
| `NEXT_WEBHOOK_URL` | ✅ | Full URL of Next.js webhook endpoint |
| `WEBHOOK_SECRET` | ✅ | Shared secret for HMAC-SHA256 signing |
| `S3_ENDPOINT` | ✅ | MinIO or S3-compatible endpoint URL |
| `S3_BUCKET` | ✅ | Bucket name for resume objects |
| `S3_ACCESS_KEY` | ✅ | S3 access key |
| `S3_SECRET_KEY` | ✅ | S3 secret key |
| `S3_REGION` | optional | S3 region (default: `us-east-1`) |
| `OPENAI_API_KEY` | ✅ (P2) | LLM provider key |
| `LOG_LEVEL` | optional | Already exists |
| `LOG_ENV` | optional | Already exists |

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
|---|---|---|---|
| ATS-01 | P1: Scan Registration — 202 happy path | Design | Mapped → `design.md` § HTTP routes |
| ATS-02 | P1: Scan Registration — 401 missing/invalid key | Design | Mapped → `design.md` § `verify_api_key` |
| ATS-03 | P1: Scan Registration — 422 invalid body | Design | Mapped → `design.md` § `CreateScanRequest` |
| ATS-04 | P1: Scan Registration — 409 duplicate scan_id | Design | Mapped → `design.md` § `ScanRepository` |
| ATS-05 | P1: Scan Registration — enqueue BackgroundTask | Design | Mapped → `design.md` § `create_scan` |
| ATS-06 | P1: Pipeline — SQLite status=processing on start | Design | Mapped → `design.md` § `process_scan` |
| ATS-07 | P1: Pipeline — processing webhook before S3 fetch | Design | Mapped → `design.md` § `process_scan` |
| ATS-08 | P1: Pipeline — S3 fetch with own credentials | Design | Mapped → `design.md` § `storage/s3.py` |
| ATS-09 | P1: Pipeline — markdown extraction via resume_parser | Design | Mapped → `design.md` § Code reuse |
| ATS-10 | P1: Pipeline — run_agent produces ATSScanResult | Design | Mapped → `design.md` § P1 agent stub |
| ATS-11 | P1: Pipeline — cv_preview via deterministic extractor | Design | Mapped → `design.md` § P1 cv_preview stub |
| ATS-12 | P1: Pipeline — SQLite completed + result_json | Design | Mapped → `design.md` § `mark_completed` |
| ATS-13 | P1: Pipeline — SQLite failed + failure_reason | Design | Mapped → `design.md` § Error handling |
| ATS-14 | P1: Pipeline — terminal webhook after completion | Design | Mapped → `design.md` § `process_scan` |
| ATS-15 | P1: Webhook — HMAC-SHA256 X-Webhook-Signature header | Design | Mapped → `design.md` § `webhook.py` |
| ATS-16 | P1: Webhook — processing payload shape | Design | Mapped → `design.md` § Webhook DTOs |
| ATS-17 | P1: Webhook — completed payload shape with result | Design | Mapped → `design.md` § Webhook DTOs |
| ATS-18 | P1: Webhook — failed payload shape with failureReason | Design | Mapped → `design.md` § Webhook DTOs |
| ATS-19 | P1: Webhook — retry 3x with 1s/3s/9s backoff | Design | Mapped → `design.md` § `send_webhook` |
| ATS-20 | P1: Webhook — log permanent failure, don't revert SQLite | Design | Mapped → `design.md` § Error handling |
| ATS-21 | P1: Webhook — idempotency (no resend if already sent) | Design | Mapped → `design.md` § SQLite columns |
| ATS-22 | P1: Startup Recovery — query pending/processing on start | Design | Mapped → `design.md` § Lifespan |
| ATS-23 | P1: Startup Recovery — re-enqueue each via BackgroundTasks | Design | Mapped → `design.md` § Lifespan |
| ATS-24 | P1: Startup Recovery — skip processing webhook if already sent | Design | Mapped → `design.md` § Recovery rule |
| ATS-25 | P1: Legacy Removal — /resume/analyze routes gone | Design | Mapped → `design.md` § HTTP routes |
| ATS-26 | P1: Legacy Removal — in-memory jobs dict removed | Design | Mapped → `design.md` § CONCERNS mitigations |
| ATS-27 | P1: Legacy Removal — debug print removed | Design | Mapped → `design.md` § CONCERNS mitigations |
| ATS-28 | P1: Legacy Removal — linting deps moved to dev group | Design | Mapped → `design.md` § Dependencies |
| ATS-29 | P2: LLM Agent — invoke real LLM with structured prompt | Design | Mapped → `design.md` § P2 `run_agent` |
| ATS-30 | P2: LLM Agent — return typed Pydantic ATSScanResult fields | Design | Mapped → `design.md` § `AgentResult` |
| ATS-31 | P2: LLM Agent — raise on failure (caught by pipeline) | Design | Mapped → `design.md` § Error handling |
| ATS-32 | P2: LLM Agent — fail fast if OPENAI_API_KEY absent | Design | Mapped → `design.md` § Settings |
| ATS-33 | P2: cv_preview — deterministic extraction from markdown | Design | Mapped → `design.md` § `extract_cv_preview` |
| ATS-34 | P2: cv_preview — returns null name gracefully | Design | Mapped → `design.md` § OQ-1 |
| ATS-35 | P2: cv_preview — completes < 100ms | Design | Mapped → `design.md` § P2 heuristics |
| ATS-36 | P3: Tests — pytest covers 5 critical paths | Design | Mapped → `design.md` § Testing |
| ATS-37 | P3: Tests — all external deps mocked | Design | Mapped → `design.md` § Testing |

**Design doc:** `.specs/features/ats-scan-worker/design.md`  
**Tasks doc:** `.specs/features/ats-scan-worker/tasks.md`  
**Coverage:** 37 total, 37 mapped to design, 37 mapped to tasks ✅

---

## Success Criteria

- [ ] `POST /scans` with valid key + body returns 202 and scan appears in SQLite as `pending`
- [ ] A scan started via `POST /scans` reaches `completed` in SQLite within ~30s (wall clock, real S3 + LLM)
- [ ] Next.js webhook endpoint receives a `processing` event and a `completed` or `failed` event for every scan
- [ ] Restarting FastAPI mid-scan results in the scan eventually completing (startup recovery)
- [ ] `GET /resume/analyze/{id}` returns 404 on the new build
- [ ] Zero module-level mutable state for job tracking
- [ ] `pytest` exits 0 with at least 5 passing tests covering the critical paths
