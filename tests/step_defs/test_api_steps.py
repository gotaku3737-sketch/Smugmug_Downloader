"""Step definitions for API Resilience feature."""

import pytest
from unittest.mock import MagicMock, patch
from pytest_bdd import scenarios, given, when, then
from src.api_client import SmugMugClient, SmugMugAPIError

# Load scenarios
scenarios('../../features/api_resilience.feature')


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def client(mock_session):
    return SmugMugClient(mock_session)


def make_response(status_code=200, json_data=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = text
    return resp


# --- Scenario: Retrying on 429 Too Many Requests ---

@given("the SmugMug API returns a 429 Too Many Requests error")
def api_returns_429(mock_session):
    mock_session.request.side_effect = [
        make_response(429, text="Too Many Requests"),
        make_response(200, {"Response": {"success": True}}),
    ]


@when("the API client receives the response")
def client_receives_response():
    pass


@then("the API client should wait using exponential backoff")
def client_waits_backoff(client):
    with patch("src.api_client.time.sleep") as mock_sleep:
        result = client._request("GET", "/api")
        assert result["Response"]["success"] is True
        assert mock_sleep.called


@then("retry the request up to a maximum number of times")
def retry_max_times(mock_session):
    assert mock_session.request.call_count == 2


# --- Scenario: Retrying on 500 Internal Server Error ---

@given("the SmugMug API returns a 500 Internal Server Error")
def api_returns_500(mock_session):
    mock_session.request.side_effect = [
        make_response(500, text="Internal Server Error"),
        make_response(200, {"Response": {"success": True}}),
    ]


@then("the API client should retry the request after a delay")
def retry_after_delay(client, mock_session):
    with patch("src.api_client.time.sleep") as mock_sleep:
        result = client._request("GET", "/api")
        assert result["Response"]["success"] is True
        assert mock_session.request.call_count == 2
        assert mock_sleep.called


# --- Scenario: Failing after maximum retries ---

@given("the SmugMug API consistently returns a 503 error")
def api_consistently_503(mock_session):
    mock_session.request.return_value = make_response(503, text="Service Unavailable")


@when("the API client reaches the maximum retry limit")
def reaches_max_limit():
    pass


@then("it should raise an exception and halt the current operation")
def raise_exception(client):
    with patch("src.api_client.time.sleep") as mock_sleep:
        with pytest.raises(SmugMugAPIError) as exc_info:
            client._request("GET", "/api")
        assert "Max retries exceeded" in str(exc_info.value)


# --- Scenarios: Retrying file download on 429 rate limit & 500 server error ---

@given("a file download receives a 429 Too Many Requests response")
def download_receives_429(mock_session):
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.is_redirect = False

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.headers = {"Content-Length": "5"}
    resp_200.is_redirect = False
    resp_200.iter_content.return_value = [b"hello"]

    mock_session.get.side_effect = [resp_429, resp_200]


@given("a file download receives a 500 Internal Server Error response")
def download_receives_500(mock_session):
    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.is_redirect = False

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.headers = {"Content-Length": "5"}
    resp_200.is_redirect = False
    resp_200.iter_content.return_value = [b"hello"]

    mock_session.get.side_effect = [resp_500, resp_200]


@when("the download client retries with exponential backoff")
def download_client_retries(client, tmp_path):
    dest_path = str(tmp_path / "downloaded.jpg")
    with patch("src.api_client.time.sleep") as mock_sleep:
        with patch("src.api_client.PreparedRequest") as mock_prepared:
            mock_prepared.return_value.url = "https://photos.smugmug.com/img.jpg"
            result = client.download_file("https://photos.smugmug.com/img.jpg", dest_path)
            pytest.download_result = result
            pytest.mock_sleep_called = mock_sleep.called


@then("the file download should succeed after the delay")
def download_succeeds_after_delay(mock_session):
    assert pytest.download_result is True
    assert pytest.mock_sleep_called is True
    assert mock_session.get.call_count == 2


@then("the file download should succeed after the server recovers")
def download_succeeds_after_server_recovers(mock_session):
    assert pytest.download_result is True
    assert pytest.mock_sleep_called is True
    assert mock_session.get.call_count == 2

