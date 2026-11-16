# SmugMug Gallery Downloader — Project Architecture & Roadmap Plan

This document outlines the current architectural foundation, completed hardening milestones, test verification status, and planned roadmap for the **SmugMug Gallery Downloader**.

---

## 1. System Architecture Overview

The SmugMug Downloader is designed as a modular, resilient CLI backup utility built with Python:

- **CLI Layer (`src/cli.py`)**: Entry point for command parsing, argument dispatch (`-a`/`--album`, `-w`/`--workers`, `-o`/`--output-dir`, `--list-albums`, `--status`, `--reset`, `--version`), clean `KeyboardInterrupt` / SIGINT handling (exit code 130), and top-level error sanitization to prevent stack trace information leaks.
- **Authentication & Credential Layer (`src/auth.py`, `src/config.py`)**: Manages OAuth 1.0a 3-legged out-of-band handshake (`callback_uri="oob"`) with 30s request timeouts, password-masked CLI credential/PIN prompts (`password=True`), 6-digit PIN format validation, and atomic token caching at `~/.smugmug_tokens.json` with strict permissions (`0o600` via `os.open` with `os.O_NOFOLLOW` and `os.fchmod`).
- **API Client Layer (`src/api_client.py`)**: Interacts with SmugMug API v2. Handles automatic cursor-based pagination, exponential backoff retries (HTTP 429, 500, 503), domain-whitelisted redirect tracking, streaming downloads via `tempfile.mkstemp`, and disk exhaustion protection (`MAX_DOWNLOAD_SIZE`).
- **State & Tracking Engine (`src/tracker.py`)**: Maintains a persistent per-album and per-image download status in `download_state.json` inside the target output directory with thread-safe atomic writes (`tempfile.mkstemp` + `os.replace`) and EAFP-based state loading.
- **Download Orchestrator (`src/downloader.py`)**: Manages thread pool concurrency, Rich live multi-progress bars, path length sanitization (255-character truncation), MD5 file integrity validation, and EAFP-based file existence verification.

---

## 2. Completed Milestones & Hardening

### Core Functionality
- [x] Full SmugMug user account album discovery and download.
- [x] Concurrent multi-threaded downloads with configurable worker pools (`-w`).
- [x] Resume capability powered by persistent JSON state tracking.
- [x] Global progress tracking (aggregate bandwidth MB/s, ETA, completed files).
- [x] MD5 checksum validation with corruption self-healing retries.

### Security Hardening (Sentinel Milestones)
- [x] **Path Traversal Protection**:
  - Sanitization of API-provided directory names, image filenames, and fallback `ImageKey` values using `os.path.basename` and exclusion of `.` / `..`.
  - Filesystem DoS prevention via 255-character path truncation with file extension preservation.
  - Fix for negative index slicing edge case when extension lengths exceed maximum allowable bounds.
- [x] **SSRF & Token Leak Prevention**:
  - Strict domain verification ensuring requests and followed HTTP redirects remain on `*.smugmug.com`.
  - URL normalization using `PreparedRequest` to eliminate parser discrepancy exploits between `urlparse` and `requests`.
  - Manual redirect tracking (`allow_redirects=False`) ensuring OAuth headers are never leaked across cross-host redirects.
  - Strict validation that relative API endpoints start with `/` to prevent hostname injection.
- [x] **Terminal Injection Defense**:
  - Escaping of Rich markup (`rich.markup.escape`) across all console outputs, table cells, and progress indicators.
  - Complete escaping of untrusted external inputs in exception strings, HTTP response bodies (e.g. 403 error payloads), and connection error messages before embedding into `SmugMugAPIError`.
- [x] **Stack Trace & Error Sanitization**:
  - Global exception handlers in CLI preventing sensitive credential and file path disclosure in standard error.
  - Explicit handling of `KeyboardInterrupt` with clean user cancellation messaging and standard exit code `130`.
- [x] **Disk Storage Exhaustion Defense (DoS)**:
  - Enforced `MAX_DOWNLOAD_SIZE` (50 GB per file) limit validating `Content-Length` headers and tracking accumulated bytes during stream iteration.
- [x] **FIPS Compatibility**:
  - Explicit `usedforsecurity=False` on MD5 hashing operations.
- [x] **TOCTOU Race Condition Elimination (EAFP)**:
  - Atomic temporary file creation with `tempfile.mkstemp` and `os.replace`.
  - Secure permission creation flags on token cache (`os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW`) followed by `os.fchmod(fd, 0o600)` to ensure strict permissions even on existing files.
  - Removal of pre-checks (`os.path.exists`) across `downloader.py`, `tracker.py`, `auth.py`, and `api_client.py` in favor of atomic `try...except OSError` (EAFP).
- [x] **Input Validation & Prompt Hardening**:
  - Strict 6-digit numeric validation for OAuth verification PINs.
  - Password-masked interactive prompts (`password=True`) for API credentials and OAuth PINs, plus 30s timeouts on OAuth token requests.
- [x] **No Hardcoded Credentials**: Removal of static `API_KEY` and `API_SECRET` fallback constants from `src/config.py`, enforcing credential provision exclusively via `SMUGMUG_API_KEY` / `SMUGMUG_API_SECRET` environment variables or masked interactive runtime prompts.

---

## 3. Test Verification & Quality Assurance

The codebase is covered by **115 automated tests** (100% passing):
- **Behavior-Driven Development (BDD)**: 23 Gherkin specifications executed with `pytest-bdd`:
  - `features/api_resilience.feature` (5 scenarios: backoff on 429/500, max retries, file download retries)
  - `features/authentication.feature` (6 scenarios: token loading, interactive login, PIN validation, file permissions)
  - `features/cli_workflows.feature` (4 scenarios: album listing, filtering, status, reset)
  - `features/concurrency.feature` (1 scenario: worker thread scaling)
  - `features/download_tracking.feature` (5 scenarios: state creation, skipping, reset, EAFP loading, disk verification)
  - `features/integrity.feature` (2 scenarios: MD5 validation and corruption recovery)
- **Unit & Security Suites**: 92 focused test cases:
  - `tests/test_api_client.py` (14 tests: pagination, request lifecycle, download streaming)
  - `tests/test_downloader.py` (30 tests: dirname sanitization, key extraction, filename resolution, format mappings, path traversal sanitization)
  - `tests/test_tracker.py` (21 tests: JSON persistence, thread safety, state recovery, reporting)
  - `tests/test_security_fix.py` (27 tests: SSRF, redirects, parser discrepancies, terminal injection, TOCTOU, filename truncation, worker EAFP checks, password masking, OAuth timeouts, unbounded streams, permission tightening, negative slicing)

Execution command:
```bash
.venv/bin/pytest tests/ -v
```

---

## 4. Multi-Agent Coordination Guidelines

Autonomous agents operating on this repository must follow the shared ground rules defined in [AGENTS.md](AGENTS.md), including:
- Adhering to Sentinel security invariants (EAFP pattern, Rich escaping, parameter URL encoding, symlink protection).
- Maintaining dual test coverage (unit tests and BDD specs in `features/`).
- Using specialized agent roles (Security Auditor, BDD & QA Engineer, Core Developer, Release Coordinator).
- Verifying all 115+ tests pass with zero regressions before staging changes.

---

## 5. Future Roadmap & Upcoming Milestones

### Phase 1: Storage Safety & Network Resilience
- [ ] **Pre-Flight Disk Capacity Verification**:
  - *Technical Scope*: Before initiating downloads, inspect target filesystem storage using `shutil.disk_usage(output_dir)`. Compare free disk space against estimated download volume.
  - *Security Scope*: Validate `ArchivedSize` metadata against negative or integer-overflow values and enforce a minimum free-space reserve threshold.
  - *Acceptance Criteria*: Abort download with an actionable warning if free space is insufficient, allowing `--force` to bypass.
- [ ] **Adaptive Rate Limiter & Header Telemetry**:
  - *Technical Scope*: Enhance API client backoff to inspect response headers (`Retry-After`, `X-RateLimit-Reset`, `X-RateLimit-Remaining`).
  - *Security Scope*: Sanitize and cap `Retry-After` / `X-RateLimit-Reset` header values (e.g., `MAX_RETRY_WAIT = 300s`) to prevent unbounded sleep DoS from malformed or malicious headers.
  - *Acceptance Criteria*: Replace static backoff sleep with bounded server-recommended pause times on HTTP 429 responses.
- [ ] **Bandwidth Throttling (`--max-rate`)**:
  - *Technical Scope*: Implement token-bucket or chunk-pacing rate limiting inside `iter_content` streaming in `src/api_client.py`.
  - *Security Scope*: Strictly validate rate-limit inputs (rejecting zero, negative, or overflow values) to prevent division-by-zero errors or thread lockups.
  - *Acceptance Criteria*: Accept rate caps (e.g. `--max-rate 5M`, `--max-rate 500K`) to prevent saturation of user network connections.

### Phase 2: Large Media & Resumption Optimization
- [ ] **Resumable Chunk Downloads (HTTP `Range` Header)**:
  - *Technical Scope*: Support partial download resumption for multi-gigabyte video files by requesting `Range: bytes=<current_bytes>-` on temporary files after dropped connections.
  - *Security Scope*: Enforce `MAX_DOWNLOAD_SIZE` across cumulative bytes (`existing_offset + streamed_bytes`) to prevent multi-request disk exhaustion bypasses, validate `Content-Range` headers, and open partial `.tmp` files with `os.O_NOFOLLOW` to prevent symlink append attacks.
  - *Acceptance Criteria*: Interrupted large downloads resume safely from their byte offset instead of restarting from 0 bytes.
- [ ] **Non-MD5 Media Integrity (Video Container Validation)**:
  - *Technical Scope*: For MP4/MOV assets lacking SmugMug MD5 checksums, perform container header validation (verifying `ftyp` and `moov` atoms) and generate a local SHA-256 hash stored in the state file.
  - *Security Scope*: Bound atom/header parsing reads to fixed offsets to prevent malformed container parser DoS.
  - *Acceptance Criteria*: Detect truncated video files even in the absence of remote MD5 metadata.
- [ ] **Preserve SmugMug Folder Hierarchy (`--preserve-folders`)**:
  - *Technical Scope*: Query the SmugMug Node API (`/api/v2/node/<NodeID>`) to resolve parent folder structures, creating mirrored subdirectories instead of saving all albums into a flat folder.
  - *Security Scope*: Sanitize each folder segment via `sanitize_dirname`, enforce a maximum nesting depth (`MAX_FOLDER_DEPTH = 10`) and total path length bound, and verify resolved directory paths stay strictly within `os.path.realpath(output_dir)` to block symlink and nested traversal escapes.
  - *Acceptance Criteria*: Albums nested in SmugMug folders are placed safely in matching subdirectories on disk when enabled.

### Phase 3: CLI Usability & Backup Auditing
- [ ] **Granular Filtering Options**:
  - *Technical Scope*: Extend CLI filters with `--since <YYYY-MM-DD>` (filter by date modified/uploaded), `--photos-only`, and `--videos-only`.
  - *Security Scope*: Validate `--since` date strings strictly against ISO-8601 (`YYYY-MM-DD`) before querying or filtering.
  - *Acceptance Criteria*: Users can selectively backup newly added media or specific media formats without scanning all files.
- [ ] **Dry-Run Inspection Mode (`--dry-run`)**:
  - *Technical Scope*: Scan account and albums, compute media counts and total byte requirements, and display summary table without performing downloads or disk writes.
  - *Acceptance Criteria*: Safe estimation of backup footprint before initiating transfers.
- [ ] **Exportable Audit Manifest (`--export-report <json|csv>`)**:
  - *Technical Scope*: Output a complete backup manifest detailing album names, file paths, byte sizes, MD5/SHA-256 checksums, and sync timestamps.
  - *Security Scope*: Prevent CSV Formula/Macro Injection by neutralizing fields starting with `=`, `+`, `-`, `@`, `\t`, or `\r`, and write report files atomically with `0o600` permissions and `os.O_NOFOLLOW`.
  - *Acceptance Criteria*: Generates a sanitized external report file suitable for offline archive auditing.
- [ ] **Multi-Profile Credential Management (`--profile <name>`)**:
  - *Technical Scope*: Support named credential profiles stored in `~/.smugmug_<profile>_tokens.json`.
  - *Security Scope*: Validate profile names against a strict allowlist regex (`^[a-zA-Z0-9_-]{1,64}$`) to prevent path traversal in token filenames.
  - *Acceptance Criteria*: Seamless switching between multiple SmugMug accounts using CLI flags.

### Phase 4: Security & Defense-in-Depth Hardening
- [ ] **OS Keychain Integration & Secure Token Revocation (`--logout`)**:
  - *Technical Scope*: Store OAuth tokens in the native OS secret store (`keyring`: macOS Keychain, Linux Secret Service, Windows Credential Locker) with encrypted fallback, and provide `--logout` to securely wipe cached tokens.
  - *Acceptance Criteria*: Credentials remain protected by OS-level secret storage rather than plaintext JSON when supported, and `--logout` revokes/removes local session state cleanly.
- [ ] **CLI Concurrency & Pagination DoS Bounds (`MAX_WORKERS`, `MAX_PAGES`)**:
  - *Technical Scope*: Enforce upper/lower bounds on `-w`/`--workers` (e.g., `1..32`) to prevent thread exhaustion or `ValueError` crashes, cap maximum pagination pages (`MAX_PAGES`) in `_paginate`, and bound JSON API response sizes.
  - *Acceptance Criteria*: Malformed CLI arguments or infinite/oversized API responses abort cleanly without exhausting system threads or memory.
- [ ] **Symlink-Safe Reads & Startup Permission Auditing**:
  - *Technical Scope*: Open existing token and state files with `os.O_NOFOLLOW` during reads (`load_cached_tokens`, `_load_state`) and audit/tighten file permissions (`0o600`) on load, warning if untrusted permissions are detected.
  - *Acceptance Criteria*: Symlinked or world-readable token/state files are detected, blocked, or remediated safely via EAFP on startup.
- [ ] **Automated Vulnerability & SAST Scanning**:
  - *Technical Scope*: Integrate `bandit` static analysis and `pip-audit` dependency vulnerability checks into the test/verification workflow.
  - *Acceptance Criteria*: Security regressions and known vulnerable dependencies are flagged automatically prior to releases.
