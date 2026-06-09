"""
SmugMug API v2 client.

Wraps REST calls with pagination, retry logic, and error handling.
"""

import hashlib
import time


from urllib.parse import urlparse, urljoin
from requests.models import PreparedRequest

from rich.console import Console
from rich.markup import escape

from src.config import BASE_URL, API_ROOT, PAGE_SIZE, MAX_RETRIES, RETRY_BACKOFF

console = Console()


def verify_md5(file_path, expected_md5):
    """Verify MD5 checksum of a file against expected value.

    Args:
        file_path (str): Path to the file.
        expected_md5 (str): Expected MD5 hex string.

    Returns:
        bool: True if checksums match or expected_md5 is not provided.
    """
    if not expected_md5:
        return True
    try:
        try:
            hash_md5 = hashlib.md5(usedforsecurity=False)
        except TypeError:
            hash_md5 = hashlib.md5()  # nosec B324
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest().lower() == expected_md5.lower()
    except IOError:
        return False



class SmugMugAPIError(Exception):
    """Raised when the SmugMug API returns an error."""

    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


class SmugMugClient:
    """Client for the SmugMug API v2."""

    def __init__(self, session):
        """
        Args:
            session (OAuth1Session): Authenticated OAuth session.
        """
        self.session = session
        self.base_url = BASE_URL

    def _request(self, method, endpoint, params=None, **kwargs):
        """Make an authenticated API request with retry logic.

        Args:
            method (str): HTTP method (GET, POST, etc.)
            endpoint (str): API endpoint path (e.g., '/api/v2!authuser')
            params (dict, optional): Query parameters.

        Returns:
            dict: Parsed JSON response.

        Raises:
            SmugMugAPIError: If the API returns an error after retries.
        """
        # Security fix: Prevent SSRF via manipulated endpoint paths (e.g. NextPage)
        if not endpoint.startswith("/"):
            raise SmugMugAPIError(0, f"Security Error: Invalid endpoint '{endpoint}'. Must start with '/'")
        url = f"{self.base_url}{endpoint}"

        if params is None:
            params = {}

        headers = {"Accept": "application/json"}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                current_url = url
                current_method = method
                # Copy kwargs to avoid mutating the outer retry loop's state
                current_kwargs = dict(kwargs)
                response = self.session.request(
                    current_method, current_url, params=params, headers=headers, timeout=30, allow_redirects=False, **current_kwargs
                )

                # Security fix: Handle redirects manually to prevent OAuth token leaks to untrusted domains
                redirects_followed = 0
                max_redirects = 30
                while getattr(response, "is_redirect", False) is True:
                    if redirects_followed >= max_redirects:
                        raise SmugMugAPIError(0, f"Security Error: Too many redirects (>{max_redirects})")
                    redirects_followed += 1

                    redirect_target = response.headers.get("Location")
                    if not redirect_target:
                        break

                    current_url = urljoin(current_url, redirect_target)

                    # Normalize URL to prevent parsing discrepancies between urlparse and requests
                    p = PreparedRequest()
                    p.prepare_url(current_url, None)
                    current_url = p.url

                    parsed_redir = urlparse(current_url)
                    redir_host = parsed_redir.hostname or ""

                    if parsed_redir.scheme != "https" or not (redir_host == "smugmug.com" or redir_host.endswith(".smugmug.com")):
                        raise SmugMugAPIError(0, f"Security Error: Refusing redirect to untrusted URL: {current_url}")

                    # Determine correct HTTP method for redirect per HTTP spec
                    if response.status_code in (301, 302, 303):
                        current_method = "GET"
                        # Drop payloads for GET redirects
                        current_kwargs.pop("data", None)
                        current_kwargs.pop("json", None)
                        current_kwargs.pop("files", None)

                    response = self.session.request(
                        current_method, current_url, headers=headers, timeout=30, allow_redirects=False, **current_kwargs
                    )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited — wait and retry
                    wait_time = RETRY_BACKOFF * (2 ** attempt)
                    console.print(
                        f"[yellow]Rate limited. Waiting {wait_time}s...[/yellow]"
                    )
                    time.sleep(wait_time)
                    continue
                elif response.status_code >= 500:
                    # Server error — retry
                    wait_time = RETRY_BACKOFF * (2 ** attempt)
                    console.print(
                        f"[yellow]Server error {response.status_code}. "
                        f"Retrying in {wait_time}s...[/yellow]"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise SmugMugAPIError(
                        response.status_code,
                        response.text[:500],
                    )

            except (ConnectionError, TimeoutError, OSError) as e:
                last_error = e
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                console.print(
                    f"[yellow]Connection error: {escape(str(e))}. Retrying in {wait_time}s...[/yellow]"
                )
                time.sleep(wait_time)
                continue

        raise SmugMugAPIError(0, f"Max retries exceeded. Last error: {last_error}")

    def _paginate(self, endpoint, params=None, response_key=None):
        """Fetch all pages of a paginated API endpoint.

        Args:
            endpoint (str): API endpoint path.
            params (dict, optional): Query parameters.
            response_key (str, optional): Key in Response to extract items from.

        Yields:
            dict: Each item from the paginated response.
        """
        if params is None:
            params = {}

        params.setdefault("count", PAGE_SIZE)
        params.setdefault("start", 1)

        while True:
            data = self._request("GET", endpoint, params=params)

            response = data.get("Response", {})

            # Extract items from the response
            items = []
            if response_key and response_key in response:
                items = response[response_key]
            else:
                # Try to find the first list in the response
                for key, value in response.items():
                    if isinstance(value, list):
                        items = value
                        break

            yield from items

            # Check for next page
            pages = response.get("Pages", {})
            next_page = pages.get("NextPage")

            if not next_page:
                break

            # Update endpoint to next page URL
            endpoint = next_page
            params = {}  # NextPage URL already contains params

    def get_authenticated_user(self):
        """Get the currently authenticated user.

        Returns:
            dict: User object with NickName, Name, etc.
        """
        data = self._request("GET", f"{API_ROOT}!authuser")
        return data.get("Response", {}).get("User", {})

    def get_user_albums(self, nickname):
        """Get all albums for a user.

        Args:
            nickname (str): SmugMug user nickname.

        Returns:
            list: List of album objects.
        """
        endpoint = f"{API_ROOT}/user/{nickname}!albums"
        return list(self._paginate(endpoint, response_key="Album"))

    def get_album_images(self, album_key):
        """Get all images in an album.

        Args:
            album_key (str): Album key (e.g., 'SJT3DX').

        Returns:
            list: List of image objects.
        """
        endpoint = f"{API_ROOT}/album/{album_key}!images"
        return list(self._paginate(endpoint, response_key="AlbumImage"))

    def get_image_download_url(self, image_key):
        """Get the original-size download URL for an image.

        Args:
            image_key (str): Image key (e.g., 'jPPKD2c').

        Returns:
            str: The download URL, or None if not found.
        """
        endpoint = f"{API_ROOT}/image/{image_key}!sizedetails"
        try:
            data = self._request("GET", endpoint)
            response = data.get("Response", {})
            size_details = response.get("ImageSizeDetails", {})

            # Try to get the archived (original) image URL
            archived = size_details.get("ImageSizeOriginal", {})
            url = archived.get("Url")
            width = archived.get("Width")
            height = archived.get("Height")

            if not url:
                # Fall back to largest available size
                for size_key in ["ImageSizeX5Large", "ImageSizeX4Large",
                                 "ImageSizeX3Large", "ImageSizeX2Large",
                                 "ImageSizeXLarge", "ImageSizeLarge"]:
                    size_info = size_details.get(size_key, {})
                    if size_info.get("Url"):
                        url = size_info["Url"]
                        break

            return url

        except SmugMugAPIError:
            return None

    def get_image_metadata(self, image_key):
        """Get metadata for an image to find download info.

        Args:
            image_key (str): Image key.

        Returns:
            dict: Image metadata.
        """
        endpoint = f"{API_ROOT}/image/{image_key}"
        data = self._request("GET", endpoint)
        return data.get("Response", {}).get("Image", {})

    def download_file(self, url, dest_path, expected_size=None, expected_md5=None, progress_callback=None):
        """Download a file with streaming and retry support.

        Args:
            url (str): URL to download.
            dest_path (str): Local file path to write to.
            expected_size (int, optional): Expected file size for verification.
            expected_md5 (str, optional): Expected MD5 hash for verification.
            progress_callback (callable, optional): Callback that takes bytes count downloaded.

        Returns:
            bool: True if download succeeded.
        """

        from src.config import CHUNK_SIZE
        import os
        import tempfile

        # Security fix: Prevent SSRF and OAuth token leaks by validating the download URL
        try:
            # Normalize URL to prevent parsing discrepancies between urlparse and requests
            p = PreparedRequest()
            p.prepare_url(url, None)
            url = p.url

            parsed_url = urlparse(url)
            hostname = parsed_url.hostname or ""
            if parsed_url.scheme != "https":
                console.print(f"[red]Security Error: Refusing to download from non-HTTPS URL: {escape(str(url))}[/red]")
                return False
            if not (hostname == "smugmug.com" or hostname.endswith(".smugmug.com")):
                console.print(f"[red]Security Error: Refusing to download from untrusted hostname: {escape(str(hostname))}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Security Error: Invalid URL format: {escape(str(url))}[/red]")
            return False


        for attempt in range(MAX_RETRIES):
            if progress_callback and hasattr(progress_callback, "reset_attempt"):
                progress_callback.reset_attempt()

            try:
                current_url = url
                response = self.session.get(current_url, stream=True, timeout=60, allow_redirects=False)

                # Security fix: Handle redirects manually to prevent OAuth token leaks to untrusted domains
                redirects_followed = 0
                max_redirects = 30
                while getattr(response, "is_redirect", False) is True:
                    if redirects_followed >= max_redirects:
                        console.print(f"[red]Security Error: Too many redirects (>{max_redirects})[/red]")
                        return False
                    redirects_followed += 1

                    from urllib.parse import urljoin
                    redirect_target = response.headers.get("Location")
                    if not redirect_target:
                        break

                    current_url = urljoin(current_url, redirect_target)

                    # Normalize URL to prevent parsing discrepancies between urlparse and requests
                    p = PreparedRequest()
                    p.prepare_url(current_url, None)
                    current_url = p.url

                    parsed_redir = urlparse(current_url)
                    redir_host = parsed_redir.hostname or ""

                    if parsed_redir.scheme != "https" or not (redir_host == "smugmug.com" or redir_host.endswith(".smugmug.com")):
                        console.print(f"[red]Security Error: Refusing redirect to untrusted URL: {escape(str(current_url))}[/red]")
                        return False

                    response = self.session.get(current_url, stream=True, timeout=60, allow_redirects=False)

                response.raise_for_status()

                # Get total size from headers
                total_size = int(response.headers.get("Content-Length", 0))
                if total_size and progress_callback and hasattr(progress_callback, "set_actual_size"):
                    progress_callback.set_actual_size(total_size)

                # Write to temp file first
                downloaded = 0

                dir_name = os.path.dirname(dest_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")

                try:
                    with os.fdopen(fd, "wb") as f:
                        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback:
                                    progress_callback(len(chunk))

                    # Verify size if known
                    if total_size and downloaded != total_size:
                        console.print(
                            f"[yellow]Size mismatch: expected {total_size}, "
                            f"got {downloaded}. Retrying...[/yellow]"
                        )
                        os.remove(temp_path)
                        continue

                    # Verify MD5 if known
                    if expected_md5 and not verify_md5(temp_path, expected_md5):
                        console.print(
                            f"[yellow]MD5 mismatch: expected {expected_md5}. Retrying...[/yellow]"
                        )
                        os.remove(temp_path)
                        continue

                    # Rename temp to final (atomic)
                    os.replace(temp_path, dest_path)
                    return True
                except Exception:
                    # Clean up temp file on internal failure if not already cleaned
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                    raise

            except Exception as e:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                console.print(
                    f"[yellow]Download error: {escape(str(e))}. Retrying in {wait_time}s...[/yellow]"
                )
                time.sleep(wait_time)

        return False
