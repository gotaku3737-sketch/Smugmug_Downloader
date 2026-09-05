# SmugMug Gallery Downloader — Project Architecture & Roadmap Plan

This document outlines the current architectural foundation, completed hardening milestones, test verification status, and planned roadmap for the **SmugMug Gallery Downloader**.

---

## 1. System Architecture Overview

The SmugMug Downloader is designed as a modular, resilient CLI backup utility built with Python:

- **CLI Layer (`src/cli.py`)**: Entry point for command parsing, argument dispatch (`-a`, `-w`, `-o`, `--list-albums`, `--status`, `--reset`), and top-level error sanitization to prevent stack trace information leaks.
- **Authentication & Credential Layer (`src/auth.py`, `src/config.py`)**: Manages OAuth 1.0a 3-legged handshake, PIN validation, and encrypted/restricted token caching (`chmod 0600`) created atomically via `os.open`.
- **API Client Layer (`src/api_client.py`)**: Interacts with SmugMug API v2. Handles automatic cursor-based pagination, exponential backoff retries (HTTP 429, 500, 503), domain-whitelisted redirect tracking, and atomic streaming downloads via `mkstemp`.
- **State & Tracking Engine (`src/tracker.py`)**: Maintains a persistent per-album and per-image download status in `.smugmug_download_state.json` with atomic writes (`os.replace`) and EAFP-based state loading.
- **Download Orchestrator (`src/downloader.py`)**: Manages thread pool concurrency, Rich live multi-progress bars, MD5 file integrity validation, and EAFP-based file existence verification.

---

## 2. Completed Milestones & Hardening

### Core Functionality
- [x] Full SmugMug user account album discovery and download.
- [x] Concurrent multi-threaded downloads with configurable worker pools (`-w`).
- [x] Resume capability powered by persistent JSON state tracking.
- [x] Global progress tracking (aggregate bandwidth MB/s, ETA, completed files).
- [x] MD5 checksum validation with corruption self-healing retries.

### Security Hardening (Sentinel Milestones)
- [x] **Path Traversal Protection**: Sanitization of API-provided directory names, image filenames, and fallback `ImageKey` values using `os.path.basename` and exclusion of `.` / `..`.
- [x] **SSRF & Token Leak Prevention**: Strict domain verification ensuring requests and followed HTTP redirects remain on `*.smugmug.com`, with URL normalization to eliminate parser discrepancy exploits.
- [x] **Terminal Injection Defense**: Escaping of Rich markup across all console outputs, table cells, and progress indicators.
- [x] **Stack Trace Sanitization**: Global exception handlers in CLI preventing sensitive credential and file path disclosure in standard error.
- [x] **FIPS Compatibility**: Explicit `usedforsecurity=False` on MD5 hashing operations.
- [x] **TOCTOU Race Condition Eliminaton (EAFP)**:
  - Atomic temporary file creation with `tempfile.mkstemp` and `os.replace`.
  - Secure permission creation flags on token cache (`os.O_CREAT | os.O_WRONLY | os.O_TRUNC`, `0o600`).
  - Removal of pre-checks (`os.path.exists`) across `downloader.py`, `tracker.py`, `auth.py`, and `api_client.py` in favor of atomic `try...except OSError` (EAFP).
- [x] **Input Validation**: Strict 6-digit numeric validation for OAuth verification PINs.

---

## 3. Test Verification & Quality Assurance

The codebase is covered by **107 automated tests**:
- **Behavior-Driven Development (BDD)**: Gherkin specs executed with `pytest-bdd` (23 scenarios):
  - `features/api_resilience.feature`
  - `features/authentication.feature`
  - `features/cli_workflows.feature`
  - `features/concurrency.feature`
  - `features/download_tracking.feature`
  - `features/integrity.feature`
- **Unit & Security Suites**:
  - `tests/test_api_client.py`
  - `tests/test_downloader.py`
  - `tests/test_tracker.py`
  - `tests/test_security_fix.py` (SSRF, path traversal, terminal injection, TOCTOU, verifier validation)

---

## 4. Multi-Agent Coordination Guidelines

Autonomous agents operating on this repository must follow the shared ground rules defined in [AGENTS.md](file:///Users/domu904/Projects/Smugmug_Downloader/AGENTS.md), including:
- Adhering to Sentinel security invariants (EAFP pattern, Rich escaping, parameter URL encoding).
- Maintaining dual test coverage (unit tests and BDD specs in `features/`).
- Using specialized agent roles (Security Auditor, BDD & QA Engineer, Core Developer, Release Coordinator).

---

## 5. Future Roadmap & Upcoming Milestones

### Phase 1: Performance & Resilience Enhancements
- [ ] **Dynamic Rate Limiter Telemetry**: Auto-tune worker thread pool and request pace based on HTTP 429 `Retry-After` headers and API latency.
- [ ] **Bandwidth Throttling Option (`--max-rate`)**: Allow users to cap download bandwidth to avoid saturating home or office network connections.
- [ ] **Video Checksum Validation**: Implement streaming SHA-256 verification or metadata validation for video formats that lack SmugMug MD5 hashes.

### Phase 2: User Experience & CLI Features
- [ ] **Multi-Profile Support**: Support multiple stored credentials / configuration profiles (`--profile <name>`).
- [ ] **Dry-Run Mode (`--dry-run`)**: Estimate total download size and file counts without writing files to disk.
- [ ] **Exportable Download Reports**: Generate summary reports in JSON or CSV format detailing backup results.
