# SmugMug Gallery Downloader

A Python CLI tool to download **all galleries (albums)** from a SmugMug account using the [SmugMug API v2](https://api.smugmug.com/api/v2/doc). Features persistent download tracking so interrupted downloads can be resumed automatically.

## Features

- **Parallel downloads** — utilizes concurrent thread workers (`-w` / `--workers`) for high-speed file transfers.
- **Integrity verification** — automatically validates downloaded files using MD5 checksums (with self-healing retries on mismatches).
- **Advanced global progress** — displays real-time backup metrics via `rich`, including overall transfer speed (MB/s), total backup size, aggregate ETA, and transient sub-task download bars.
- **OAuth 1.0a authentication** — one-time browser-based authorization; OAuth access tokens are cached in `.smugmug_tokens.json` for future runs.
- **Full account download** — discovers and downloads every album tied to the user's account.
- **Album filtering** — download specific albums by name matching (`-a` / `--album`).
- **Resume support** — tracks per-image download state in a JSON file (`.smugmug_download_state.json`); interrupted downloads resume seamlessly.
- **Retry with exponential backoff** — automatically retries on rate limits (HTTP 429), server errors (HTTP 500/503), and connection failures.
- **Original quality** — downloads full-resolution archived photos and videos.
- **Hardened Security & Path Traversal Protection** — protects against API parameter and file path traversal, SSRF via endpoint and redirect validation, terminal injection via Rich tag escaping, stack trace/credential leakage, and enforces secure token file permissions.

## Project Architecture & Specs

The project uses Behavior-Driven Development (BDD) with Gherkin feature files stored in `features/` and implemented via `pytest-bdd`.

```
Smugmug_Downloader/
├── main.py                          # Top-level executable script entry point
├── requirements.txt                 # Python runtime and testing dependencies
├── setup.py                         # Package installation script (defines `smd` and `smugmug-download`)
├── pyproject.toml                   # Project metadata and setuptools configuration
├── .env.example                     # API credential template
├── features/                        # Gherkin BDD Feature Specification Files
│   ├── api_resilience.feature       # Backoff retries for HTTP 429/500/503 errors
│   ├── authentication.feature       # OAuth 1.0a flow, token caching, credential resolution
│   ├── cli_workflows.feature        # Listing, album filtering, status, and reset flags
│   ├── concurrency.feature          # Parallel thread worker scaling
│   ├── download_tracking.feature    # Persistent state tracking and resume capabilities
│   └── integrity.feature            # MD5 checksum verification and corruption self-healing
├── src/                             # Core Python implementation package
│   ├── __init__.py                  # Version declaration (v1.0.0)
│   ├── config.py                    # Credential resolution (Env vars > Static constants > CLI prompt)
│   ├── auth.py                      # OAuth 1.0a authentication & token persistence
│   ├── api_client.py                # SmugMug API wrapper (pagination, backoff, download stream)
│   ├── tracker.py                   # JSON state tracking engine (.smugmug_download_state.json)
│   ├── downloader.py                # Concurrent download engine and progress reporting
│   └── cli.py                       # Command line interface parsing & command dispatch
└── tests/                           # Test suite
    ├── step_defs/                   # BDD step definition files for pytest-bdd
    │   ├── test_api_steps.py
    │   ├── test_authentication_steps.py
    │   ├── test_cli_steps.py
    │   ├── test_concurrency_steps.py
    │   ├── test_integrity_steps.py
    │   └── test_tracking_steps.py
    ├── test_tracker.py              # Unit tests for DownloadTracker
    ├── test_api_client.py           # Unit tests for SmugMugClient
    ├── test_downloader.py           # Unit tests for download orchestration
    └── test_security_fix.py         # Unit tests for terminal injection and security fixes
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
3. Open a browser window to authorize access via OAuth 1.0a
4. Save access tokens to `.smugmug_tokens.json` and start downloading all albums

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

The test suite covers unit tests and BDD feature specification scenarios.

### Running all tests

```bash
pip3 install -e ".[dev]"
python3 -m pytest tests/ -v
```

### Running BDD specification tests

To run only the BDD feature tests in `features/`:

```bash
python3 -m pytest tests/step_defs/ -v
```
