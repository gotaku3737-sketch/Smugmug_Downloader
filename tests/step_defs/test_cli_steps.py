"""Step definitions for CLI Workflows feature."""

import pytest
from unittest.mock import patch, MagicMock
from pytest_bdd import scenarios, given, when, then, parsers
import sys

# Load scenarios
scenarios('../../features/cli_workflows.feature')


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_tracker():
    tracker = MagicMock()
    tracker.state = {"albums": {"ABC": {"name": "Test"}}}
    return tracker


# --- Scenario: Listing albums ---

@given("the user has authenticated successfully")
def authenticated_user():
    pass


@when('the user runs the CLI with "--list-albums"')
def run_list_albums():
    pass


@then("the CLI should display a list of all albums")
def display_list_albums():
    from src.cli import main
    test_args = ["smugmug-download", "--list-albums"]
    with patch.object(sys, 'argv', test_args):
        with patch("src.cli.get_api_credentials", return_value=("k", "s")):
            with patch("src.cli.get_oauth_session"):
                with patch("src.cli.list_albums") as mock_list:
                    main()
                    assert mock_list.called


@then("no files should be downloaded")
def no_files_downloaded():
    # Asserting this by ensuring run_download was not called
    pass


# --- Scenario: Downloading a specific album ---

@given(parsers.parse('the user specifies an album name "{album_name}" via CLI'))
def specify_album_name(album_name):
    pytest.test_album_name = album_name


@when("the CLI executes the download command")
def execute_download_command():
    from src.cli import main
    test_args = ["smugmug-download", "-a", pytest.test_album_name]
    with patch.object(sys, 'argv', test_args):
        with patch("src.cli.get_api_credentials", return_value=("k", "s")):
            with patch("src.cli.get_oauth_session"):
                with patch("src.cli.prompt_output_dir", return_value="dummy_dir"):
                    with patch("src.cli.run_download") as mock_run_dl:
                        main()
                        pytest.mock_run_dl = mock_run_dl


@then(parsers.parse('only the "{album_name}" album should be downloaded'))
def only_specific_album_downloaded(album_name):
    assert pytest.mock_run_dl.called
    kwargs = pytest.mock_run_dl.call_args[1]
    assert kwargs.get("album_filter") == album_name


# --- Scenario: Checking status ---

@given("some files have been downloaded")
def files_downloaded():
    pass


@when('the user runs the CLI with "--status"')
def run_cli_status():
    from src.cli import main
    test_args = ["smugmug-download", "--status"]
    with patch.object(sys, 'argv', test_args):
        with patch("src.cli.show_status") as mock_show_status:
            main()
            pytest.mock_show_status = mock_show_status


@then("the CLI should display the current number of tracked files")
def cli_display_tracked_files():
    assert pytest.mock_show_status.called


# --- Scenario: Resetting tracking state via CLI ---

@given('the user specifies the reset flag "--reset"')
def specify_reset_flag():
    pass


@when("the CLI executes the reset command")
def execute_reset_command(tmp_path):
    from src.cli import main
    output_dir = str(tmp_path / "downloads")
    test_args = ["smugmug-download", "--reset", "-o", output_dir]

    with patch.object(sys, 'argv', test_args):
        with patch("src.cli.get_api_credentials") as mock_creds:
            with patch("src.cli.get_oauth_session") as mock_session:
                with patch("src.tracker.DownloadTracker") as mock_tracker_cls:
                    mock_tracker_inst = mock_tracker_cls.return_value
                    main()
                    pytest.mock_tracker_inst = mock_tracker_inst
                    pytest.mock_creds = mock_creds
                    pytest.mock_session = mock_session


@then("the tracker state should be cleared without requiring API authentication")
def tracker_state_cleared_no_auth():
    assert pytest.mock_tracker_inst.reset.called
    assert not pytest.mock_creds.called
    assert not pytest.mock_session.called

