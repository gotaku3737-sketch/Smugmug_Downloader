Feature: CLI Workflows
  As a user
  I want a powerful command-line interface
  So that I can control what gets downloaded

  Scenario: Listing albums
    Given the user has authenticated successfully
    When the user runs the CLI with "--list-albums"
    Then the CLI should display a list of all albums
    And no files should be downloaded

  Scenario: Downloading a specific album
    Given the user specifies an album name "Vacation" via CLI
    When the CLI executes the download command
    Then only the "Vacation" album should be downloaded

  Scenario: Checking status
    Given some files have been downloaded
    When the user runs the CLI with "--status"
    Then the CLI should display the current number of tracked files
