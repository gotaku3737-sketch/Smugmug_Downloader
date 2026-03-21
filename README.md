# SmugMug Gallery Downloader

A Python CLI tool to download **all galleries (albums)** from a SmugMug account using the [SmugMug API v2](https://api.smugmug.com/api/v2/doc). Features persistent download tracking so interrupted downloads can be resumed automatically.

## Features

- **OAuth 1.0a authentication** — one-time browser-based authorization, tokens cached for future runs
- **Full account download** — discovers and downloads every album tied to the account
- **Resume support** — tracks per-image download state in a JSON file; interrupted downloads resume where they left off
- **Retry with backoff** — automatically retries on rate limits, server errors, and connection failures
- **Rich CLI output** — progress bars, colored status tables, and spinners
- **Original quality** — downloads the archived (full-resolution) version of each photo/video

## Project Structure

```
Smugmug_Downloader/
├── main.py                          # Entry point
├── requirements.txt                 # Python dependencies
├── .env.example                     # API credential template
├── smugmug_downloader/
│   ├── __init__.py
│   ├── config.py                    # Settings & credential resolution
│   ├── auth.py                      # OAuth 1.0a flow with token caching
│   ├── api_client.py                # SmugMug API wrapper (pagination, retry)
│   ├── tracker.py                   # JSON-based download state tracker
│   ├── downloader.py                # Download orchestration engine
│   └── cli.py                       # CLI interface (argparse + rich)
└── tests/
    ├── test_tracker.py              # Unit tests for state tracker
    └── test_api_client.py           # Unit tests for API client (mocked)
```

## Setup

### 1. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 2. Get SmugMug API credentials

Apply for an API key at [https://api.smugmug.com/api/developer/apply](https://api.smugmug.com/api/developer/apply).

Set your credentials via **one of** these methods:

| Method | How |
|---|---|
| **Environment variables** | `export SMUGMUG_API_KEY=... SMUGMUG_API_SECRET=...` |
| **Static constants** | Edit `API_KEY` and `API_SECRET` at the top of `smugmug_downloader/config.py` |
| **Interactive prompt** | Just run the app — it will ask you |

## Usage

### Download all galleries

```bash
python3 main.py
```

On first run, the app will:
1. Prompt for API credentials (if not already set)
2. Ask where to save downloads (default: `./smugmug_downloads`)
3. Walk you through OAuth authorization in your browser
4. Begin downloading all albums

### Download to a specific directory

```bash
python3 main.py -o ~/SmugMug_Backup
```

### Download a specific album

```bash
python3 main.py -a "Vacation 2024"
```

### List all albums (no download)

```bash
python3 main.py --list-albums
```

### Check download progress

```bash
python3 main.py --status -o ~/SmugMug_Backup
```

### Reset tracking state and start fresh

```bash
python3 main.py --reset -o ~/SmugMug_Backup
```

### Resume an interrupted download

Simply re-run the same command — already-downloaded files are automatically skipped:

```bash
python3 main.py -o ~/SmugMug_Backup
```

## Running Tests

```bash
pip3 install pytest
python3 -m pytest tests/ -v
```
