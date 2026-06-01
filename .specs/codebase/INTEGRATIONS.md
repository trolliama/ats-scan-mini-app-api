# External Integrations

## Current Integrations

### MarkItDown (document conversion)

**Service:** Microsoft MarkItDown (`markitdown[docx,pdf]`)
**Purpose:** Convert PDF/DOCX resume bytes (fetched from S3) to plain markdown text.
**Implementation:** `src/resume_parser.py`
**Configuration:** No external API keys — local library processing.
**Authentication:** N/A

```python
_converter = MarkItDown()
result = _converter.convert_stream(BytesIO(content), file_extension=ext)
```

**Supported formats:** `.pdf`, `.docx` (validated by extension before conversion).

### LangChain (declared, not active)

**Service:** LangChain Core
**Purpose:** LLM orchestration for resume analysis.
**Implementation:** `src/agent.py`
**Configuration:** Optional `OPENAI_API_KEY` in settings; no provider client wired.
**Authentication:** N/A (stub returns hardcoded string)

A `PromptTemplate` is defined but never invoked. Target: structured `AgentResult` output with 8 ATS category scores.

### structlog + stdlib logging

**Service:** Local structured logging (not external).
**Purpose:** Dev-friendly colored logs; prod JSON logs.
**Implementation:** `src/logger.py`
**Configuration:** `LOG_LEVEL`, `LOG_ENV`, `LOG_COLOR` via `.env`

### Uvicorn (ASGI server)

**Service:** Local process server.
**Purpose:** Serve FastAPI app.
**Configuration:** Command-line invocation; uvicorn loggers redirected to propagate through structlog.

### SQLite (partial — schema only)

**Service:** Local file database.
**Purpose:** Persistent scan lifecycle.
**Implementation:** `src/db/models.py`, `src/db/engine.py`
**Configuration:** `SQLITE_PATH` (default `data/scans.db`); parent directory auto-created.
**Authentication:** N/A

Repository layer and route wiring not implemented yet.

## API Surface (this service)

### Endpoints

| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| POST | `/scans` | Accept scan job from Next.js, return 202 pending | Planned |

No public read API — Next.js reads from Supabase after webhooks land.

**Authentication:** `X-API-Key` header (shared secret with Next.js)
**Content type:** `application/json`

## Declared Dependencies (not wired)

These packages are in `pyproject.toml` and settings exist in `.env.example`, but no client code is present yet.

### MinIO / S3 (boto3)

**Purpose:** Fetch resume PDFs by `bucket + fileKey` from scan job metadata.
**Planned location:** `src/storage/s3.py`
**Configuration:** `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`
**Authentication:** AWS-style credentials in FastAPI env.
**Status:** Dependency declared; no implementation.

### Next.js webhooks (httpx)

**Purpose:** Push scan lifecycle updates (`processing`, `completed`, `failed`) to Next.js.
**Planned location:** `src/scan/webhook.py`
**Configuration:** `NEXT_WEBHOOK_URL`, `WEBHOOK_SECRET`
**Authentication:** HMAC-SHA256 header `X-Webhook-Signature: sha256=<hex>`
**Status:** Schemas defined in `src/scan/schemas.py`; no HTTP client yet.

### Next.js inbound auth

**Purpose:** Protect `POST /scans` from unauthorized callers.
**Planned location:** `src/deps/api_key.py`
**Configuration:** `API_KEY` shared secret with Next.js
**Authentication:** `X-API-Key` header comparison.
**Status:** Settings field exists; no dependency/middleware yet.

## Webhooks

**Outbound:** FastAPI → Next.js at `NEXT_WEBHOOK_URL` with HMAC verification.

| Event | Payload status | Key fields |
|-------|---------------|------------|
| Processing | `"processing"` | `scanId` |
| Completed | `"completed"` | `scanId`, `atsScore`, `jobTitleDetected`, `result` |
| Failed | `"failed"` | `scanId`, `failureReason` |

Idempotency tracked in SQLite (`webhook_processing_sent`, `webhook_terminal_sent`).

**Inbound:** None. Next.js calls `POST /scans`.

## Background Jobs

**Queue system:** None — FastAPI `BackgroundTasks` (same process).

**Scan pipeline:**
- **Location:** `src/scan/service.py` — `process_scan` (planned)
- **Jobs:** S3 fetch → parse → preview → agent → webhooks
- **State:** SQLite with startup recovery for pending/processing scans

**Limitations (MVP):**
- Single-process; no horizontal scaling with shared SQLite writes
- No dead-letter queue; webhook exhaustion logs error but scan state remains terminal

## Outbound HTTP Clients

**httpx** and **boto3** are declared in dependencies. No client usage in source code yet. Planned for webhook delivery and S3 object fetch respectively.

## Configuration Reference

All integration settings are documented in `.env.example`:

| Variable | Integration |
|----------|-------------|
| `API_KEY` | Inbound auth for `/scans` |
| `SQLITE_PATH` | SQLite persistence |
| `NEXT_WEBHOOK_URL` | Outbound webhooks |
| `WEBHOOK_SECRET` | HMAC signing |
| `S3_*` | S3/MinIO object fetch |
| `OPENAI_API_KEY` | LLM provider (optional P1, required P2) |
