"""
Configuration for SmugMug Downloader.

API credentials can be set in three ways (in order of priority):
1. Environment variables: SMUGMUG_API_KEY and SMUGMUG_API_SECRET
2. Static constants below (edit these directly)
3. Interactive CLI prompt (if neither of the above is set)
"""

import os

# ============================================================================
# STATIC API CREDENTIALS — Edit these if you prefer not to use env vars
# ============================================================================
API_KEY = ""
API_SECRET = ""
# ============================================================================

# SmugMug API endpoints
BASE_URL = "https://api.smugmug.com"
API_ROOT = "/api/v2"

# OAuth 1.0a endpoints
REQUEST_TOKEN_URL = "https://api.smugmug.com/services/oauth/1.0a/getRequestToken"
AUTHORIZE_URL = "https://api.smugmug.com/services/oauth/1.0a/authorize"
ACCESS_TOKEN_URL = "https://api.smugmug.com/services/oauth/1.0a/getAccessToken"

# Token storage
TOKEN_FILE = os.path.expanduser("~/.smugmug_tokens.json")

# Download defaults
DEFAULT_OUTPUT_DIR = "./smugmug_downloads"
STATE_FILENAME = "download_state.json"
DEFAULT_WORKERS = 3
CHUNK_SIZE = 8192  # bytes per download chunk
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, multiplied on each retry
PAGE_SIZE = 100  # items per API page request


def get_api_credentials():
    """
    Get API credentials from env vars, static constants, or interactive prompt.

    Returns:
        tuple: (api_key, api_secret)
    """
    # Priority 1: Environment variables
    api_key = os.environ.get("SMUGMUG_API_KEY", "").strip()
    api_secret = os.environ.get("SMUGMUG_API_SECRET", "").strip()

    if api_key and api_secret:
        return api_key, api_secret

    # Priority 2: Static constants at top of this file
    if API_KEY and API_SECRET:
        return API_KEY, API_SECRET

    # Priority 3: Interactive prompt
    from rich.console import Console
    console = Console()
    console.print(
        "\n[bold yellow]SmugMug API credentials not found.[/bold yellow]"
    )
    console.print(
        "You can get API credentials at: "
        "[link=https://api.smugmug.com/api/developer/apply]"
        "https://api.smugmug.com/api/developer/apply[/link]\n"
    )
    console.print(
        "[dim]Tip: Set SMUGMUG_API_KEY and SMUGMUG_API_SECRET as environment "
        "variables, or edit the constants in src/config.py to "
        "avoid this prompt.[/dim]\n"
    )

    api_key = console.input("[bold]Enter your SmugMug API Key: [/bold]").strip()
    api_secret = console.input(
        "[bold]Enter your SmugMug API Secret: [/bold]"
    ).strip()

    if not api_key or not api_secret:
        console.print("[bold red]API key and secret are required. Exiting.[/bold red]")
        raise SystemExit(1)

    return api_key, api_secret
