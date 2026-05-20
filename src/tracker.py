"""
Download state tracker with JSON persistence.

Tracks which albums and images have been downloaded, enabling resume on failure.
Uses atomic writes (temp file + rename) to prevent corruption.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone


class DownloadTracker:
    """Tracks download state for albums and images."""

    def __init__(self, state_file_path):
        """
        Args:
            state_file_path (str): Absolute path to the state JSON file.
        """
        self.state_file = state_file_path
        self._lock = threading.RLock()
        with self._lock:
            self.state = self._load_state()

    def _load_state(self):
        """Load state from disk, or return a fresh state dict.

        Returns:
            dict: The current download state.
        """
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        return {"albums": {}, "last_updated": None}

    def save(self):
        """Atomically write state to disk (temp file + rename)."""
        with self._lock:
            self.state["last_updated"] = datetime.now(timezone.utc).isoformat()

            dir_name = os.path.dirname(self.state_file)
            os.makedirs(dir_name, exist_ok=True)

            # Write to temp file, then rename for atomicity
            fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self.state, f, indent=2)
                os.replace(temp_path, self.state_file)
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise

    # --- Album-level tracking ---

    def register_album(self, album_key, album_name, album_path, total_images):
        """Register an album in the state if not already present.

        Args:
            album_key (str): Album key identifier.
            album_name (str): Display name of the album.
            album_path (str): Local directory name for the album.
            total_images (int): Total number of images in the album.
        """
        with self._lock:
            if album_key not in self.state["albums"]:
                self.state["albums"][album_key] = {
                    "name": album_name,
                    "path": album_path,
                    "status": "pending",
                    "total_images": total_images,
                    "images": {},
                }
                self.save()
            else:
                # Update total count if changed
                album = self.state["albums"][album_key]
                if album["total_images"] != total_images:
                    album["total_images"] = total_images
                    self.save()

    def set_album_status(self, album_key, status):
        """Set the download status of an album.

        Args:
            album_key (str): Album key identifier.
            status (str): One of 'pending', 'in_progress', 'done'.
        """
        with self._lock:
            if album_key in self.state["albums"]:
                self.state["albums"][album_key]["status"] = status
                self.save()

    def is_album_done(self, album_key):
        """Check if an album is fully downloaded.

        Args:
            album_key (str): Album key identifier.

        Returns:
            bool: True if the album status is 'done'.
        """
        with self._lock:
            album = self.state["albums"].get(album_key, {})
            return album.get("status") == "done"

    # --- Image-level tracking ---

    def register_image(self, album_key, image_key, filename):
        """Register an image in the state if not already present.

        Args:
            album_key (str): Album key.
            image_key (str): Image key.
            filename (str): The image filename.
        """
        with self._lock:
            album = self.state["albums"].get(album_key)
            if album and image_key not in album["images"]:
                album["images"][image_key] = {
                    "filename": filename,
                    "status": "pending",
                }

    def set_image_status(self, album_key, image_key, status):
        """Set the download status of an image.

        Args:
            album_key (str): Album key.
            image_key (str): Image key.
            status (str): One of 'pending', 'in_progress', 'done', 'failed'.
        """
        with self._lock:
            album = self.state["albums"].get(album_key)
            if album and image_key in album["images"]:
                album["images"][image_key]["status"] = status
                self.save()

    def is_image_done(self, album_key, image_key):
        """Check if an image is already downloaded.

        Args:
            album_key (str): Album key.
            image_key (str): Image key.

        Returns:
            bool: True if the image status is 'done'.
        """
        with self._lock:
            album = self.state["albums"].get(album_key, {})
            image = album.get("images", {}).get(image_key, {})
            return image.get("status") == "done"

    # --- Reporting ---

    def get_summary(self):
        """Get a summary of download progress.

        Returns:
            dict: Summary with counts and per-album breakdowns.
        """
        with self._lock:
            total_albums = len(self.state["albums"])
            done_albums = sum(
                1 for a in self.state["albums"].values() if a["status"] == "done"
            )

            total_images = 0
            done_images = 0
            failed_images = 0
            album_details = []

            for album_key, album in self.state["albums"].items():
                album_total = album.get("total_images", 0)
                album_done = sum(
                    1 for img in album["images"].values() if img["status"] == "done"
                )
                album_failed = sum(
                    1 for img in album["images"].values() if img["status"] == "failed"
                )

                total_images += album_total
                done_images += album_done
                failed_images += album_failed

                album_details.append({
                    "key": album_key,
                    "name": album["name"],
                    "status": album["status"],
                    "total": album_total,
                    "done": album_done,
                    "failed": album_failed,
                })

            return {
                "total_albums": total_albums,
                "done_albums": done_albums,
                "total_images": total_images,
                "done_images": done_images,
                "failed_images": failed_images,
                "last_updated": self.state.get("last_updated"),
                "albums": album_details,
            }

    def reset(self):
        """Clear all tracking state."""
        with self._lock:
            self.state = {"albums": {}, "last_updated": None}
            self.save()
