"""
Downloader engine — orchestrates discovery and downloading of all albums and images.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from src.api_client import SmugMugClient
from src.tracker import DownloadTracker
from src.config import STATE_FILENAME

console = Console()


def sanitize_dirname(name):
    """Convert an album name into a safe directory name.

    Args:
        name (str): Album name.

    Returns:
        str: Filesystem-safe directory name.
    """
    # Replace unsafe chars with hyphens, collapse multiples
    safe = re.sub(r'[<>:"/\\|?*]', '-', name)
    safe = re.sub(r'-+', '-', safe).strip(' -.')
    return safe or "untitled"


def extract_image_key(image):
    """Extract the image key from an image object.

    The key might be in 'ImageKey' directly, or parsed from
    the 'Uri' field which looks like '/api/v2/image/XXXXXX'.

    Args:
        image (dict): Image object from the API.

    Returns:
        str: Image key.
    """
    key = image.get("ImageKey", "")
    if not key:
        uri = image.get("Uri", "")
        # Example: /api/v2/image/jPPKD2c → jPPKD2c
        parts = uri.rstrip("/").split("/")
        key = parts[-1] if parts else ""
    return key


def extract_album_key(album):
    """Extract the album key from an album object.

    Args:
        album (dict): Album object from the API.

    Returns:
        str: Album key.
    """
    key = album.get("AlbumKey", "")
    if not key:
        uri = album.get("Uri", "")
        parts = uri.rstrip("/").split("/")
        key = parts[-1] if parts else ""
    return key


def get_image_filename(image):
    """Determine a filename for an image, using the original filename if available.

    Args:
        image (dict): Image object from the API.

    Returns:
        str: Filename for saving.
    """
    filename = image.get("FileName", "")
    if filename:
        # Prevent path traversal vulnerabilities by sanitizing the filename
        filename = os.path.basename(filename.replace("\\", "/"))
        if filename in (".", ".."):
            filename = ""

    if not filename:
        key = extract_image_key(image)
        # Try to determine extension from format
        fmt = image.get("Format", "JPG").upper()
        ext_map = {"JPG": "jpg", "JPEG": "jpg", "PNG": "png",
                    "GIF": "gif", "HEIC": "heic", "MP4": "mp4",
                    "MOV": "mov", "TIFF": "tiff", "TIF": "tif"}
        ext = ext_map.get(fmt, "jpg")
        filename = f"{key}.{ext}"
    return filename


def list_albums(client):
    """Fetch and display all albums for the authenticated user.

    Args:
        client (SmugMugClient): Authenticated API client.
    """
    with console.status("[bold cyan]Fetching user info..."):
        user = client.get_authenticated_user()

    nickname = user.get("NickName", "")
    display_name = user.get("Name", nickname)
    console.print(f"\n[bold]Logged in as:[/bold] {display_name} ({nickname})\n")

    with console.status("[bold cyan]Fetching albums..."):
        albums = client.get_user_albums(nickname)

    if not albums:
        console.print("[yellow]No albums found.[/yellow]")
        return

    table = Table(title=f"Albums ({len(albums)})")
    table.add_column("#", style="dim", width=5)
    table.add_column("Name", style="bold")
    table.add_column("Key", style="dim")
    table.add_column("Images", justify="right")
    table.add_column("Privacy", style="dim")

    for idx, album in enumerate(albums, 1):
        table.add_row(
            str(idx),
            album.get("Name", "Unknown"),
            extract_album_key(album),
            str(album.get("ImageCount", "?")),
            album.get("SecurityType", "?"),
        )

    console.print(table)


def show_status(output_dir):
    """Display download progress from the state file.

    Args:
        output_dir (str): Output directory containing state file.
    """
    state_path = os.path.join(output_dir, STATE_FILENAME)
    tracker = DownloadTracker(state_path)
    summary = tracker.get_summary()

    if not summary["total_albums"]:
        console.print("[yellow]No download state found. Run a download first.[/yellow]")
        return

    console.print(f"\n[bold]Download Status[/bold]")
    console.print(f"  Last updated: {summary['last_updated'] or 'Never'}")
    console.print(
        f"  Albums: [green]{summary['done_albums']}[/green] / "
        f"{summary['total_albums']} done"
    )
    console.print(
        f"  Images: [green]{summary['done_images']}[/green] / "
        f"{summary['total_images']} done"
    )
    if summary["failed_images"]:
        console.print(
            f"  Failed: [red]{summary['failed_images']}[/red]"
        )

    table = Table(title="Per-Album Progress")
    table.add_column("Album", style="bold")
    table.add_column("Status")
    table.add_column("Progress", justify="right")
    table.add_column("Failed", justify="right")

    for album in summary["albums"]:
        status_icon = {
            "done": "[green]✓ done[/green]",
            "in_progress": "[yellow]⧗ in progress[/yellow]",
            "pending": "[dim]○ pending[/dim]",
        }.get(album["status"], album["status"])

        table.add_row(
            album["name"],
            status_icon,
            f"{album['done']}/{album['total']}",
            str(album["failed"]) if album["failed"] else "-",
        )

    console.print(table)


def download_album_images(client, tracker, album, output_dir, album_key):
    """Download all images for a single album.

    Args:
        client (SmugMugClient): Authenticated API client.
        tracker (DownloadTracker): Download state tracker.
        album (dict): Album object.
        output_dir (str): Base output directory.
        album_key (str): Album key.

    Returns:
        tuple: (downloaded_count, skipped_count, failed_count)
    """
    album_name = album.get("Name", "Untitled")
    album_dir_name = sanitize_dirname(album_name)
    album_dir = os.path.join(output_dir, album_dir_name)
    os.makedirs(album_dir, exist_ok=True)

    # Fetch images in this album
    images = client.get_album_images(album_key)

    tracker.register_album(
        album_key, album_name, album_dir_name, len(images)
    )
    tracker.set_album_status(album_key, "in_progress")

    downloaded = 0
    skipped = 0
    failed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"📷 {album_name}", total=len(images)
        )

        for image in images:
            image_key = extract_image_key(image)
            filename = get_image_filename(image)

            # Skip if already downloaded
            if tracker.is_image_done(album_key, image_key):
                skipped += 1
                progress.advance(task)
                continue

            tracker.register_image(album_key, image_key, filename)
            tracker.set_image_status(album_key, image_key, "in_progress")

            # Get download URL
            download_url = image.get("ArchivedUri")
            if not download_url:
                # Try to get from size details
                download_url = client.get_image_download_url(image_key)

            if not download_url:
                console.print(
                    f"  [red]✗ No download URL for {filename}[/red]"
                )
                tracker.set_image_status(album_key, image_key, "failed")
                failed += 1
                progress.advance(task)
                continue

            # Download the file
            dest_path = os.path.join(album_dir, filename)

            # Check if file already exists on disk (but state wasn't tracked)
            if os.path.exists(dest_path):
                tracker.set_image_status(album_key, image_key, "done")
                skipped += 1
                progress.advance(task)
                continue

            expected_size = image.get("ArchivedSize")
            success = client.download_file(download_url, dest_path, expected_size)

            if success:
                tracker.set_image_status(album_key, image_key, "done")
                downloaded += 1
            else:
                tracker.set_image_status(album_key, image_key, "failed")
                failed += 1

            progress.advance(task)

    # Mark album as done if all images succeeded
    if failed == 0:
        tracker.set_album_status(album_key, "done")
    else:
        tracker.set_album_status(album_key, "in_progress")

    return downloaded, skipped, failed


def run_download(client, output_dir, album_filter=None):
    """Run the full download process: discover albums then download all images.

    Args:
        client (SmugMugClient): Authenticated API client.
        output_dir (str): Base output directory.
        album_filter (str, optional): If provided, only download this album name.
    """
    os.makedirs(output_dir, exist_ok=True)

    state_path = os.path.join(output_dir, STATE_FILENAME)
    tracker = DownloadTracker(state_path)

    # Get authenticated user
    with console.status("[bold cyan]Fetching user info..."):
        user = client.get_authenticated_user()

    nickname = user.get("NickName", "")
    display_name = user.get("Name", nickname)
    console.print(f"\n[bold]Logged in as:[/bold] {display_name} ({nickname})")

    # Fetch all albums
    with console.status("[bold cyan]Fetching albums..."):
        albums = client.get_user_albums(nickname)

    if not albums:
        console.print("[yellow]No albums found.[/yellow]")
        return

    # Filter if specified
    if album_filter:
        albums = [
            a for a in albums
            if album_filter.lower() in a.get("Name", "").lower()
        ]
        if not albums:
            console.print(
                f"[yellow]No albums matching '{album_filter}' found.[/yellow]"
            )
            return

    console.print(f"[bold]Found {len(albums)} album(s) to process.[/bold]")
    console.print(f"[dim]Output directory: {os.path.abspath(output_dir)}[/dim]\n")

    total_downloaded = 0
    total_skipped = 0
    total_failed = 0

    for idx, album in enumerate(albums, 1):
        album_key = extract_album_key(album)
        album_name = album.get("Name", "Untitled")

        # Skip fully downloaded albums
        if tracker.is_album_done(album_key):
            console.print(
                f"[dim]  [{idx}/{len(albums)}] {album_name} — "
                f"already complete, skipping[/dim]"
            )
            continue

        console.print(
            f"\n[bold cyan]  [{idx}/{len(albums)}] Downloading: "
            f"{album_name}[/bold cyan]"
        )

        downloaded, skipped, failed = download_album_images(
            client, tracker, album, output_dir, album_key
        )

        total_downloaded += downloaded
        total_skipped += skipped
        total_failed += failed

        console.print(
            f"  [green]↓ {downloaded}[/green] downloaded, "
            f"[dim]{skipped} skipped[/dim]"
            + (f", [red]{failed} failed[/red]" if failed else "")
        )

    # Final summary
    console.print("\n" + "─" * 50)
    console.print("[bold]Download Complete![/bold]")
    console.print(f"  [green]Downloaded:[/green] {total_downloaded}")
    console.print(f"  [dim]Skipped:[/dim]    {total_skipped}")
    if total_failed:
        console.print(f"  [red]Failed:[/red]     {total_failed}")
    console.print(f"  [dim]Location:[/dim]   {os.path.abspath(output_dir)}")
    console.print("─" * 50)
