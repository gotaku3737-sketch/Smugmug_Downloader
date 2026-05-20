"""
Downloader engine — orchestrates discovery and downloading of all albums and images.
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from src.api_client import SmugMugClient, verify_md5
from src.tracker import DownloadTracker
from src.config import STATE_FILENAME, DEFAULT_WORKERS

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

        # Prevent path traversal vulnerabilities by sanitizing the fallback key
        key = os.path.basename(key.replace("\\", "/"))
        if key in (".", "..", ""):
            key = "untitled_image"

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


class ProgressCallback:
    """Callback to update Rich progress bars during download."""

    def __init__(self, progress, sub_task_id, album_task_id, global_task_id, estimated_size):
        self.progress = progress
        self.sub_task_id = sub_task_id
        self.album_task_id = album_task_id
        self.global_task_id = global_task_id
        self.estimated_size = estimated_size
        self.downloaded_in_attempt = 0

    def _get_task_total(self, task_id):
        task = next((t for t in self.progress.tasks if t.id == task_id), None)
        return task.total if task else 0

    def set_actual_size(self, actual_size):
        if self.sub_task_id is not None:
            self.progress.update(self.sub_task_id, total=actual_size)
        diff = actual_size - self.estimated_size
        if diff != 0:
            album_total = self._get_task_total(self.album_task_id)
            global_total = self._get_task_total(self.global_task_id)
            self.progress.update(self.album_task_id, total=album_total + diff)
            self.progress.update(self.global_task_id, total=global_total + diff)
            self.estimated_size = actual_size

    def __call__(self, chunk_len):
        self.downloaded_in_attempt += chunk_len
        if self.sub_task_id is not None:
            self.progress.update(self.sub_task_id, completed=self.downloaded_in_attempt)
        self.progress.advance(self.album_task_id, chunk_len)
        self.progress.advance(self.global_task_id, chunk_len)

    def reset_attempt(self):
        if self.downloaded_in_attempt > 0:
            self.progress.advance(self.album_task_id, -self.downloaded_in_attempt)
            self.progress.advance(self.global_task_id, -self.downloaded_in_attempt)
        self.downloaded_in_attempt = 0
        if self.sub_task_id is not None:
            self.progress.update(self.sub_task_id, completed=0)


def download_image_worker(client, tracker, image, album_key, album_dir, progress, album_task_id, global_task_id):
    """Worker task to download a single image."""
    image_key = extract_image_key(image)
    filename = get_image_filename(image)
    dest_path = os.path.join(album_dir, filename)

    fmt = image.get("Format", "JPG").upper()
    is_video = fmt in ["MP4", "MOV"]
    fallback_size = 50 * 1024 * 1024 if is_video else 5 * 1024 * 1024
    est_size = image.get("ArchivedSize") or fallback_size
    expected_md5 = image.get("ArchivedMD5")

    # 1. Skip if already completed in tracker
    if tracker.is_image_done(album_key, image_key):
        progress.advance(album_task_id, est_size)
        progress.advance(global_task_id, est_size)
        return "skipped"

    tracker.register_image(album_key, image_key, filename)
    tracker.set_image_status(album_key, image_key, "in_progress")

    # 2. Check if file already exists on disk
    if os.path.exists(dest_path):
        if expected_md5:
            if verify_md5(dest_path, expected_md5):
                tracker.set_image_status(album_key, image_key, "done")
                progress.advance(album_task_id, est_size)
                progress.advance(global_task_id, est_size)
                return "skipped"
        else:
            expected_size = image.get("ArchivedSize")
            if expected_size and os.path.getsize(dest_path) == expected_size:
                tracker.set_image_status(album_key, image_key, "done")
                progress.advance(album_task_id, est_size)
                progress.advance(global_task_id, est_size)
                return "skipped"
            elif not expected_size:
                # Fallback: assume done if no expected size or MD5 and file exists
                tracker.set_image_status(album_key, image_key, "done")
                progress.advance(album_task_id, est_size)
                progress.advance(global_task_id, est_size)
                return "skipped"

    # 3. Get download URL
    download_url = image.get("ArchivedUri")
    if not download_url:
        download_url = client.get_image_download_url(image_key)

    if not download_url:
        progress.console.print(f"  [red]✗ No download URL for {filename}[/red]")
        tracker.set_image_status(album_key, image_key, "failed")
        progress.update(album_task_id, total=next((t.total for t in progress.tasks if t.id == album_task_id), 0) - est_size)
        progress.update(global_task_id, total=next((t.total for t in progress.tasks if t.id == global_task_id), 0) - est_size)
        return "failed"

    # 4. Set up dynamic sub-task
    sub_task_id = progress.add_task(f"  ↳ {filename}", total=est_size, visible=True)
    cb = ProgressCallback(progress, sub_task_id, album_task_id, global_task_id, est_size)

    # 5. Download the file
    try:
        success = client.download_file(
            url=download_url,
            dest_path=dest_path,
            expected_size=image.get("ArchivedSize"),
            expected_md5=expected_md5,
            progress_callback=cb
        )
        if success:
            tracker.set_image_status(album_key, image_key, "done")
            return "downloaded"
        else:
            tracker.set_image_status(album_key, image_key, "failed")
            cb.reset_attempt()
            return "failed"
    finally:
        progress.remove_task(sub_task_id)


def download_album_images(client, tracker, album, output_dir, album_key, progress, global_task_id, workers=DEFAULT_WORKERS):
    """Download all images for a single album in parallel.

    Args:
        client (SmugMugClient): Authenticated API client.
        tracker (DownloadTracker): Download state tracker.
        album (dict): Album object.
        output_dir (str): Base output directory.
        album_key (str): Album key.
        progress (Progress): Rich Progress instance.
        global_task_id (TaskID): Rich task ID for global progress.
        workers (int): Number of thread workers.

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

    # Compute initial total size estimate for this album
    album_est_bytes = 0
    for image in images:
        fmt = image.get("Format", "JPG").upper()
        is_video = fmt in ["MP4", "MOV"]
        fallback_size = 50 * 1024 * 1024 if is_video else 5 * 1024 * 1024
        size = image.get("ArchivedSize") or fallback_size
        album_est_bytes += size

    # Update global task total and add album task
    global_total = next((t.total for t in progress.tasks if t.id == global_task_id), 0)
    progress.update(global_task_id, total=global_total + album_est_bytes)
    album_task_id = progress.add_task(f"📷 {album_name}", total=album_est_bytes)

    downloaded = 0
    skipped = 0
    failed = 0

    # Execute downloads in parallel
    futures = {}
    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    download_image_worker,
                    client, tracker, image, album_key, album_dir, progress, album_task_id, global_task_id
                ): image
                for image in images
            }

            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res == "downloaded":
                        downloaded += 1
                    elif res == "skipped":
                        skipped += 1
                    elif res == "failed":
                        failed += 1
                except Exception as e:
                    failed += 1
                    progress.console.print(f"[red]Error downloading image: {e}[/red]")
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        raise
    finally:
        progress.remove_task(album_task_id)

    # Mark album as done if all images succeeded
    if failed == 0:
        tracker.set_album_status(album_key, "done")
    else:
        tracker.set_album_status(album_key, "in_progress")

    return downloaded, skipped, failed


def run_download(client, output_dir, album_filter=None, workers=DEFAULT_WORKERS):
    """Run the full download process: discover albums then download all images in parallel.

    Args:
        client (SmugMugClient): Authenticated API client.
        output_dir (str): Base output directory.
        album_filter (str, optional): If provided, only download this album name.
        workers (int): Number of concurrent download workers.
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

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        global_task_id = progress.add_task("Total Backup Progress", total=0)

        for idx, album in enumerate(albums, 1):
            album_key = extract_album_key(album)
            album_name = album.get("Name", "Untitled")

            # Skip fully downloaded albums
            if tracker.is_album_done(album_key):
                progress.console.print(
                    f"[dim]  [{idx}/{len(albums)}] {album_name} — "
                    f"already complete, skipping[/dim]"
                )
                continue

            progress.console.print(
                f"\n[bold cyan]  [{idx}/{len(albums)}] Downloading: "
                f"{album_name}[/bold cyan]"
            )

            try:
                downloaded, skipped, failed = download_album_images(
                    client, tracker, album, output_dir, album_key, progress, global_task_id, workers=workers
                )
            except KeyboardInterrupt:
                progress.console.print(
                    "\n[yellow]Download interrupted. Progress has been saved.[/yellow]"
                )
                progress.console.print(
                    "[dim]Run the same command again to resume.[/dim]"
                )
                raise

            total_downloaded += downloaded
            total_skipped += skipped
            total_failed += failed

            progress.console.print(
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
