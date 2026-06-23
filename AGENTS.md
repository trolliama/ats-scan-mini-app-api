# Agent Guidelines

Conventions and design principles for AI agents. Project-specific details live in linked docs and a short **Project-specific conventions** subsection where needed.

---

## Testing

We follow the **classical (Detroit) school** of testing — not the London (mockist) school.

| | Classical | London (avoid for integration tests) |
|---|---|---|
| **Goal** | Verify behaviour through real collaborators | Verify behaviour by replacing collaborators with test doubles |
| **Doubles** | Only at true system boundaries (network, storage, clock) | At every module boundary, including internal collaborators |
| **Integration tests** | Exercise real code paths that compose across modules | Stub the orchestrator's dependencies and test wiring in isolation |
| **Confidence** | A passing test means the parts actually work together | A passing test only means the orchestrator invoked the expected doubles |

### Integration tests must stay close to reality

An integration test verifies that **multiple real modules compose correctly** — not that one unit called another unit you replaced with a stub.

**The core problem:** when you stub dependencies *on the orchestrator* (the function or class that coordinates the workflow), every module it imports is bypassed. The HTTP client, storage adapter, and parser never run. The test can pass even when signing, serialization, error mapping, or retry logic are broken — because that code was never executed.

```
// Bad — doubles on the orchestrator; infrastructure never runs
stub(orchestrator.fetchRemoteData).returns(cannedBytes)
stub(orchestrator.parseDocument).returns(cannedText)
stub(orchestrator.notifyDownstream).returns(success)

orchestrator.runJob(id)

// only the orchestrator's control flow was tested
```

```
// Good — real modules; only external systems are faked
fakeStorage.seed(fixtureFile)
fakeHttpServer.acceptPosts()

orchestrator.runJob(id)

assert fakeHttpServer.receivedCount == 2   // real client built the request
assert db.readRow(id).status == "completed" // independent verification path
```

In the good example, the storage adapter, parser, and notification client all execute real code. Only the **external systems they talk to** are replaced.

### Where to fake vs. what to run real

| Layer | Integration test | Unit test |
|---|---|---|
| Database / persistence | Real (in-process or in-memory) | Not used, or mocked |
| Domain logic and orchestration | Real | Real (single unit under test) |
| Infrastructure adapters (HTTP, storage, messaging) | **Real** | Real or isolated |
| External systems (remote APIs, cloud services, filesystem) | Fake at the boundary | Fake at the boundary |
| Slow or non-deterministic third parties | Stub or fixture | Stub |

**Rule of thumb:** do not stub functions imported into the unit under test. Replace the **transport** the adapter uses (HTTP server fake, in-memory storage, fixture file on disk) so the adapter's own logic still runs.

Unit tests are the place to isolate a single module with finer-grained doubles when testing one concern (retry policy, error translation, edge cases). Integration tests should trust that those modules work and focus on **composition**.

### Verification

Do not round-trip through the component under test. When exercising write path A, assert the outcome via an independent read path B — not another method on the same class that shares the same implementation bugs.

Example: after `repository.insert(record)`, verify with a raw query or a separate test helper — not `repository.getById()`, unless `getById` itself is what you are testing.

### Key rules

- Name tests by outcome first: `test_<behaviour>_when_<context>`
- One-line docstring per test stating what must hold, not how the test is wired
- Build test data via factories or builders — not ad-hoc inline assembly
- Integration tests: real collaborators + boundary fakes; never stub the orchestrator's imports

### Project-specific conventions

This repo uses pytest, Factory Boy, and a TDD skill. For fixtures, factory usage, gate commands, and directory layout see [`.specs/codebase/TESTING.md`](.specs/codebase/TESTING.md). When creating tests here, use the TDD skill at [`.cursor/skills/tdd`](.cursor/skills/tdd).

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
│   Rich, Hidden       │  ← sessions, retries, persistence, encoding…
│   Implementation     │
│                      │
└──────────────────────┘
```

A **shallow module** is the opposite — large interface, thin implementation. It forces callers to manage complexity that the module should absorb.

```
// Bad — shallow: caller manages mechanism
save(connection, tableName, rowMap, conflictColumn)

// Good — deep: caller supplies domain intent
insertPending(order)
```

When designing a module, ask:

- Can I reduce the number of methods or parameters?
- Can I move complexity from the caller into the implementation?
- Does calling this feel simple from the outside?

**Warning signs of a shallow module:**

- A wrapper that does nothing but delegate to another function
- Parameters that expose internal mechanism (connection handles, table names, raw encodings)
- Callers that always invoke two or three methods in the same fixed sequence — that sequence should be one method
- A type whose methods are one-to-one with its fields (a struct with no behaviour)

### Naming

Good names communicate **purpose and behaviour**, not type or mechanism.

A name should make the reader slightly smarter about what the code does — if the name requires a comment to explain it, the name is wrong.

```
// Bad — what is "d"? what does "proc" mean?
proc(d)

// Good — intent is clear without reading the body
processOrder(orderId)
```

Additional naming rules:

- **Be specific, not generic.** Names like `Manager`, `Handler`, `Helper`, `Utils`, `Data` describe nothing. Name the domain concept instead (`NotificationClient`, `DocumentParser`).
- **Be consistent.** If one operation is `getById`, the next is not `fetchByOrderId` or `load`. Pick a verb and stay with it across the module.
- **Booleans read as assertions.** Prefer `isComplete`, `hasFailed`, `shouldRetry` over bare `complete` or `flag`.
- **Avoid type encodings in the name.** `orderList`, `orderMap`, `orderStr` — the type system already carries that information.

Follow the project's established casing and file-naming conventions; do not invent a parallel style.

### Reducing Cognitive Load

Every piece of information a caller must hold in their head to use a module is cognitive load. Abstractions that **hide information** reduce that load.

Techniques:

- **Encapsulate decisions** — if the caller must choose a format, a strategy, or an encoding, pull that decision into the module
- **Provide sensible defaults** — callers should only supply what varies
- **Keep coupling low** — a change inside a module should not ripple to its callers

```
// Bad — caller must know encoding, content-type, and retries
send(url, bodyBytes, contentType, retries)

// Good — caller supplies domain intent; module handles the rest
sendNotification(orderId, result)
```

### General Purpose vs Special Purpose

Prefer **slightly general-purpose** interfaces over purpose-built ones. A general-purpose module is easier to reuse, easier to test, and its interface ends up being simpler because it isn't entangled with one caller's assumptions.

The test: "could this module serve a second, slightly different caller without changing its interface?" If yes, it is general enough. If no, it is probably too tightly coupled to one use case.

**Pull complexity downwards.** When a design decision can live in the module or in the caller, it should live in the module. Callers shouldn't need to know about edge cases the module can handle itself.

```
// Bad — caller must know that lookup returns null and handle it
order = repo.getById(id)
if order == null:
    respondNotFound()

// Good — module raises a domain error; the transport layer maps it once
order = repo.getByIdOrRaise(id)  // throws NotFound internally
```

### Designing Errors

Errors are part of the interface. A messy error design makes every caller more complex.

**1. Design errors out of existence.**
The best way to handle an error is to make the condition unrepresentable or return a neutral value when absence is expected.

```
// Bad — callers must guard against null everywhere
getById(id) -> Entity | null

// Good — absence is not an error for this operation
listIncomplete() -> List<Entity>   // empty list, not null
```

**2. Mask exceptions.**
Detect and handle errors at the lowest level where you have enough context, then translate to domain errors. Callers should not see vendor-specific failures.

```
// Bad — leaks storage SDK errors to callers
download(key)  // throws VendorClientError

// Good — translate at the boundary
download(key)  // throws DocumentNotFound(key) wrapping vendor error
```

**3. Exception aggregation.**
Handle failures of a given scope in one place. In background jobs, a single top-level handler catches everything, records failure state, notifies downstream, and logs with full context — individual steps do not each define recovery policy.

```
// Good — one handler for all background job failures
runJob(id):
    try:
        ...
    catch (any):
        log.exception("job failed", id)
        repo.markFailed(id, reason)
        notifier.sendFailed(id)
```

### Project-specific conventions

For naming tables, file layout, and language-specific style in this repo see [`.specs/codebase/CONVENTIONS.md`](.specs/codebase/CONVENTIONS.md).

---

## Comments & Documentation

> Also rooted in _A Philosophy of Software Design_ — Ousterhout.

**The primary goal of a comment is to convey _what_ is happening and _why_ — not _how_.**
The code already shows how. A comment that restates the code in prose adds noise, not signal.

```
// Bad — restates the code
id = generateUuid()  // generate a UUID

// Good — explains intent the code cannot show
id = generateUuid()  // string PK to match the identifier stored by the upstream client
```

### When to Comment

Write a comment only when **the information is not already obvious from the code**. If a reader with domain knowledge can understand the code in a few seconds, no comment is needed.

Write a comment when:

- The reason for a decision would surprise a future reader
- A non-obvious constraint or invariant must hold
- The behaviour of a unit is richer than its signature or type implies

### Categories of Comments

**Interface comments** — the most important kind. Document the unit's contract: what it does, its inputs, what it returns, and what can go wrong. A caller must be able to use it correctly by reading only this comment.

**Data member comments** — document fields that carry non-obvious meaning. The type alone is rarely enough when there are invariants, formats, or domain constraints attached.

```
class JobRecord {
    score: int       // 0–100; -1 means scoring failed
    notified: bool   // true once terminal notification delivered; prevents duplicates
}
```

**Implementation comments** — explain _why_, not _what_. Use inside function bodies only when the logic is genuinely surprising or fragile.

```
// Retry once: transient latency spikes are common immediately after upload
for attempt in 0..1:
    ...
```

**Cross-module comments** — document coupling between packages. Place a NOTE at the top of a file or in the module doc when a design decision spans modules and would be invisible to a reader looking at only one.

```
// NOTE: This module must not import from persistence — dependency is
// domain → persistence, not the reverse. Keep it that way.
```

### Comments as Abstraction

A good interface comment does for the reader what a deep module does for the caller: it hides implementation details and provides a higher-level model of the behaviour. A caller who reads only the documentation should be able to use the unit correctly without reading its body.

**Precision and intuition serve different levels:**

- **Intuition** (higher level): "Parse the document and return structured text" — mental model without detail. Best for public API docs.
- **Precision** (lower level): "Throws ParseError if the file is password-protected" — exact, actionable, matters for callers. Include when the detail affects correct usage or error handling.

Use precision where it changes caller behaviour; use intuition everywhere else.

### Documentation Format

Use **one consistent documentation style** across the project — whatever the language's idiomatic form is (docstrings, JSDoc, JavaDoc, XML comments). Match what existing code in the repo already uses.

Every public unit should document:

- **Purpose** — what it does, in one sentence
- **Inputs and outputs** — including units, formats, and valid ranges where non-obvious
- **Errors** — what can fail and under what conditions
- **Invariants** — constraints the caller must uphold or can rely on

Keep module-level docs for non-obvious packages: what belongs here, what must not be imported from elsewhere, and the abstraction boundary the package enforces.

Inline comments are for implementation-level notes only — use sparingly.

### What Not to Comment

Some comments are actively harmful because they create noise that readers learn to skip.

**Never comment:**

- Code that is self-explanatory from its name and types
- Commented-out code — delete it; version control exists for a reason
- What a function does when the name already says it
- TODOs without an owner or a ticket — turn them into tracked issues

```
// Bad — all noise
getOrder(id):
    // get the order from the repository
    order = repo.getById(id)
    // return it
    return order

// Good — no comment needed
getOrder(id):
    return repo.getById(id)
```

### What Makes a Good Comment

1. **Adds information the code cannot.** Explains intent, not mechanics.
2. **Written at a higher level of abstraction than the code it describes.** Elevates the reader's mental model.
3. **Precise where precision matters.** Exact constraints, error conditions, and invariants stated exactly.
4. **Short.** One to three sentences is almost always enough for a public API doc.
5. **Kept up to date.** A wrong comment is worse than no comment — it actively misleads. When code changes, update its comments.

### Project-specific conventions

This repo uses Google-style Python docstrings. For examples and formatting rules see [`.specs/codebase/CONVENTIONS.md`](.specs/codebase/CONVENTIONS.md).
