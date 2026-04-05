CCA Portfolio Project — demonstrates Domain 3 (Claude Code Config), Domain 4 (Prompt Engineering), and Domain 5 (Context & Reliability)

# Maintenance Request Data Extraction Pipeline

## Project Title and Description

**Maintenance Request Data Extraction Pipeline** — a chain-workflow data extraction system
that ingests tenant maintenance requests arriving in multiple unstructured formats (email
bodies, web form submissions, and scanned handwritten notes) and produces clean, validated,
structured output.

Every request is parsed into the following fields:

| Field | Type | Required |
|---|---|---|
| `name` | string | No |
| `unit_number` | string | No |
| `category` | enum: `plumbing`, `electrical`, `HVAC`, `appliance`, `structural`, `general` | Yes |
| `urgency` | enum: `emergency`, `standard`, `low` | Yes |
| `description` | string | Yes |

The system outputs both a structured JSON record and a human-readable work-order summary.
It is implemented in `maintenance_submissions.py` and is run via `python maintenance_submissions.py`.

---

## Architecture Overview

The system is a deterministic **chain workflow** — each step depends on the prior step
completing successfully. Chaining was chosen over an agentic loop because every required
step is predictable and does not need autonomous tool selection.

```
Raw Tenant Text
      |
      v
[Step 1: Extraction] --- parse_submission tool ---> Structured JSON
      |
      v
[Step 1a: Unit Number Sanitization] --- regex validation ---> Cleaned JSON
      |
      v
[Step 1b: Cross-Check] --- verify_classification tool (separate API call) ---> Pass / Fail
      |                                                                            |
      |   <--- [Retry with feedback, up to 5x] <--- Fail                           |
      |   <--- [Oscillation detection] <--- alternating urgency values             |
      |                                                                            |
      v                                                                            |
[Step 2: Summary Generation] <--- Pass --------------------------------------------
      |
      v
Human-Readable Work-Order Summary
```

**Key architectural decisions:**

- **Forced tool calls** — both `parse_submission` and `verify_classification` are invoked
  via `tool_choice`, guaranteeing structured, schema-conformant output on every call.
- **Separate cross-check context** — verification runs in a fresh API call with no prior
  conversation history, eliminating self-review bias from the extraction step.
- **Retry with feedback** — on cross-check failure, feedback is injected into a new
  extraction call, up to `MAX_RETRIES = 5`.
- **Oscillation resolution** — if urgency alternates in an A-B-A pattern across retries,
  the pipeline selects the **higher** urgency using the rank `emergency < standard < low`.
- **Unit number sanitization** — regex validation blanks out values that look like
  sentences rather than real unit identifiers (e.g., `"the one near the lobby"` → `null`).

---

## CLAUDE.md Breakdown

`CLAUDE.md` is the project-level instruction file Claude Code loads automatically at the
start of every session in this directory. It encodes the rules that keep generated code
aligned with the pipeline's architecture and coding standards.

The file is organized into four sections:

### 1. Project Overview
Declares that the project is a data extraction pipeline for maintenance requests and
specifies the three required output fields (`category`, `urgency`, `description`) with
their enum values. This anchors every generation to the correct problem domain.

### 2. Python Coding Standards
A style contract covering:
- **Naming conventions** — `snake_case` for functions, `PascalCase` for classes,
  `UPPER_SNAKE_CASE` for constants, `_leading_underscore` for private helpers, predicate
  names for booleans (`is_valid`, `has_header`), and domain-specific prefixes
  (`extract_<entity>_from_<source>`, `transform_<entity>`, `load_<entity>_to_<dest>`).
- **Type hinting** — mandatory hints on all signatures, lowercase generics
  (`list[str]`, `dict[str, Any]`), `pathlib.Path` over `str`, `T | None` over `Optional[T]`,
  `TypedDict`/`dataclass` over raw dicts.
- **Error handling** — no bare `except`, specific exception types, a custom
  `ExtractionError` base, fail-fast on config errors, per-row error collection for batch
  jobs, never swallow with `pass`.
- **Docstrings** — Google-style with `Args:`, `Returns:`, `Raises:` sections.
- **Project structure** — one module per data source, separation of extract/transform,
  shared schemas in `models.py`, constants in `constants.py`.
- **Data handling** — all output validated as JSON.
- **Logging** — use the `logging` module (never `print`), with INFO/WARNING/ERROR levels
  that always include source file and record identifier.
- **Testing** — pytest, fixtures in `tests/fixtures/`, assertions on output shape.

### 3. Architecture Rules
Four hard rules that override any default model behavior:
- On urgency oscillation during retry, **always choose the higher-emergency value**.
- Never fabricate, invent, or hallucinate data.
- Every result must be backed by the actual maintenance request content.
- Never modify tool schemas, tools, or functions without approval.

## Permission Model

Permissions are declared in `.claude/settings.local.json` and define exactly what
Claude Code is allowed to do in this project without prompting. Three lists are used:

### `allow` — auto-approved
```json
"Bash(pip install:*)"
"Bash(python maintenance_submissions.py)"
```
Dependency installation and running the pipeline are pre-approved because they are the
day-to-day loop for this project and carry no destructive side-effects.

### `deny` — hard-blocked
```json
"Write(tool_schemas/*.py)"
"Write(system_prompts/*.py)"
"Write(.env)"
```
These match the CLAUDE.md architecture rule that tool schemas and system prompts must
never be modified without approval, plus a safety block on overwriting `.env` (which
contains the `ANTHROPIC_API_KEY`). Denies are absolute — they cannot be overridden
in-session.

### `ask` — prompt before running
```json
"Execute(*.sh)"
"Write(config/*)"
```
Shell scripts and writes to `config/` are gated behind an explicit user confirmation. They
are not blocked outright (since they may be legitimate), but they are never silent.

This three-tier model (**allow / ask / deny**) encodes the project's trust boundaries:
routine loop operations run freely, sensitive areas prompt, and invariants are locked.

---

## Custom `/review` Command

The project ships a custom slash command at `.claude/commands/review.md`. Invoking
`/review` in Claude Code expands to a prompt that asks the model to review all Python
files in the project and produce a structured report with three sections:

### 1. Code Correctness
- Are functions missing error handling for bad input?
- Are API calls wrapped in `try`/`except` blocks?
- Are retry loops working correctly?
- Does the validation logic actually catch invalid JSON responses?

### 2. Security
- Any sensitive data exposed (API keys, usernames, passwords)?
- Are names and unit numbers being printed to the console or logged anywhere?

### 3. Architecture Integrity
- Are all required fields present?
- Is data returned as JSON?
- When urgency oscillation is detected, is the higher urgency selected?
- Is cross-check validation using a **separate** Claude instance with a clean context
  (not reusing the same conversation)?

The command instructs Claude to format output as a human-readable report with severity
labels **CRITICAL**, **WARNING**, or **INFO** per finding. This mirrors the architecture
rules in `CLAUDE.md` and gives the project a repeatable, one-keystroke audit tied directly
to its invariants.

---

## PostToolUse Hook

A `PostToolUse` hook is registered in `.claude/settings.local.json` under `hooks`:

```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Write",
      "hooks": [
        {
          "type": "command",
          "command": "pylint $FILE --output-format=text"
        }
      ]
    }
  ]
}
```

**How it works:**
- **Event** — `PostToolUse` fires immediately after a tool call completes.
- **Matcher** — `"Write"` scopes the hook to only the `Write` tool (file creation /
  full-file rewrites). `Edit` operations don't trigger it.
- **Action** — the harness runs `pylint $FILE --output-format=text` where `$FILE` is the
  path that was just written, and feeds the output back into the conversation.

**Why this matters:** every file Claude writes is lint-checked automatically against the
coding standards declared in `CLAUDE.md` (naming conventions, type hints, docstrings, etc.)
without the user having to ask. Lint violations surface in the next turn so Claude can
correct them before the user reviews anything. The hook is the enforcement mechanism that
closes the loop between "standards documented in CLAUDE.md" and "standards actually
applied to generated code."

---

## CCA Domain Mapping

Each feature of this project maps to a specific Claude Certified Associate (CCA) domain
concept. The mapping below ties what is in the repo to what it demonstrates.

### Domain 4 — API & Structured Tool Use
Implemented inside `maintenance_submissions.py`.

| CCA Concept | Where It Appears |
|---|---|
| `tool_choice` forcing | `_call_extraction` and `_cross_check` both pass `tool_choice={"type": "tool", "name": ...}` to guarantee a structured tool call on every request |
| Tool schemas for guaranteed output format | `parse_submission_tool` and `verify_classification_tool` define `input_schema` with enum constraints on `category` and `urgency` |
| XML tags in system prompts | `SYSTEM_PROMPT` uses `<instructions>`, `<rules>`, `<category>`, `<urgency>`, `<examples>`, `<constraints>` as structural boundaries |
| Self-review bias resolved via separate API call | `_cross_check` opens a fresh request with no prior message history, passing only the fields to be audited |
| Few-shot examples | Four examples inside `<examples>` cover multi-line, short, single-line, and messy/vague submissions |
| Semantic validation & retry with feedback | `extract_submission` runs up to `MAX_RETRIES = 5` cross-checks, injecting feedback into the next extraction call |
| Oscillation detection | A-B-A pattern detection on `urgency_history` with automatic escalation to the higher-urgency value using `urgency_rank` |

### Claude Code Harness Domain — Project Configuration & Agent Control
Implemented outside the Python code, in the Claude Code control surface.

| CCA Concept | Where It Appears |
|---|---|
| Project-level instructions (`CLAUDE.md`) | Encodes project overview, coding standards, and architecture rules loaded automatically every session |
| Permission model (allow / ask / deny) | `.claude/settings.local.json` with pre-approved pipeline commands, gated config writes, and locked tool schemas / `.env` |
| Custom slash commands | `.claude/commands/review.md` provides a repeatable `/review` audit tied to the architecture rules |
| Lifecycle hooks | `PostToolUse` hook runs `pylint` on every `Write` to enforce the CLAUDE.md coding standards automatically |

Together, the Domain 4 concepts define **what** the pipeline does, and the Harness
concepts define **how** Claude Code is constrained while building and maintaining it.

---

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your Anthropic API key:

```
ANTHROPIC_API_KEY=your-api-key-here
```

## Usage

```bash
python maintenance_submissions.py
```
