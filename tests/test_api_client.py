"""Unit tests for the SmugMug API client (mocked HTTP)."""

import json
import pytest
from unittest.mock import MagicMock, patch

from src.api_client import SmugMugClient, SmugMugAPIError


@pytest.fixture
def mock_session():
    """Create a mock OAuth session."""
    return MagicMock()


@pytest.fixture
def client(mock_session):
    """Create a SmugMugClient with a mock session."""
    return SmugMugClient(mock_session)


def make_response(status_code=200, json_data=None, text=""):
    """Create a mock response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    resp.headers = {"Content-Length": "0"}
    return resp


class TestRequest:
    def test_successful_request(self, client, mock_session):
        mock_session.request.return_value = make_response(
            200, {"Response": {"User": {"NickName": "testuser"}}}
        )
        result = client._request("GET", "/api/v2!authuser")
        assert result["Response"]["User"]["NickName"] == "testuser"

    def test_api_error_raises(self, client, mock_session):
        mock_session.request.return_value = make_response(404, text="Not Found")
        with pytest.raises(SmugMugAPIError) as exc_info:
            client._request("GET", "/api/v2/nonexistent")
        assert exc_info.value.status_code == 404

    @patch("src.api_client.time.sleep")
    def test_retry_on_server_error(self, mock_sleep, client, mock_session):
        """Should retry on 500 errors and succeed on subsequent attempt."""
        mock_session.request.side_effect = [
            make_response(500, text="Server Error"),
            make_response(200, {"Response": {"data": "ok"}}),
        ]
        result = client._request("GET", "/api/v2/test")
        assert result["Response"]["data"] == "ok"
        assert mock_session.request.call_count == 2

    @patch("src.api_client.time.sleep")
    def test_retry_on_rate_limit(self, mock_sleep, client, mock_session):
        mock_session.request.side_effect = [
            make_response(429),
            make_response(200, {"Response": {"data": "ok"}}),
        ]
        result = client._request("GET", "/api/v2/test")
        assert result["Response"]["data"] == "ok"

    @patch("src.api_client.time.sleep")
    def test_max_retries_exceeded(self, mock_sleep, client, mock_session):
        mock_session.request.side_effect = ConnectionError("timeout")
        with pytest.raises(SmugMugAPIError) as exc_info:
            client._request("GET", "/api/v2/test")
        assert "Max retries exceeded" in str(exc_info.value)


class TestPagination:
    def test_single_page(self, client, mock_session):
        mock_session.request.return_value = make_response(200, {
            "Response": {
                "Album": [{"Name": "Album1"}, {"Name": "Album2"}],
                "Pages": {"Total": 2, "Start": 1, "Count": 2},
            }
        })
        items = list(client._paginate("/api/v2/user/test!albums", response_key="Album"))
        assert len(items) == 2
        assert items[0]["Name"] == "Album1"

    def test_multi_page(self, client, mock_session):
        mock_session.request.side_effect = [
            make_response(200, {
                "Response": {
                    "Album": [{"Name": "A1"}],
                    "Pages": {"NextPage": "/api/v2/user/test!albums?start=2&count=1"},
                }
            }),
            make_response(200, {
                "Response": {
                    "Album": [{"Name": "A2"}],
                    "Pages": {},
                }
            }),
        ]
        items = list(client._paginate("/api/v2/user/test!albums", response_key="Album"))
        assert len(items) == 2
        assert items[1]["Name"] == "A2"


class TestGetAuthenticatedUser:
    def test_returns_user(self, client, mock_session):
        mock_session.request.return_value = make_response(200, {
            "Response": {"User": {"NickName": "johndoe", "Name": "John Doe"}}
        })
        user = client.get_authenticated_user()
        assert user["NickName"] == "johndoe"


class TestGetUserAlbums:
    def test_returns_albums(self, client, mock_session):
        mock_session.request.return_value = make_response(200, {
            "Response": {
                "Album": [
                    {"Name": "Vacation", "AlbumKey": "ABC", "ImageCount": 10},
                    {"Name": "Family", "AlbumKey": "DEF", "ImageCount": 5},
                ],
                "Pages": {},
            }
        })
        albums = client.get_user_albums("testuser")
        assert len(albums) == 2
        assert albums[0]["AlbumKey"] == "ABC"


class TestGetAlbumImages:
    def test_returns_images(self, client, mock_session):
        mock_session.request.return_value = make_response(200, {
            "Response": {
                "AlbumImage": [
                    {"ImageKey": "IMG1", "FileName": "photo1.jpg"},
                    {"ImageKey": "IMG2", "FileName": "photo2.jpg"},
                ],
                "Pages": {},
            }
        })
        images = client.get_album_images("ABC")
        assert len(images) == 2
        assert images[0]["ImageKey"] == "IMG1"


class TestGetImageDownloadUrl:
    def test_returns_original_url(self, client, mock_session):
        mock_session.request.return_value = make_response(200, {
            "Response": {
                "ImageSizeDetails": {
                    "ImageSizeOriginal": {
                        "Url": "https://photos.smugmug.com/original.jpg",
                        "Width": 4000,
                        "Height": 3000,
                    }
                }
            }
        })
        url = client.get_image_download_url("IMG1")
        assert "original.jpg" in url

    def test_returns_none_on_error(self, client, mock_session):
        mock_session.request.return_value = make_response(404, text="Not Found")
        url = client.get_image_download_url("IMG1")
        assert url is None


class TestDownloadFile:
    @patch("src.api_client.verify_md5")
    @patch("src.api_client.time.sleep")
    def test_download_file_success(self, mock_sleep, mock_verify_md5, client, mock_session, tmp_path):
        import os
        dest_path = str(tmp_path / "test.jpg")
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "5"}
        mock_response.iter_content.return_value = [b"hello"]
        mock_session.get.return_value = mock_response
        mock_verify_md5.return_value = True

        success = client.download_file("https://photos.smugmug.com/img.jpg", dest_path, expected_size=5, expected_md5="abc")
        assert success
        assert os.path.exists(dest_path)
        with open(dest_path, "r") as f:
            assert f.read() == "hello"

    @patch("src.api_client.verify_md5")
    @patch("src.api_client.time.sleep")
    def test_download_file_md5_mismatch_retry(self, mock_sleep, mock_verify_md5, client, mock_session, tmp_path):
        dest_path = str(tmp_path / "test.jpg")
        mock_response = MagicMock()
        mock_response.headers = {"Content-Length": "5"}
        mock_response.iter_content.return_value = [b"hello"]
        mock_session.get.return_value = mock_response
        mock_verify_md5.side_effect = [False, True]

        success = client.download_file("https://photos.smugmug.com/img.jpg", dest_path, expected_size=5, expected_md5="abc")
        assert success
        assert mock_session.get.call_count == 2
