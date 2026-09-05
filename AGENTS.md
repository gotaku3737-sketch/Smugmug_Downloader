# Multi-Agent Coordination Guidelines & Instructions

This document provides system instructions, invariant security rules, specialized agent roles, and task delegation templates for autonomous agents collaborating on the **SmugMug Gallery Downloader** codebase.

---

## 1. Repository Ground Rules & Invariants (All Agents)

All agents operating in this repository must strictly adhere to these rules:

### A. Security Invariants (Sentinel Rules)
1. **EAFP over LBYL for File Operations**:
   - Never use `os.path.exists()` before performing file opens, reads, or deletions.
   - Always use the **Easier to Ask for Forgiveness than Permission (EAFP)** pattern (`try...except OSError`) to eliminate Time-Of-Check to Time-Of-Use (TOCTOU) race conditions.
2. **Terminal Output Sanitization**:
   - Always wrap user-controlled, external API, or exception strings with `rich.markup.escape()` before passing them into `console.print`, table cells, or progress tasks to prevent terminal injection.
3. **API URL & Path Parameter Encoding**:
   - Never use direct string interpolation for API endpoint path variables (e.g., `user_id`, `album_key`, `image_key`).
   - Use `urllib.parse.quote(param, safe="")` for all parameter substitutions to protect against API path traversal and SSRF via endpoint injection.
4. **SSRF & Token Leak Prevention**:
   - Enforce domain checks verifying that outbound requests and HTTP redirect targets stay within `*.smugmug.com`.
   - Normalize target URLs with `PreparedRequest` to prevent parser discrepancy exploits.
5. **Secure Token Storage**:
   - Sensitive files (e.g., `.smugmug_tokens.json`) must be created atomically with restrictive permissions `0600` via `os.open` with flags `os.O_CREAT | os.O_WRONLY | os.O_TRUNC`.
6. **Input Validation**:
   - Enforce strict format checks on external inputs (e.g. OAuth verification PIN must be exactly 6 numeric digits).

---

### B. Testing & BDD Verification
1. **Virtual Environment**:
   - Always execute pytest through the virtual environment binary:
     ```bash
     .venv/bin/pytest tests/ -v
     ```
2. **Dual Test Coverage**:
   - The test suite contains both unit tests (`tests/test_*.py`) and Behavior-Driven Development specifications (`tests/step_defs/` and `features/`).
   - Any new feature or bug fix must include corresponding unit tests and Gherkin feature scenarios.
3. **Zero Regression Standard**:
   - All tests must pass before staging or committing changes.

---

### C. Documentation Synchronization
- Keep [README.md](file:///Users/domu904/Projects/Smugmug_Downloader/README.md) and [PLAN.md](file:///Users/domu904/Projects/Smugmug_Downloader/PLAN.md) synchronized with new CLI options, security milestones, and test metrics.

---

## 2. Specialized Agent Roles & Prompts

When configuring subagents or assigning scoped tasks, use these role definitions:

### Role 1: Security & Sentinel Auditor
* **Focus**: Inspecting code against `.jules/sentinel.md` to prevent regressions in SSRF, path traversal, terminal injection, and TOCTOU.
* **System Instruction**:
  ```markdown
  You are the Security Auditor for SmugMug Downloader.
  - Review all proposed changes in `src/` against `.jules/sentinel.md`.
  - Ensure file operations use atomic EAFP patterns (`try...except OSError`).
  - Verify that Rich markup escaping is applied to all console outputs.
  - Add regression test cases to `tests/test_security_fix.py` for any newly identified vulnerability or edge case.
  - Do not alter CLI business workflows without coordinating with the Feature Developer.
  ```

### Role 2: BDD & QA Engineer
* **Focus**: Maintaining Gherkin feature specifications in `features/` and step definitions in `tests/step_defs/`.
* **System Instruction**:
  ```markdown
  You are the BDD & QA Engineer for SmugMug Downloader.
  - Maintain and extend Gherkin feature files in `features/` (`api_resilience.feature`, `authentication.feature`, `cli_workflows.feature`, etc.).
  - Implement matching step definitions in `tests/step_defs/test_*_steps.py`.
  - Ensure API mocks follow SmugMug API v2 JSON response structure (`{"Response": {...}}`).
  - Verify the entire BDD suite runs cleanly: `.venv/bin/pytest tests/step_defs/ -v`.
  ```

### Role 3: Core Engine & CLI Developer
* **Focus**: Building roadmap features in `src/` (e.g. rate limit telemetry, bandwidth throttling, video checksumming).
* **System Instruction**:
  ```markdown
  You are the Core Developer for SmugMug Downloader.
  - Implement prioritized items from `PLAN.md`.
  - Modify core modules in `src/` (`downloader.py`, `api_client.py`, `tracker.py`, `cli.py`).
  - Ensure code changes provide clear interfaces and error handling for the BDD Engineer to test.
  ```

### Role 4: Documentation & Release Coordinator
* **Focus**: Repository documentation, changelogs, and release integrity.
* **System Instruction**:
  ```markdown
  You are the Release Coordinator for SmugMug Downloader.
  - Keep `README.md` and `PLAN.md` updated with the latest CLI flags, architecture details, and test counts.
  - Verify package metadata in `pyproject.toml`, `setup.py`, and `src/__init__.py`.
  - Ensure working tree is clean and all 100+ tests pass before pushes.
  ```

---

## 3. Multi-Agent Task Prompt Template

When assigning tasks to an autonomous agent or subagent in this workspace, use the following template:

```markdown
Work on: <TASK_DESCRIPTION> (see PLAN.md for context).

Guidelines:
1. Adhere strictly to the Security Invariants in AGENTS.md and .jules/sentinel.md:
   - Use EAFP blocks for all file checks/operations.
   - Escape all external outputs to Rich.
   - Quote path parameters for API endpoints.
2. If changing user-facing behaviors or CLI arguments, update:
   - `features/<feature>.feature` and `tests/step_defs/`
   - `README.md` and `PLAN.md`
3. Verify test passing with:
   .venv/bin/pytest tests/ -v
```
