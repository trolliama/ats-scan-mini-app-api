# Agent Guidelines

Conventions and design principles for AI agents working on this codebase.

---

## Testing

This project uses **pytest** for unit and integration tests, with **Factory Boy** for test data.

Key rules at a glance:

- Test function names: `test_<behaviour>_when_<context>` (behaviour first)
- Every test function requires a one-line docstring stating the expected outcome
- Never round-trip through the component under test — verify side effects via an independent path (e.g. raw SQL, not another method on the same class)
- Build test data via factories in `tests/factories/`, never inline dict assembly

A well-structured integration test looks like this:

```python
class TestScanRepository:
    def test_persists_retrievable_scan_when_insert_pending(
        self, db_session: Session
    ) -> None:
        """Inserting a pending scan persists input fields and default lifecycle values."""
        scan = ScanCreateFactory.build()

        ScanRepository(db_session).insert_pending(scan)

        row = _fetch_scan(db_session, scan.id)  # raw SQL — not repo.get_by_id
        assert row["status"] == "pending"
        assert row["file_key"] == scan.file_key
```

Note the separation: factory builds the data, repository exercises the behaviour, raw SQL verifies the result.

For the full testing spec (fixtures, factory usage, coverage matrix, gate commands) see [`.specs/codebase/TESTING.md`](.specs/codebase/TESTING.md).

### SKILL

Whenever creating a test you must use the tdd skill located on [`.cursor/skills/tdd`](.cursor/skills/tdd)

---

## Code Design

> Rooted in _A Philosophy of Software Design_ — Ousterhout.

The single most important goal: **reduce cognitive load for the next developer**.

### Deep Modules vs Shallow Modules

A **deep module** hides a large, complex implementation behind a small, simple interface. That gap between interface and implementation is where value lives.

```
┌──────────────────────┐
│    Small Interface   │  ← few methods, simple params
├──────────────────────┤
│                      │
│   Rich, Hidden       │  ← sessions, retries, SQL, encoding…
│   Implementation     │
│                      │
└──────────────────────┘
```

A **shallow module** is the opposite — large interface, thin implementation. It forces callers to manage complexity that the module should absorb.

```python
# Bad — shallow: caller manages all the details
def save(engine, table_name, row_dict, conflict_column):
    ...

# Good — deep: caller just supplies domain objects
def insert_pending(scan: ScanCreate) -> None:
    ...
```

When designing a module, ask:

- Can I reduce the number of methods or parameters?
- Can I move complexity from the caller into the implementation?
- Does calling this feel simple from the outside?

**Warning signs of a shallow module:**

- A wrapper that does nothing but delegate to another function
- Parameters that expose internal mechanism (engine, table name, session)
- Callers that always call two or three methods in the same fixed sequence — that sequence should be one method
- A class whose methods are one-to-one with its fields (glorified struct with no behaviour)

### Naming

Good names communicate **purpose and behaviour**, not type or mechanism.

| Layer               | Convention                     | Example                                              |
| ------------------- | ------------------------------ | ---------------------------------------------------- |
| Files / modules     | `snake_case`                   | `scan_repository.py`                                 |
| Functions / methods | `snake_case`, verb-led         | `insert_pending()`, `extract_markdown_from_resume()` |
| Variables           | `snake_case`, intent-revealing | `scan_id`, `file_key`                                |
| Constants           | `UPPER_SNAKE_CASE`             | `SUPPORTED_EXTENSIONS`                               |
| Classes / models    | `PascalCase`                   | `ScanCreate`, `ATSScanResult`                        |
| Exceptions          | `PascalCase` + `Error` suffix  | `DuplicateScanError`                                 |

A name should make the reader slightly smarter about what the code does — if the name requires a comment to explain it, the name is wrong.

```python
# Bad — what is "d"? what does "proc" mean?
def proc(d):
    ...

# Good — intent is clear without needing to read the body
def process_scan(scan_id: str) -> None:
    ...
```

Additional naming rules:

- **Be specific, not generic.** `manager`, `handler`, `helper`, `utils`, `data` are almost always wrong — they describe nothing. Name the domain concept instead (`WebhookClient`, `ResumeParser`).
- **Be consistent.** If one function is `get_by_id`, the next one is not `fetch_by_scan_id` or `load`. Pick a verb and stay with it across the module.
- **Booleans read as assertions.** Prefix with `is_`, `has_`, or `should_`: `is_complete`, `has_failed`, `should_retry`.
- **Avoid encodings in the name.** `scan_list`, `scan_dict`, `scan_str` — the type annotation already carries that information.

### Reducing Cognitive Load

Every piece of information a caller must hold in their head to use a module is cognitive load. Abstractions that **hide information** reduce that load.

Techniques:

- **Encapsulate decisions** — if the caller must choose a format, a strategy, or an encoding, pull that decision into the module
- **Provide sensible defaults** — callers should only supply what varies
- **Keep coupling low** — a change inside a module should not ripple to its callers

```python
# Bad — caller must know about encoding, content-type, and retries
def send(url, body_bytes, content_type, retries):
    ...

# Good — caller supplies domain intent; module handles the rest
def send_webhook(scan_id: str, result: ATSScanResult) -> None:
    ...
```

### General Purpose vs Special Purpose

Prefer **slightly general-purpose** interfaces over purpose-built ones. A general-purpose module is easier to reuse, easier to test, and its interface ends up being simpler because it isn't entangled with one caller's assumptions.

The test: "could this module serve a second, slightly different caller without changing its interface?" If yes, it is general enough. If no, it is probably too tightly coupled to one use case.

**Pull complexity downwards.** When a design decision can live in the module or in the caller, it should live in the module. Callers shouldn't need to know about edge cases the module can handle itself.

```python
# Bad — caller must know that get_by_id returns None and handle it
scan = repo.get_by_id(scan_id)
if scan is None:
    raise HTTPException(status_code=404)

# Good — module raises a domain exception; HTTP layer maps it once
scan = repo.get_by_id_or_raise(scan_id)  # raises ScanNotFound internally
```

### Designing Errors

Errors are part of the interface. A messy error design makes every caller more complex.

**1. Design errors out of existence.**
The best way to handle an exception is to not throw one. Redesign the API so the error condition cannot occur.

```python
# Bad — callers must guard against None everywhere
def get_by_id(scan_id: str) -> Scan | None: ...

# Good — return a neutral value when absence is expected behaviour
def list_incomplete() -> list[Scan]: ...  # returns [] instead of None
```

**2. Mask exceptions.**
Detect and handle errors at the lowest level where you have enough context, so callers never see them.

```python
# Bad — leaks S3-specific errors into the caller
def download(key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()  # raises ClientError

# Good — translate to a domain error at the boundary
def download(key: str) -> bytes:
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        raise ResumeNotFoundError(key) from exc
```

**3. Exception aggregation.**
Handle all exceptions of a given class in one place. In background tasks, a single top-level `except Exception` catches everything, marks the scan failed, and logs with full traceback — callers never see raw exceptions.

```python
# Good — one handler for all background task failures
async def process_scan(scan_id: str) -> None:
    try:
        ...
    except Exception:
        logger.exception("Scan failed", scan_id=scan_id)
        await repo.mark_failed(scan_id, reason=str(exc))
        await webhook.send_failed(scan_id)
```

For the full naming and code organisation conventions see [`.specs/codebase/CONVENTIONS.md`](.specs/codebase/CONVENTIONS.md).

---

## Comments & Documentation

> Also rooted in _A Philosophy of Software Design_ — Ousterhout.

**The primary goal of a comment is to convey _what_ is happening and _why_ — not _how_.**
The code already shows how. A comment that just re-states the code in English adds noise, not signal.

```python
# Bad — restates the code
scan_id = str(uuid4())  # generate a UUID and convert it to string

# Good — explains intent that the code cannot show
scan_id = str(uuid4())  # use string PK to match the value stored by the Next.js frontend
```

### When to Comment

Write a comment only when **the information is not already obvious from the code**. If a reader with domain knowledge can understand the code in a few seconds, no comment is needed.

Write a comment when:

- The reason for a decision would surprise a future reader
- A non-obvious constraint or invariant must hold
- The behaviour of a function is richer than its signature implies

### Categories of Comments

**Interface comments** — the most important kind. Document the function's contract: what it does, its parameters, what it returns, and what can go wrong. A caller must be able to use the function correctly by reading only this comment.

**Data structure member comments** — document fields that carry non-obvious meaning. The type alone is rarely enough when there are invariants, formats, or domain constraints attached.

```python
class Scan(Base):
    overall_score: Mapped[int]  # ATS score 0–100; -1 means scoring failed
    webhook_sent: Mapped[bool]  # True once terminal webhook delivered; prevents duplicate delivery
```

**Implementation comments** — explain _why_, not _what_. Go inside function bodies only when the logic is genuinely surprising or fragile.

```python
# Retry once: transient S3 latency spikes are common in the first 200ms after upload
for attempt in range(2):
    ...
```

**Cross-module comments** — document coupling between packages. Use a `# NOTE:` block at the top of the file or in the module docstring when a design decision spans two or more modules and would be invisible to a reader looking at only one.

```python
# NOTE: This module must not import from src.scan — the dependency arrow
# is scan → db, not the other way around. Keep it that way.
```

### Comments as Abstraction

A good interface comment does for the reader what a deep module does for the caller: it hides implementation details and provides a higher-level model of the behaviour. A caller who reads only the docstring should be able to use the function correctly without reading its body.

This is why **precision and intuition serve different levels**:

- **Intuition comments** (higher level): "Parse the resume and return structured markdown" — gives the reader a mental model without burying them in detail. Best for function and class docstrings.
- **Precision comments** (lower level): "Raises `ResumeParseError` if the file is password-protected" — exact, actionable, matters for callers. Include these when the detail affects correct usage or error handling.

Use precision where it changes caller behaviour; use intuition everywhere else.

### Python Docstring Format

Use **Google-style docstrings** consistently across files, classes, methods, and functions.

**Module docstring** (file-level, optional but valuable for non-obvious modules):

```python
"""Structured logging configuration.

Configures structlog with JSON output in production and a coloured
console renderer in development. Import `get_logger` from here; do not
configure structlog directly in other modules.
"""
```

**Function / method docstring:**

```python
def extract_markdown_from_resume(content: bytes, filename: str) -> str:
    """Convert a PDF or DOCX resume to plain Markdown.

    Args:
        content: Raw file bytes.
        filename: Original filename used to detect format by extension.

    Returns:
        Markdown string with headings and bullet points preserved.

    Raises:
        ResumeParseError: If the file format is unsupported or unreadable.
    """
```

**Class docstring** (describe the abstraction, not the constructor):

```python
class ScanRepository:
    """Persistence layer for ATS scan lifecycle.

    Wraps all SQL operations for the `scans` table. Callers work with
    domain objects (`ScanCreate`, `Scan`) and domain exceptions
    (`DuplicateScanError`, `ScanNotFound`); SQL details never leak out.
    """
```

**Inline comments** — use sparingly, only for implementation-level notes:

```python
# SQLite doesn't enforce FK constraints by default; enable per-connection
engine.execute("PRAGMA foreign_keys = ON")
```

### What Not to Comment

Some comments are actively harmful because they create noise that readers learn to skip, which means the signal-to-noise ratio of the whole file drops.

**Never comment:**

- Code that is self-explanatory from its name and types
- Commented-out code — delete it; git history exists for a reason
- What a function does when the name already says it (`# returns the scan` above `return scan`)
- TODOs without an owner or a ticket — turn them into GitHub issues

```python
# Bad — all noise
def get_scan(scan_id: str) -> Scan:
    # get the scan from the repository
    scan = self.repo.get_by_id(scan_id)
    # return it
    return scan

# Good — no comment needed; the code is already clear
def get_scan(scan_id: str) -> Scan:
    return self.repo.get_by_id(scan_id)
```

### What Makes a Good Comment

1. **Adds information the code cannot.** Explains intent, not mechanics.
2. **Written at a higher level of abstraction than the code it describes.** Elevates the reader's mental model.
3. **Precise where precision matters.** Exact parameter constraints, exception conditions, and invariants should be stated exactly.
4. **Short.** One to three sentences is almost always enough for a function docstring.
5. **Kept up to date.** A wrong comment is worse than no comment — it actively misleads. When code changes, update its comments.
