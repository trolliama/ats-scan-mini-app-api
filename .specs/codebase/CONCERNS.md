# Codebase Concerns

**Analysis Date:** 2026-05-31

## Tech Debt

**ScanRepository stub with failing tests:**

- Issue: `src/db/scan_repository.py` is `class ScanRepository: pass` but `tests/integration/test_scan_repository.py` imports `ScanCreate`, `DuplicateScanError`, and 8 lifecycle tests.
- Files: `src/db/scan_repository.py`, `tests/integration/test_scan_repository.py`
- Why: TDD — tests written before implementation.
- Impact: `poetry run pytest tests/integration/` fails on import; gate blocked for downstream tasks.
- Fix approach: Implement repository per `.specs/features/ats-scan-worker/design.md` § ScanRepository.

**Agent is a non-functional stub:**

- Issue: LangChain prompt defined but `run_agent()` returns hardcoded string; no LLM call.
- Files: `src/agent.py`
- Why: Placeholder while persistence layer was prioritized.
- Impact: Scan pipeline will complete without real analysis until wired.
- Fix approach: Change signature to `run_agent(markdown: str) -> AgentResult`; wire provider in P2.

**Dual lockfiles:**

- Issue: Both `poetry.lock` and `uv.lock` present; `pyproject.toml` uses Poetry format.
- Files: `poetry.lock`, `uv.lock`, `pyproject.toml`
- Why: Possible uv experimentation alongside Poetry.
- Impact: Dependency drift if only one lockfile is maintained.
- Fix approach: Pick one package manager and remove the other lockfile.

## Security Considerations

**API key auth not wired:**

- Risk: `POST /scans` will be unprotected until `deps/api_key.py` is implemented.
- Files: `src/config.py` (settings exist), route not yet implemented
- Current mitigation: No route exposed yet.
- Recommendations: Implement `X-API-Key` dependency before exposing endpoint.

**Webhook secret in env:**

- Risk: `WEBHOOK_SECRET` must be shared with Next.js; leakage enables forged lifecycle events.
- Files: `src/config.py`, `.env.example`
- Current mitigation: Secret in `.env` (gitignored).
- Recommendations: Rotate on compromise; constant-time HMAC comparison when webhook client is implemented.

**PII in logs:**

- Risk: Resume markdown must not appear in structured logs at INFO level.
- Files: `src/logger.py`, planned `scan/service.py`
- Current mitigation: Parser and logger do not log content today.
- Recommendations: Log byte length only; never log extracted markdown at INFO (ATS-27 in tasks).

## Performance Bottlenecks

**Synchronous parsing in background task:**

- Problem: MarkItDown conversion is CPU-bound; will block the background thread pool inside `process_scan`.
- Files: `src/resume_parser.py`
- Measurement: Not profiled — likely seconds for large PDFs.
- Improvement path: Run `extract_markdown_from_resume` in `asyncio.to_thread()` or dedicated worker process.

**SQLite single-writer:**

- Problem: File-based SQLite — no horizontal scaling for concurrent writes.
- Files: `src/db/engine.py`
- Current mitigation: Acceptable for MVP single-process worker.
- Improvement path: External store if multi-instance deployment needed.

## Fragile Areas

**MarkItDown singleton:**

- Files: `src/resume_parser.py` (`_converter = MarkItDown()`)
- Why fragile: Library behavior varies by file type; empty extraction raises generic `ValueError`.
- Common failures: Scanned PDFs with no OCR may return empty text → "Could not extract text from resume".
- Safe modification: Add format-specific error messages; consider fallback OCR.
- Test coverage: None.

**Repository contract enforced only by tests:**

- Files: `tests/integration/test_scan_repository.py`, `src/db/scan_repository.py`
- Why fragile: Implementation gap means CI gate fails once added.
- Safe modification: Implement repository atomically with passing tests.
- Test coverage: Tests exist; implementation missing.

## Scaling Limits

**Single-process SQLite worker:**

- Current capacity: One Uvicorn worker; SQLite single-writer.
- Limit: No horizontal scaling without external store.
- Symptoms at limit: Write contention or inconsistent state across multiple instances.
- Scaling path: External store (Postgres/Redis), dedicated worker queue.

## Dependencies at Risk

**Python 3.14.5 minimum:**

- Risk: Very new Python version — limited deployment image availability and ecosystem compatibility.
- Impact: CI/CD and hosting may not offer 3.14 yet.
- Migration plan: Verify target deployment supports 3.14; consider relaxing to 3.12+ if needed.

**LangChain major version:**

- Risk: LangChain 1.x API differs from 0.x; rapid ecosystem changes.
- Impact: Agent implementation may require pattern updates.
- Migration plan: Pin provider packages explicitly when wiring LLM; follow LangChain 1.x docs.

## Missing Critical Features

**ScanRepository implementation:**

- Problem: Tests define contract; class is empty stub.
- Blocks: Service layer, routes, recovery, webhooks.
- Implementation complexity: Medium (design fully specified).

**S3 fetch and webhook clients:**

- Problem: boto3 and httpx declared but no client modules.
- Blocks: End-to-end scan pipeline.
- Implementation complexity: Low–medium per task definitions.

**POST /scans route and process_scan pipeline:**

- Problem: No HTTP entry point or orchestration service yet.
- Blocks: Integration with Next.js.
- Implementation complexity: Medium (design fully specified in tasks).

**Real LLM analysis:**

- Problem: Agent returns placeholder text.
- Blocks: Product value delivery (P2).
- Implementation complexity: Medium–high (provider setup, prompt engineering, output schema).

**Startup recovery:**

- Problem: Lifespan not implemented; pending/processing scans not re-enqueued on restart.
- Blocks: Production reliability.
- Implementation complexity: Low–medium.

## Test Coverage Gaps

**ScanRepository (tests exist, impl missing):**

- What's not tested: Nothing runs — import fails.
- Priority: Critical (current sprint)
- Difficulty to test: Implementation task; tests already written.

**HTTP route validation (`POST /scans`):**

- What's not tested: 202 happy path, 401 missing key, 409 duplicate, 422 invalid body.
- Priority: High
- Difficulty to test: Low — FastAPI `TestClient` with dependency overrides.

**Resume parser edge cases:**

- What's not tested: Empty PDF, corrupt file, missing extension, `.docx` vs `.pdf` paths.
- Priority: Medium
- Difficulty to test: Low — pure functions with fixture bytes.

**Scan pipeline state transitions:**

- What's not tested: pending → processing → completed/failed flow with webhook idempotency.
- Priority: High
- Difficulty to test: Medium — mock S3/agent/webhook.

**No CI pipeline:**

- What's not tested: Automated gate on every change.
- Priority: Medium
- Difficulty to test: Low — add GitHub Actions with `poetry install && poetry run pytest`.

---

_Concerns audit: 2026-05-31_
_Update as issues are fixed or new ones discovered_
