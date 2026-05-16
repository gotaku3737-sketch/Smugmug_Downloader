"""
SmugMug API v2 client.

Wraps REST calls with pagination, retry logic, and error handling.
"""

import time


from urllib.parse import urlparse

from rich.console import Console


from src.config import BASE_URL, API_ROOT, PAGE_SIZE, MAX_RETRIES, RETRY_BACKOFF

console = Console()


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
        url = f"{self.base_url}{endpoint}"

        if params is None:
            params = {}

        headers = {"Accept": "application/json"}

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.request(
                    method, url, params=params, headers=headers, timeout=30, **kwargs
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
                    f"[yellow]Connection error: {e}. Retrying in {wait_time}s...[/yellow]"
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

    def download_file(self, url, dest_path, expected_size=None):
        """Download a file with streaming and retry support.

        Args:
            url (str): URL to download.
            dest_path (str): Local file path to write to.
            expected_size (int, optional): Expected file size for verification.

        Returns:
            bool: True if download succeeded.
        """

        from src.config import CHUNK_SIZE
        import os

        # Security fix: Prevent SSRF and OAuth token leaks by validating the download URL
        try:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname or ""
            if parsed_url.scheme != "https":
                console.print(f"[red]Security Error: Refusing to download from non-HTTPS URL: {url}[/red]")
                return False
            if not (hostname == "smugmug.com" or hostname.endswith(".smugmug.com")):
                console.print(f"[red]Security Error: Refusing to download from untrusted hostname: {hostname}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Security Error: Invalid URL format: {url}[/red]")
            return False


        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(url, stream=True, timeout=60)
                response.raise_for_status()

                # Get total size from headers
                total_size = int(response.headers.get("Content-Length", 0))

                # Write to temp file first
                temp_path = dest_path + ".tmp"
                downloaded = 0

                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                # Verify size if known
                if total_size and downloaded != total_size:
                    console.print(
                        f"[yellow]Size mismatch: expected {total_size}, "
                        f"got {downloaded}. Retrying...[/yellow]"
                    )
                    os.remove(temp_path)
                    continue

                # Rename temp to final
                os.rename(temp_path, dest_path)
                return True

            except Exception as e:
                wait_time = RETRY_BACKOFF * (2 ** attempt)
                console.print(
                    f"[yellow]Download error: {e}. Retrying in {wait_time}s...[/yellow]"
                )
                time.sleep(wait_time)

                # Clean up temp file
                temp_path = dest_path + ".tmp"
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        return False
