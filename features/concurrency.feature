Feature: Concurrent Downloads
  As a user
  I want the system to download files concurrently
  So that the download process is faster

  Scenario: Specifying worker count via CLI
    Given the user specifies worker count "5" via CLI
    When the CLI executes the download command
    Then the download should run using "5" concurrent workers
