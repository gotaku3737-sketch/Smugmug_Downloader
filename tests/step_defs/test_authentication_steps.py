"""Step definitions for Authentication feature."""

import os
import json
from unittest.mock import patch, MagicMock
import pytest
from pytest_bdd import scenarios, given, when, then

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
