Feature: Authentication
  As a user
  I want the system to authenticate securely via OAuth 1.0a
  So that I can access my private SmugMug content without entering credentials every time

  Scenario: Loading cached tokens
    Given a valid cached OAuth token exists
    When the application starts
    Then the application should not prompt for a browser login
    And the application should successfully make an authenticated API request

  Scenario: Missing cached tokens requires login
    Given no cached OAuth tokens exist
    When the application starts
    Then the application should prompt the user to authorize via a browser
    And upon successful authorization, the application should cache the tokens for future use

  Scenario: API Key and Secret resolution
    Given environment variables for API key and secret are set
    When the application initializes configuration
    Then it should use the environment variables over static constants
