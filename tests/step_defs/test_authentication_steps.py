"""Step definitions for Authentication feature."""

import os
import json
from unittest.mock import patch, MagicMock
import pytest
from pytest_bdd import scenarios, given, when, then, parsers

# Load scenarios
scenarios('../../features/authentication.feature')


@pytest.fixture
def mock_token_file(tmp_path):
    token_path = tmp_path / "tokens.json"
    return str(token_path)


# --- Scenario: Loading cached tokens ---

@given("a valid cached OAuth token exists")
def valid_cached_token(mock_token_file):
    with open(mock_token_file, "w") as f:
        json.dump({"oauth_token": "token123", "oauth_token_secret": "secret123"}, f)


@when("the application starts")
def app_starts():
    pass  # Action handled in the then step for testing


@then("the application should not prompt for a browser login")
def no_browser_prompt(mock_token_file):
    from src.auth import load_cached_tokens
    with patch("src.auth.TOKEN_FILE", mock_token_file):
        tokens = load_cached_tokens()
        assert tokens is not None
        assert tokens["oauth_token"] == "token123"


@then("the application should successfully make an authenticated API request")
def auth_api_request():
    from src.auth import get_oauth_session
    # We mock get_oauth_session to verify it returns a session without calling authorize()
    with patch("src.auth.authorize") as mock_authorize:
        with patch("src.auth.load_cached_tokens", return_value={"oauth_token": "a", "oauth_token_secret": "b"}):
            session = get_oauth_session("key", "secret")
            assert mock_authorize.call_count == 0
            assert session is not None


# --- Scenario: Missing cached tokens requires login ---

@given("no cached OAuth tokens exist")
def no_cached_tokens(mock_token_file):
    if os.path.exists(mock_token_file):
        os.remove(mock_token_file)


@then("the application should prompt the user to authorize via a browser")
def prompt_for_browser(mock_token_file):
    from src.auth import get_oauth_session
    with patch("src.auth.TOKEN_FILE", mock_token_file):
        with patch("src.auth.authorize") as mock_authorize:
            mock_authorize.return_value = {"oauth_token": "new", "oauth_token_secret": "new"}
            get_oauth_session("key", "secret")
            assert mock_authorize.called


@then("upon successful authorization, the application should cache the tokens for future use")
def cache_tokens(mock_token_file):
    from src.auth import save_tokens
    with patch("src.auth.TOKEN_FILE", mock_token_file):
        save_tokens({"oauth_token": "new", "oauth_token_secret": "new"})
        assert os.path.exists(mock_token_file)


# --- Scenario: API Key and Secret resolution ---

@given("environment variables for API key and secret are set")
def env_vars_set(monkeypatch):
    monkeypatch.setenv("SMUGMUG_API_KEY", "env_key")
    monkeypatch.setenv("SMUGMUG_API_SECRET", "env_secret")


@when("the application initializes configuration")
def init_config():
    pass


@then("it should use the environment variables over static constants")
def use_env_vars():
    from src.config import get_api_credentials
    key, secret = get_api_credentials()
    assert key == "env_key"
    assert secret == "env_secret"


# --- Scenarios: PIN validation and secure file permission caching ---

@given("the user is prompted for an OAuth verification code")
def prompt_oauth_code():
    pass


@when(parsers.parse('the user enters an invalid verification code "{code}"'))
def enter_invalid_code(code):
    pytest.test_verifier_code = code


@then("the application should reject the code and halt execution")
def reject_code_halt():
    from src.auth import authorize
    with patch("src.auth.console") as mock_console:
        mock_console.input.return_value = pytest.test_verifier_code
        with patch("src.auth.OAuth1Session") as mock_oauth_cls:
            mock_oauth_inst = mock_oauth_cls.return_value
            mock_oauth_inst.fetch_request_token.return_value = {
                "oauth_token": "rt", "oauth_token_secret": "rts"
            }
            mock_oauth_inst.authorization_url.return_value = "https://api.smugmug.com/auth"
            with pytest.raises(SystemExit) as exc_info:
                authorize("api_key", "api_secret")
            assert exc_info.value.code == 1


@when(parsers.parse('the user enters a valid 6-digit code "{code}"'))
def enter_valid_code(code):
    pytest.test_verifier_code = code


@then("the application should proceed to exchange it for an access token")
def proceed_exchange_token():
    from src.auth import authorize
    with patch("src.auth.console") as mock_console:
        mock_console.input.return_value = pytest.test_verifier_code
        with patch("src.auth.OAuth1Session") as mock_oauth_cls:
            mock_oauth_inst = mock_oauth_cls.return_value
            mock_oauth_inst.fetch_request_token.return_value = {
                "oauth_token": "rt", "oauth_token_secret": "rts"
            }
            mock_oauth_inst.authorization_url.return_value = "https://api.smugmug.com/auth"
            mock_oauth_inst.fetch_access_token.return_value = {
                "oauth_token": "access_token", "oauth_token_secret": "access_secret"
            }
            with patch("src.auth.save_tokens") as mock_save:
                tokens = authorize("api_key", "api_secret")
                assert tokens["oauth_token"] == "access_token"
                assert mock_save.called


@given("new OAuth tokens are received")
def new_tokens_received():
    pytest.new_tokens = {"oauth_token": "tok", "oauth_token_secret": "sec"}


@when("the tokens are saved to disk")
def save_tokens_to_disk(mock_token_file):
    from src.auth import save_tokens
    with patch("src.auth.TOKEN_FILE", mock_token_file):
        save_tokens(pytest.new_tokens)


@then("the token file should have restricted permissions 0600")
def verify_restricted_permissions(mock_token_file):
    import stat
    mode = stat.S_IMODE(os.stat(mock_token_file).st_mode)
    assert mode == 0o600

