Feature: Download Tracking
  As a user
  I want the system to track downloaded files
  So that interrupted downloads can resume without re-downloading everything

  Scenario: Initial download creates tracker state
    Given an empty download directory
    When a file "photo.jpg" is successfully downloaded
    Then the file should be saved to the directory
    And the tracker state file should record "photo.jpg" as downloaded

  Scenario: Skipping already downloaded files
    Given a tracker state file indicating "photo.jpg" is downloaded
    And the file "photo.jpg" exists in the download directory
    When the system attempts to download "photo.jpg"
    Then the system should skip the download

  Scenario: Resetting download state
    Given a tracker state file exists with tracked files
    When the user requests to reset the state
    Then the tracker state file should be cleared or deleted
