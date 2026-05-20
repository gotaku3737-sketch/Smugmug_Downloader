"""Step definitions for Concurrent Downloads feature."""

import pytest
from unittest.mock import patch, MagicMock
from pytest_bdd import scenarios, given, when, then, parsers
import sys

# Load scenarios
scenarios('../../features/concurrency.feature')


@given(parsers.parse('the user specifies worker count "{workers}" via CLI'))
def specify_worker_count(workers):
    pytest.test_workers = int(workers)


@when("the CLI executes the download command")
def execute_download_command_with_workers():
    from src.cli import main
    test_args = ["smugmug-download", "-w", str(pytest.test_workers)]
    with patch.object(sys, 'argv', test_args):
        with patch("src.cli.get_api_credentials", return_value=("k", "s")):
            with patch("src.cli.get_oauth_session"):
                with patch("src.cli.prompt_output_dir", return_value="dummy_dir"):
                    with patch("src.cli.run_download") as mock_run_dl:
                        main()
                        pytest.mock_run_dl = mock_run_dl


@then(parsers.parse('the download should run using "{workers}" concurrent workers'))
def download_runs_with_workers(workers):
    assert pytest.mock_run_dl.called
    kwargs = pytest.mock_run_dl.call_args[1]
    assert kwargs.get("workers") == int(workers)
