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
