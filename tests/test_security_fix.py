import pytest
from unittest.mock import MagicMock, patch
import os
import sys

# Mock rich before importing modules that use it
mock_rich = MagicMock()
sys.modules["rich"] = mock_rich
sys.modules["rich.console"] = mock_rich.console
sys.modules["requests_oauthlib"] = MagicMock()

import src.config
import src.auth

def test_get_api_credentials_uses_password_masking():
    # In src.config, Console is imported inside the function
    # from rich.console import Console
    # Since we mocked sys.modules["rich.console"], we can patch that
    with patch("rich.console.Console") as MockConsole:
        mock_console_inst = MockConsole.return_value
        mock_console_inst.input.return_value = "secret"

        # Ensure env vars are not set to trigger prompt
        with patch.dict(os.environ, {}, clear=True):
            # Also ensure static constants are empty
            with patch("src.config.API_KEY", ""), patch("src.config.API_SECRET", ""):
                src.config.get_api_credentials()

        # Check that input was called with password=True
        assert mock_console_inst.input.call_count == 2
        for call in mock_console_inst.input.call_args_list:
            assert call.kwargs.get("password") is True

def test_authorize_uses_password_masking_for_verifier():
    # In src.auth, console = Console() is at module level
    with patch("src.auth.console") as mock_console:
        mock_console.input.return_value = "123456"

        # Mock OAuth1Session to avoid network calls
        with patch("src.auth.OAuth1Session") as MockOAuth:
            mock_oauth_inst = MockOAuth.return_value
            mock_oauth_inst.fetch_request_token.return_value = {
                "oauth_token": "rt", "oauth_token_secret": "rts"
            }
            mock_oauth_inst.authorization_url.return_value = "http://auth"
            mock_oauth_inst.fetch_access_token.return_value = {
                "oauth_token": "at", "oauth_token_secret": "ats"
            }

            with patch("src.auth.save_tokens"):
                src.auth.authorize("key", "secret")

        # Check that verifier input was called with password=True
        mock_console.input.assert_called_once()
        assert mock_console.input.call_args.kwargs.get("password") is True

def test_save_tokens_uses_secure_permissions():
    tokens = {"oauth_token": "at", "oauth_token_secret": "ats"}

    with patch("os.open") as mock_open:
        mock_open.return_value = 42 # dummy fd
        with patch("os.fdopen") as mock_fdopen:
            mock_file = MagicMock()
            mock_fdopen.return_value.__enter__.return_value = mock_file

            src.auth.save_tokens(tokens)

            mock_open.assert_called_once_with(
                src.auth.TOKEN_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                0o600
            )
            mock_fdopen.assert_called_once_with(42, "w")

def test_download_file_prevents_ssrf():
    import sys
    from unittest.mock import MagicMock
    from src.api_client import SmugMugClient
    from requests_oauthlib import OAuth1Session

    # Create a dummy session and client
    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    # Test non-HTTPS URL
    assert client.download_file("http://api.smugmug.com/image.jpg", "/tmp/out") is False
    assert mock_session.get.call_count == 0

    # Test non-SmugMug hostname
    assert client.download_file("https://attacker.com/image.jpg", "/tmp/out") is False
    assert mock_session.get.call_count == 0

    # Test valid SmugMug hostname but no subdomain
    assert client.download_file("https://smugmug.com.attacker.com/image.jpg", "/tmp/out") is False
    assert mock_session.get.call_count == 0

    # Test valid subdomains (should attempt request, but since we mock, we catch the exception or setup mock return)
    mock_session.get.side_effect = Exception("Should try to download")
    try:
        client.download_file("https://api.smugmug.com/image.jpg", "/tmp/out")
    except Exception:
        pass
    # Depending on retry logic, it might catch it or not. The point is it didn't return False early.
    assert mock_session.get.call_count > 0

def test_download_file_prevents_redirect_ssrf():
    from src.api_client import SmugMugClient
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    # Mock responses to simulate a redirect to an attacker domain
    class MockRedirectResponse:
        def __init__(self, is_redirect, location=None, status=200):
            self.is_redirect = is_redirect
            self.headers = {"Location": location} if location else {}
            self.status_code = status
        def raise_for_status(self):
            pass

    # First request returns a 302 redirect to attacker.com
    # The while loop will check the new URL and reject it
    mock_session.get.return_value = MockRedirectResponse(True, "https://attacker.com/image.jpg", 302)

    result = client.download_file("https://api.smugmug.com/image.jpg", "/tmp/out")

    # Should be rejected because it redirected to attacker.com
    assert result is False

    # Ensure it only made the FIRST request and didn't follow the redirect!
    assert mock_session.get.call_count == 1
    mock_session.get.assert_called_with("https://api.smugmug.com/image.jpg", stream=True, timeout=60, allow_redirects=False)

def test_request_prevents_ssrf_in_endpoint():
    from src.api_client import SmugMugClient, SmugMugAPIError
    from unittest.mock import MagicMock
    import pytest

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    # An attacker controls endpoint (e.g. via NextPage)
    malicious_endpoint = "@attacker.com/api/v2"

    with pytest.raises(SmugMugAPIError) as exc_info:
        client._request("GET", malicious_endpoint)

    assert "Invalid endpoint" in str(exc_info.value)
    assert mock_session.request.call_count == 0

def test_request_prevents_redirect_ssrf():
    from src.api_client import SmugMugClient, SmugMugAPIError
    from unittest.mock import MagicMock
    import pytest

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    class MockRedirectResponse:
        def __init__(self, is_redirect, location=None, status=302):
            self.is_redirect = is_redirect
            self.headers = {"Location": location} if location else {}
            self.status_code = status
        def json(self): return {}

    # Simulate a redirect to an attacker's domain
    mock_session.request.return_value = MockRedirectResponse(True, "https://attacker.com/api", 302)

    with pytest.raises(SmugMugAPIError) as exc_info:
        client._request("GET", "/test")

    assert "untrusted URL" in str(exc_info.value) or "Security Error" in str(exc_info.value)

    # Check that allow_redirects=False was used
    assert mock_session.request.call_count == 1
    kwargs = mock_session.request.call_args[1]
    assert kwargs.get("allow_redirects") is False

def test_urlparse_requests_discrepancy_bypass():
    from src.api_client import SmugMugClient
    from unittest.mock import MagicMock
    import pytest

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    # Attack URL that bypasses simple urlparse but would be sent to attacker.com by requests
    attack_url = "https://attacker.com\\@smugmug.com/image.jpg"

    # Should be rejected
    assert client.download_file(attack_url, "/tmp/out") is False
    assert mock_session.get.call_count == 0

def test_urlparse_requests_discrepancy_redirect_bypass():
    from src.api_client import SmugMugClient, SmugMugAPIError
    from unittest.mock import MagicMock
    import pytest

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    class MockRedirectResponse:
        def __init__(self, is_redirect, location=None, status=302):
            self.is_redirect = is_redirect
            self.headers = {"Location": location} if location else {}
            self.status_code = status
        def json(self): return {}

    attack_url = "https://attacker.com\\@smugmug.com/api"
    mock_session.request.return_value = MockRedirectResponse(True, attack_url, 302)

    with pytest.raises(SmugMugAPIError) as exc_info:
        client._request("GET", "/test")

    assert "untrusted URL" in str(exc_info.value) or "Security Error" in str(exc_info.value)

def test_auth_timeouts_applied():
    from src.auth import authorize
    from unittest.mock import patch, MagicMock

    with patch("src.auth.console") as mock_console:
        mock_console.input.return_value = "123456"

        with patch("src.auth.OAuth1Session") as MockOAuth:
            mock_oauth_inst = MockOAuth.return_value
            mock_oauth_inst.fetch_request_token.return_value = {
                "oauth_token": "rt", "oauth_token_secret": "rts"
            }
            mock_oauth_inst.authorization_url.return_value = "http://auth"
            mock_oauth_inst.fetch_access_token.return_value = {
                "oauth_token": "at", "oauth_token_secret": "ats"
            }

            with patch("src.auth.save_tokens"):
                authorize("key", "secret")

            # Verify fetch_request_token was called with timeout=30
            mock_oauth_inst.fetch_request_token.assert_called_once()
            args, kwargs = mock_oauth_inst.fetch_request_token.call_args
            assert kwargs.get("timeout") == 30

            # Verify fetch_access_token was called with timeout=30
            mock_oauth_inst.fetch_access_token.assert_called_once()
            args, kwargs = mock_oauth_inst.fetch_access_token.call_args
            assert kwargs.get("timeout") == 30

def test_download_file_uses_mkstemp():
    import sys
    from unittest.mock import MagicMock, patch
    from src.api_client import SmugMugClient

    mock_session = MagicMock()
    client = SmugMugClient(mock_session)

    # Mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Length": "10"}
    mock_response.is_redirect = False
    mock_response.iter_content.return_value = [b"1234567890"]
    mock_session.get.return_value = mock_response

    with patch("tempfile.mkstemp") as mock_mkstemp, patch("os.fdopen") as mock_fdopen, patch("os.replace") as mock_replace, patch("os.makedirs"):
        mock_mkstemp.return_value = (42, "/tmp/some_dir/mock.tmp")
        mock_file = MagicMock()
        mock_fdopen.return_value.__enter__.return_value = mock_file

        result = client.download_file("https://api.smugmug.com/image.jpg", "/tmp/some_dir/out.jpg")

        assert result is True
        mock_mkstemp.assert_called_once_with(dir="/tmp/some_dir", suffix=".tmp")
        mock_fdopen.assert_called_once_with(42, "wb")
        mock_replace.assert_called_once_with("/tmp/some_dir/mock.tmp", "/tmp/some_dir/out.jpg")

def test_verify_md5_usedforsecurity_false():
    import tempfile
    import os
    from unittest.mock import patch
    from src.api_client import verify_md5

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"testdata")
        filepath = f.name

    try:
        with patch("src.api_client.hashlib.md5") as mock_md5:
            # We must mock it so it returns something that has 'update' and 'hexdigest'
            mock_hash_obj = mock_md5.return_value
            mock_hash_obj.hexdigest.return_value = "dummy"

            verify_md5(filepath, "dummy")

            # Check that it tried to call md5(usedforsecurity=False)
            mock_md5.assert_called_once_with(usedforsecurity=False)
    finally:
        os.remove(filepath)

def test_downloader_rich_terminal_injection():
    # Remove the global mock of rich temporarily so we can import src.downloader properly
    import sys
    orig_rich = sys.modules.pop("rich", None)
    orig_rich_console = sys.modules.pop("rich.console", None)

    try:
        from src.downloader import list_albums, run_download
        from src.tracker import DownloadTracker
        from unittest.mock import MagicMock, patch
        from rich.markup import escape

        # Create dummy client
        mock_client = MagicMock()
        mock_client.get_authenticated_user.return_value = {
            "NickName": "[red]hacker[/red]",
            "Name": "[link=http://attacker.com]malicious[/link]"
        }

        mock_client.get_user_albums.return_value = [{
            "Name": "[invalid tag] album",
            "AlbumKey": "123",
            "ImageCount": 5,
            "SecurityType": "Public"
        }]

        # We'll patch Table to capture what gets added to the table
        with patch("src.downloader.Table") as MockTable:
            mock_table_instance = MockTable.return_value

            with patch("src.downloader.console") as mock_console:
                list_albums(mock_client)

                # Check the table.add_row arguments were escaped
                mock_table_instance.add_row.assert_called_once()
                args = mock_table_instance.add_row.call_args[0]

                # str(idx), escape(Name), escape(Key), str(ImageCount), escape(SecurityType)
                assert escape("[invalid tag] album") in args

                # Check the print statement for the user info was escaped
                printed_strs = [call[0][0] for call in mock_console.print.call_args_list if isinstance(call[0][0], str)]
                user_info_str = next(s for s in printed_strs if "Logged in as" in s)

                assert escape("[red]hacker[/red]") in user_info_str
                assert escape("[link=http://attacker.com]malicious[/link]") in user_info_str
    finally:
        if orig_rich: sys.modules["rich"] = orig_rich
        if orig_rich_console: sys.modules["rich.console"] = orig_rich_console

def test_downloader_progress_injection():
    # Remove the global mock of rich temporarily
    import sys
    orig_rich = sys.modules.pop("rich", None)
    orig_rich_console = sys.modules.pop("rich.console", None)

    try:
        from src.downloader import download_album_images, download_image_worker
        from src.tracker import DownloadTracker
        from unittest.mock import MagicMock, patch
        from rich.markup import escape
        import tempfile

        mock_client = MagicMock()
        mock_client.get_album_images.return_value = [{
            "ImageKey": "img1",
            "FileName": "[red]malicious[/red].jpg"
        }]
        mock_tracker = MagicMock()
        mock_tracker.is_album_done.return_value = False
        mock_tracker.is_image_done.return_value = False

        mock_progress = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            download_album_images(mock_client, mock_tracker, {"Name": "[bad] album"}, tmpdir, "123", mock_progress, 0, workers=1)

            # Verify album_task_id was created with escaped album name
            mock_progress.add_task.assert_called()
            add_task_calls = mock_progress.add_task.call_args_list

            album_task_call = next(call for call in add_task_calls if "📷" in call[0][0])
            assert escape("[bad] album") in album_task_call[0][0]

            # Since the workers run in thread, to reliably test the sub_task_id escaping we can just call the worker directly
            mock_progress.reset_mock()
            download_image_worker(
                mock_client, mock_tracker, {"ImageKey": "img2", "FileName": "[bad]file.jpg"},
                "123", tmpdir, mock_progress, 1, 2
            )

            sub_task_call = next(call for call in mock_progress.add_task.call_args_list if "↳" in call[0][0])
            assert escape("[bad]file.jpg") in sub_task_call[0][0]
    finally:
        if orig_rich: sys.modules["rich"] = orig_rich
        if orig_rich_console: sys.modules["rich.console"] = orig_rich_console
