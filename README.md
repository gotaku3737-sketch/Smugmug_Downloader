# SmugMug Gallery Downloader

A Python CLI tool to download **all galleries (albums)** from a SmugMug account using the [SmugMug API v2](https://api.smugmug.com/api/v2/doc). Features persistent download tracking so interrupted downloads can be resumed automatically.

## Features

- **Parallel downloads** — utilizes concurrent thread workers (`-w` / `--workers`) for high-speed file transfers.
- **Integrity verification** — automatically validates downloaded files using MD5 checksums (with self-healing retries on mismatches).
- **Advanced global progress** — displays real-time backup metrics via `rich`, including overall transfer speed (MB/s), total backup size, aggregate ETA, and transient sub-task download bars.
- **OAuth 1.0a authentication** — one-time browser-based authorization; OAuth access tokens are cached in `.smugmug_tokens.json` with strict file permissions (`0o600`, `os.O_NOFOLLOW`, `os.fchmod`).
- **Full account download** — discovers and downloads every album tied to the user's account.
- **Album filtering** — download specific albums by name matching (`-a` / `--album`).
- **Resume support** — tracks per-image download state in a JSON file (`.smugmug_download_state.json`); interrupted downloads resume seamlessly.
- **Retry with exponential backoff** — automatically retries on rate limits (HTTP 429), server errors (HTTP 500/503), and connection failures.
- **Original quality** — downloads full-resolution archived photos and videos.
- **Hardened Security & Sentinel Protection** — robust protections against:
  - **Path Traversal & Filesystem DoS**: Sanitization of API directory/file names and fallback keys via `os.path.basename` (excluding `.` and `..`), 255-character name bounds with extension preservation, and negative index slicing bypass guards.
  - **SSRF & Token Leakage**: Strict domain whitelisting (`*.smugmug.com`), `PreparedRequest` normalization against parser discrepancy exploits, manual redirect tracking (`allow_redirects=False`), and `/` endpoint prefix checks.
  - **Terminal Output Injection**: Complete Rich markup escaping across console outputs, table cells, progress indicators, API error bodies (e.g. 403 responses), and custom exception messages.
  - **Disk Storage Exhaustion (DoS)**: Streaming download bounds via `MAX_DOWNLOAD_SIZE` limits (50 GB per file) and byte-tracking during chunk iteration.
  - **TOCTOU Race Condition Mitigation**: EAFP patterns (`try...except OSError`) for file operations and state loading, atomic temp downloads with `tempfile.mkstemp` and `os.replace`.
  - **Secure Token Storage**: Atomic token cache creation with `os.open` flags `os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW` and explicit `os.fchmod(fd, 0o600)`.
  - **Clean CLI Interruption**: Graceful SIGINT / `KeyboardInterrupt` interception with exit code `130`, eliminating sensitive stack trace and file path disclosure.
  - **Input Validation & FIPS Compliance**: Strict 6-digit numeric verification for OAuth PINs and `usedforsecurity=False` on MD5 hashing operations.

## Project Architecture & Specs

The project follows Behavior-Driven Development (BDD) with Gherkin feature files stored in `features/` and implemented via `pytest-bdd`.

```
Smugmug_Downloader/
├── main.py                          # Top-level executable script entry point
├── requirements.txt                 # Python runtime and testing dependencies
├── setup.py                         # Package installation script (defines `smd` and `smugmug-download`)
├── pyproject.toml                   # Project metadata and setuptools configuration
├── PLAN.md                          # Architecture overview, hardening status & roadmap plan
├── AGENTS.md                        # Multi-agent coordination rules, roles & instructions
├── .env.example                     # API credential template
├── .jules/
│   └── sentinel.md                  # Security vulnerability catalog & regression rules
├── features/                        # Gherkin BDD Feature Specification Files
│   ├── api_resilience.feature       # Backoff retries for HTTP 429/500/503 errors
│   ├── authentication.feature       # OAuth 1.0a flow, token caching, credential resolution
│   ├── cli_workflows.feature        # Listing, album filtering, status, and reset flags
│   ├── concurrency.feature          # Parallel thread worker scaling
│   ├── download_tracking.feature    # Persistent state tracking and resume capabilities
│   └── integrity.feature            # MD5 checksum verification and corruption self-healing
├── src/                             # Core Python implementation package
│   ├── __init__.py                  # Version declaration (v1.0.0)
│   ├── config.py                    # Credential resolution, endpoints & constants
│   ├── auth.py                      # OAuth 1.0a flow, PIN validation & secure token storage
│   ├── api_client.py                # SmugMug API wrapper (pagination, backoff, bounded streaming)
│   ├── tracker.py                   # JSON state tracking engine (atomic write & EAFP state loading)
│   ├── downloader.py                # Concurrent download engine (EAFP file checks & progress reporting)
│   └── cli.py                       # CLI parsing, command dispatch & SIGINT handling
└── tests/                           # Test suite (115 automated tests)
    ├── step_defs/                   # BDD step definition files for pytest-bdd (23 scenarios)
    │   ├── test_api_steps.py
    │   ├── test_authentication_steps.py
    │   ├── test_cli_steps.py
    │   ├── test_concurrency_steps.py
    │   ├── test_integrity_steps.py
    │   └── test_tracking_steps.py
    ├── test_tracker.py              # Unit tests for DownloadTracker (21 tests)
    ├── test_api_client.py           # Unit tests for SmugMugClient (14 tests)
    ├── test_downloader.py           # Unit tests for download orchestration (30 tests)
    └── test_security_fix.py         # Unit tests for Sentinel security hardening (27 tests)
```

## Setup

### 1. Install the application

```bash
pip3 install -e .
```

This installs the project locally and makes the `smd` and `smugmug-download` commands available in your terminal.

To uninstall the tool later, run:
```bash
pip3 uninstall smugmug-downloader
```

### 2. Get SmugMug API credentials

Apply for an API key at [https://api.smugmug.com/api/developer/apply](https://api.smugmug.com/api/developer/apply).

Set your credentials via **one of** these methods:

| Method | How |
|---|---|
| **Environment variables** | `export SMUGMUG_API_KEY=... SMUGMUG_API_SECRET=...` |
| **Static constants** | Edit `API_KEY` and `API_SECRET` in `src/config.py` |
| **Interactive prompt** | Run the application — it will prompt for missing keys |

## Usage

### Download all galleries

```bash
smd
# or
smugmug-download
```

On first run, the app will:
1. Prompt for API credentials (if not already configured)
2. Prompt for destination folder (default: `./smugmug_downloads`)
3. Open a browser window to authorize access via OAuth 1.0a and prompt for the 6-digit PIN
4. Validate the 6-digit PIN, securely save access tokens to `.smugmug_tokens.json` (`0o600`, `os.O_NOFOLLOW`), and start downloading all albums

### Specifying concurrent workers

To speed up downloads, adjust the worker thread count (default: 3):
```bash
smd -w 5
```

### Download to a specific directory

```bash
smd -o ~/SmugMug_Backup
```

### Download a specific album

```bash
smd -a "Vacation 2024"
```

### List all albums (no download)

```bash
smd --list-albums
```

### Check download progress (No API Auth Required)

```bash
smd --status -o ~/SmugMug_Backup
```

### Reset tracking state (No API Auth Required)

```bash
smd --reset -o ~/SmugMug_Backup
```

### Resume an interrupted download

Simply re-run your download command — already-downloaded and verified files are automatically skipped:

```bash
smd -o ~/SmugMug_Backup
```

## Testing & Specifications

The codebase is covered by **115 automated tests** (23 BDD feature scenarios and 92 unit/security regression tests).

### Running all tests

```bash
.venv/bin/pytest tests/ -v
```

### Running BDD specification tests

To run only the BDD feature tests in `features/`:

```bash
.venv/bin/pytest tests/step_defs/ -v
```

## Roadmap & Architecture Plan

Detailed architectural roadmaps, planned milestones (pre-flight disk space checks, adaptive rate limiting, resumable HTTP `Range` downloads, folder hierarchy preservation, and exportable audit manifests), and agent instructions are documented in:
- [PLAN.md](PLAN.md) — Architectural overview, hardening status, and phased milestone roadmap.
- [AGENTS.md](AGENTS.md) — Multi-agent coordination guidelines, sentinel rules, and role templates.
- [.jules/sentinel.md](.jules/sentinel.md) — Security regression history and mitigation patterns.
