"""Unit tests for the DownloadTracker."""

import json
import os
import tempfile
import pytest

from src.tracker import DownloadTracker


@pytest.fixture
def tracker(tmp_path):
    """Create a tracker with a temp state file."""
    state_file = os.path.join(str(tmp_path), "download_state.json")
    return DownloadTracker(state_file)


class TestTrackerInit:
    def test_fresh_state(self, tracker):
        assert tracker.state["albums"] == {}
        assert tracker.state["last_updated"] is None

    def test_loads_existing_state(self, tmp_path):
        state_file = os.path.join(str(tmp_path), "download_state.json")
        existing = {
            "albums": {"ABC": {"name": "Test", "path": "test", "status": "done",
                                "total_images": 1, "images": {}}},
            "last_updated": "2026-01-01T00:00:00"
        }
        with open(state_file, "w") as f:
            json.dump(existing, f)

        tracker = DownloadTracker(state_file)
        assert "ABC" in tracker.state["albums"]
        assert tracker.state["albums"]["ABC"]["status"] == "done"

    def test_handles_corrupt_state_file(self, tmp_path):
        state_file = os.path.join(str(tmp_path), "download_state.json")
        with open(state_file, "w") as f:
            f.write("not json")

        tracker = DownloadTracker(state_file)
        assert tracker.state["albums"] == {}


class TestAlbumTracking:
    def test_register_album(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        assert "KEY1" in tracker.state["albums"]
        assert tracker.state["albums"]["KEY1"]["name"] == "Vacation"
        assert tracker.state["albums"]["KEY1"]["status"] == "pending"
        assert tracker.state["albums"]["KEY1"]["total_images"] == 50

    def test_register_album_idempotent(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        assert len(tracker.state["albums"]) == 1

    def test_register_album_updates_total(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_album("KEY1", "Vacation", "vacation", 55)
        assert tracker.state["albums"]["KEY1"]["total_images"] == 55

    def test_set_album_status(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.set_album_status("KEY1", "in_progress")
        assert tracker.state["albums"]["KEY1"]["status"] == "in_progress"

    def test_is_album_done(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        assert not tracker.is_album_done("KEY1")
        tracker.set_album_status("KEY1", "done")
        assert tracker.is_album_done("KEY1")

    def test_is_album_done_nonexistent(self, tracker):
        assert not tracker.is_album_done("NONEXISTENT")


class TestImageTracking:
    def test_register_image(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        assert "IMG1" in tracker.state["albums"]["KEY1"]["images"]
        assert tracker.state["albums"]["KEY1"]["images"]["IMG1"]["status"] == "pending"

    def test_register_image_idempotent(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        assert len(tracker.state["albums"]["KEY1"]["images"]) == 1

    def test_set_image_status(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        tracker.set_image_status("KEY1", "IMG1", "done")
        assert tracker.state["albums"]["KEY1"]["images"]["IMG1"]["status"] == "done"

    def test_is_image_done(self, tracker):
        tracker.register_album("KEY1", "Vacation", "vacation", 50)
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        assert not tracker.is_image_done("KEY1", "IMG1")
        tracker.set_image_status("KEY1", "IMG1", "done")
        assert tracker.is_image_done("KEY1", "IMG1")

    def test_is_image_done_nonexistent(self, tracker):
        assert not tracker.is_image_done("KEY1", "IMG1")


class TestPersistence:
    def test_save_and_reload(self, tmp_path):
        state_file = os.path.join(str(tmp_path), "download_state.json")
        tracker = DownloadTracker(state_file)
        tracker.register_album("KEY1", "Vacation", "vacation", 10)
        tracker.register_image("KEY1", "IMG1", "photo.jpg")
        tracker.set_image_status("KEY1", "IMG1", "done")

        # Reload from disk
        tracker2 = DownloadTracker(state_file)
        assert tracker2.is_image_done("KEY1", "IMG1")
        assert tracker2.state["albums"]["KEY1"]["name"] == "Vacation"

    def test_save_sets_last_updated(self, tracker):
        tracker.register_album("KEY1", "Test", "test", 1)
        assert tracker.state["last_updated"] is not None

    def test_atomic_write_creates_file(self, tmp_path):
        state_file = os.path.join(str(tmp_path), "subdir", "state.json")
        tracker = DownloadTracker(state_file)
        tracker.register_album("KEY1", "Test", "test", 1)
        assert os.path.exists(state_file)


class TestReporting:
    def test_get_summary_empty(self, tracker):
        summary = tracker.get_summary()
        assert summary["total_albums"] == 0
        assert summary["total_images"] == 0

    def test_get_summary(self, tracker):
        tracker.register_album("KEY1", "Album1", "album1", 3)
        tracker.register_image("KEY1", "IMG1", "p1.jpg")
        tracker.register_image("KEY1", "IMG2", "p2.jpg")
        tracker.set_image_status("KEY1", "IMG1", "done")
        tracker.set_image_status("KEY1", "IMG2", "failed")

        summary = tracker.get_summary()
        assert summary["total_albums"] == 1
        assert summary["done_albums"] == 0
        assert summary["total_images"] == 3
        assert summary["done_images"] == 1
        assert summary["failed_images"] == 1

    def test_reset(self, tracker):
        tracker.register_album("KEY1", "Album1", "album1", 3)
        tracker.reset()
        assert tracker.state["albums"] == {}
