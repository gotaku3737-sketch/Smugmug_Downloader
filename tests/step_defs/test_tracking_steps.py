"""Step definitions for download tracking feature."""

import os
import json
import pytest
from pytest_bdd import scenarios, given, when, then, parsers
from src.tracker import DownloadTracker

# Load all scenarios from the feature file
scenarios('../../features/download_tracking.feature')


@pytest.fixture
def tracker_dir(tmp_path):
    """Fixture to provide a temporary directory for tracker files."""
    return str(tmp_path)


@pytest.fixture
def tracker_file(tracker_dir):
    """Fixture to provide the path to the state file."""
    return os.path.join(tracker_dir, ".smugmug_state.json")


@pytest.fixture
def tracker(tracker_file):
    """Fixture to provide a DownloadTracker instance."""
    return DownloadTracker(tracker_file)


# --- Scenario: Initial download creates tracker state ---

@given("an empty download directory")
def empty_download_directory(tracker_dir, tracker_file):
    if os.path.exists(tracker_file):
        os.remove(tracker_file)
    assert not os.path.exists(tracker_file)


@when(parsers.parse('a file "{filename}" is successfully downloaded'))
def file_is_downloaded(tracker, tracker_dir, filename):
    album_key = "TestAlbum"
    image_key = "TestImage"
    pytest.test_filename = filename
    
    # Simulate saving file
    file_path = os.path.join(tracker_dir, filename)
    with open(file_path, "w") as f:
        f.write("mock image data")
        
    # Simulate tracker updates
    tracker.register_album(album_key, "Album", "album_path", 1)
    tracker.register_image(album_key, image_key, filename)
    tracker.set_image_status(album_key, image_key, "done")


@then('the file should be saved to the directory')
def file_saved_to_directory(tracker_dir):
    file_path = os.path.join(tracker_dir, pytest.test_filename)
    assert os.path.exists(file_path)


@then(parsers.parse('the tracker state file should record "{filename}" as downloaded'))
def tracker_records_downloaded(tracker, filename):
    album_key = "TestAlbum"
    image_key = "TestImage"
    
    # Reload tracker to verify state was written to disk
    tracker2 = DownloadTracker(tracker.state_file)
    assert tracker2.is_image_done(album_key, image_key)
    
    # Also verify filename matches
    image_info = tracker2.state["albums"][album_key]["images"][image_key]
    assert image_info["filename"] == filename


# --- Scenario: Skipping already downloaded files ---

@given(parsers.parse('a tracker state file indicating "{filename}" is downloaded'))
def state_file_indicates_downloaded(tracker, filename):
    album_key = "TestAlbum"
    image_key = "TestImage"
    tracker.register_album(album_key, "Album", "album_path", 1)
    tracker.register_image(album_key, image_key, filename)
    tracker.set_image_status(album_key, image_key, "done")


@given(parsers.parse('the file "{filename}" exists in the download directory'))
def file_exists_in_directory(tracker_dir, filename):
    file_path = os.path.join(tracker_dir, filename)
    with open(file_path, "w") as f:
        f.write("mock image data")


@when(parsers.parse('the system attempts to download "{filename}"'))
def attempt_download(tracker, filename):
    album_key = "TestAlbum"
    image_key = "TestImage"
    # The system logic would check if it's done before downloading
    # We simulate the check here
    is_done = tracker.is_image_done(album_key, image_key)
    # Store result for 'then' step
    pytest.is_done_check_result = is_done


@then(parsers.parse('the system should skip the download'))
def system_should_skip():
    assert pytest.is_done_check_result is True


# --- Scenario: Resetting download state ---

@given("a tracker state file exists with tracked files")
def state_file_with_tracked_files(tracker):
    tracker.register_album("Album1", "Album 1", "album_1", 5)
    assert len(tracker.state["albums"]) > 0


@when("the user requests to reset the state")
def request_reset_state(tracker):
    tracker.reset()


@then("the tracker state file should be cleared or deleted")
def state_file_cleared(tracker):
    assert len(tracker.state["albums"]) == 0
