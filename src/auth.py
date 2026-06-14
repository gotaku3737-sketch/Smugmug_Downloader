"""
OAuth 1.0a authentication for SmugMug API.

Implements the non-web-based OAuth flow:
1. Get a request token
2. User visits authorization URL in browser
3. User enters 6-digit verification code
4. Exchange for access token
5. Cache tokens for future use
"""

import json
import os

from requests_oauthlib import OAuth1Session
from rich.console import Console
from rich.markup import escape

from src.config import (
    ACCESS_TOKEN_URL,
    AUTHORIZE_URL,
    REQUEST_TOKEN_URL,
    TOKEN_FILE,
)

console = Console()


def load_cached_tokens():
    """Load previously saved OAuth tokens from disk.

    Returns:
        dict or None: Token dict with 'oauth_token' and 'oauth_token_secret',
                      or None if no cached tokens exist.
    """
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r") as f:
                tokens = json.load(f)
            if tokens.get("oauth_token") and tokens.get("oauth_token_secret"):
                return tokens
        except (json.JSONDecodeError, IOError):
            pass
    return None


def save_tokens(tokens):
    """Save OAuth tokens to disk for future use.

    Args:
        tokens (dict): Token dict with 'oauth_token' and 'oauth_token_secret'.
    """
    try:
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(tokens, f, indent=2)
        console.print(
            f"[dim]Tokens saved to {TOKEN_FILE}[/dim]"
        )
    except OSError as e:
        console.print(f"[yellow]Warning: Could not save tokens: {escape(str(e))}[/yellow]")


def authorize(api_key, api_secret):
    """Run the full OAuth 1.0a non-web authorization flow.

    Args:
        api_key (str): SmugMug API key.
        api_secret (str): SmugMug API secret.

    Returns:
        dict: Token dict with 'oauth_token' and 'oauth_token_secret'.
    """
    # Step 1: Get a request token
    console.print("\n[bold cyan]Starting SmugMug OAuth Authorization...[/bold cyan]")
    oauth = OAuth1Session(api_key, client_secret=api_secret, callback_uri="oob")

    try:
        fetch_response = oauth.fetch_request_token(REQUEST_TOKEN_URL, timeout=30)
    except Exception as e:
        console.print(f"[bold red]Failed to get request token: {escape(str(e))}[/bold red]")
        raise SystemExit(1)

    resource_owner_key = fetch_response.get("oauth_token")
    resource_owner_secret = fetch_response.get("oauth_token_secret")

    # Step 2: Direct user to authorization URL
    authorization_url = oauth.authorization_url(
        AUTHORIZE_URL, Access="Full", Permissions="Read"
    )

    console.print(
        "\n[bold]Please visit this URL in your browser to authorize the app:[/bold]"
    )
    console.print(f"[link={authorization_url}]{authorization_url}[/link]\n")

    # Step 3: User enters verification code
    verifier = console.input(
        "[bold]Enter the 6-digit verification code: [/bold]", password=True
    ).strip()

    if not verifier:
        console.print("[bold red]No verification code entered. Exiting.[/bold red]")
        raise SystemExit(1)

    # Step 4: Exchange for access token
    oauth = OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=resource_owner_key,
        resource_owner_secret=resource_owner_secret,
        verifier=verifier,
    )

    try:
        tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL, timeout=30)
    except Exception as e:
        console.print(f"[bold red]Failed to get access token: {escape(str(e))}[/bold red]")
        raise SystemExit(1)

    console.print("[bold green]✓ Authorization successful![/bold green]")

    # Step 5: Cache tokens
    save_tokens(tokens)

    return tokens


def get_oauth_session(api_key, api_secret):
    """Get an authenticated OAuth1Session, using cached tokens or running auth flow.

    Args:
        api_key (str): SmugMug API key.
        api_secret (str): SmugMug API secret.

    Returns:
        OAuth1Session: Authenticated session ready for API calls.
    """
    tokens = load_cached_tokens()

    if tokens:
        console.print("[dim]Using cached OAuth tokens.[/dim]")
    else:
        tokens = authorize(api_key, api_secret)

    session = OAuth1Session(
        api_key,
        client_secret=api_secret,
        resource_owner_key=tokens["oauth_token"],
        resource_owner_secret=tokens["oauth_token_secret"],
    )

    return session
