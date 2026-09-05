Feature: API Resilience
  As a system
  I want to automatically handle transient API errors
  So that long-running downloads do not crash midway

  Scenario: Retrying on 429 Too Many Requests
    Given the SmugMug API returns a 429 Too Many Requests error
    When the API client receives the response
    Then the API client should wait using exponential backoff
    And retry the request up to a maximum number of times

  Scenario: Retrying on 500 Internal Server Error
    Given the SmugMug API returns a 500 Internal Server Error
    When the API client receives the response
    Then the API client should retry the request after a delay
    
  Scenario: Failing after maximum retries
    Given the SmugMug API consistently returns a 503 error
    When the API client reaches the maximum retry limit
    Then it should raise an exception and halt the current operation

  Scenario: Retrying file download on 429 rate limit
    Given a file download receives a 429 Too Many Requests response
    When the download client retries with exponential backoff
    Then the file download should succeed after the delay

  Scenario: Retrying file download on 500 server error
    Given a file download receives a 500 Internal Server Error response
    When the download client retries with exponential backoff
    Then the file download should succeed after the server recovers
