"""
CLI entry point for SmugMug Downloader.
"""

import sys
import argparse
import os

from rich.console import Console
from rich.markup import escape

from src import __version__
from src.config import DEFAULT_OUTPUT_DIR, get_api_credentials, DEFAULT_WORKERS
from src.auth import get_oauth_session
from src.api_client import SmugMugClient
from src.downloader import list_albums, show_status, run_download

console = Console()


def print_banner():
    """Print a stylish startup banner."""
    console.print(
        "\n[bold cyan]"
        "╔═══════════════════════════════════════════╗\n"
        "║         SmugMug Gallery Downloader         ║\n"
        f"║              v{__version__:^20s}       ║\n"
        "╚═══════════════════════════════════════════╝"
        "[/bold cyan]\n"
    )


def prompt_output_dir(default):
    """Prompt the user for the output directory.

    Args:
        default (str): Default output directory path.

    Returns:
        str: Chosen output directory.
    """
    console.print(
        f"[bold]Where should downloads be saved?[/bold] "
        f"[dim](default: {escape(os.path.abspath(default))})[/dim]"
    )
    user_input = console.input("  [bold]Output directory: [/bold]").strip()

    if user_input:
        return user_input
    return default


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="smugmug-download",
        description="Download all galleries from your SmugMug account.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help=f"Output directory for downloads (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-a", "--album",
        default=None,
        help="Download only albums matching this name (case-insensitive)",
    )
    parser.add_argument(
        "--list-albums",
        action="store_true",
        help="List all albums without downloading",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show download progress from the state file",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear all download tracking state and start fresh",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of concurrent download workers (default: {DEFAULT_WORKERS})",
    )

    args = parser.parse_args()

    print_banner()

    # Handle --status without needing auth
    if args.status:
        output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
        show_status(output_dir)
        return

    # Handle --reset without needing auth
    if args.reset:
        output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
        from src.tracker import DownloadTracker
        from src.config import STATE_FILENAME

        state_path = os.path.join(output_dir, STATE_FILENAME)
        tracker = DownloadTracker(state_path)
        tracker.reset()
        console.print("[green]✓ Download state has been reset.[/green]")
        return

    # Get API credentials (env vars → static constants → prompt)
    try:
        api_key, api_secret = get_api_credentials()
    except SystemExit:
        return

    # Authenticate
    try:
        session = get_oauth_session(api_key, api_secret)
    except SystemExit:
        return

    client = SmugMugClient(session)

    # Handle --list-albums
    if args.list_albums:
        list_albums(client)
        return

    # Prompt for output directory if not specified via CLI
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = prompt_output_dir(DEFAULT_OUTPUT_DIR)

    console.print(
        f"\n[dim]Downloads will be saved to: "
        f"{escape(os.path.abspath(output_dir))}[/dim]\n"
    )

    # Run the download
    try:
        run_download(client, output_dir, album_filter=args.album, workers=args.workers)
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Download interrupted. Progress has been saved.[/yellow]"
        )
        console.print(
            "[dim]Run the same command again to resume.[/dim]"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
