"""Step definitions for MD5 Integrity Verification feature."""

import os
import pytest
from unittest.mock import patch, MagicMock
from pytest_bdd import scenarios, given, when, then, parsers
from src.api_client import SmugMugClient

# Load scenarios
scenarios('../../features/integrity.feature')


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def client(mock_session):
    return SmugMugClient(mock_session)


@given(parsers.parse('a remote file has MD5 checksum "{md5}"'))
def remote_file_has_md5(md5):
    pytest.expected_md5 = md5


@when(parsers.parse('the file is downloaded and its MD5 matches "{md5}"'))
def download_matching_md5(client, mock_session, tmp_path, md5):
    dest_path = str(tmp_path / "matching.jpg")
    
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "5"}
    mock_response.iter_content.return_value = [b"hello"]
    mock_session.get.return_value = mock_response

    with patch("src.api_client.verify_md5", return_value=True) as mock_verify:
        pytest.success = client.download_file(
            "https://photos.smugmug.com/img.jpg",
            dest_path,
            expected_size=5,
            expected_md5=pytest.expected_md5
        )


@then("the file should be saved and marked as done in the tracker")
def file_saved_and_marked():
    assert pytest.success is True


@when(parsers.parse('the file is downloaded but its MD5 is "{mismatched_md5}"'))
def download_mismatched_md5(client, mock_session, tmp_path, mismatched_md5):
    dest_path = str(tmp_path / "mismatched.jpg")
    
    mock_response = MagicMock()
    mock_response.headers = {"Content-Length": "5"}
    mock_response.iter_content.return_value = [b"hello"]
    mock_session.get.return_value = mock_response

    with patch("src.api_client.verify_md5") as mock_verify:
        with patch("src.api_client.time.sleep") as mock_sleep:
            mock_verify.side_effect = [False, True]
            pytest.success = client.download_file(
                "https://photos.smugmug.com/img.jpg",
                dest_path,
                expected_size=5,
                expected_md5=pytest.expected_md5
            )
            pytest.get_call_count = mock_session.get.call_count


@then("the system should reject the file, delete it, and retry the download")
def reject_delete_retry():
    assert pytest.success is True
    # The client must make 2 requests (initial + retry)
    assert pytest.get_call_count == 2
