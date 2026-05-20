Feature: MD5 Integrity Verification
  As a user
  I want the system to verify the MD5 checksum of downloaded files
  So that corrupted downloads are detected and automatically retried

  Scenario: Successful download with matching MD5
    Given a remote file has MD5 checksum "abcde12345"
    When the file is downloaded and its MD5 matches "abcde12345"
    Then the file should be saved and marked as done in the tracker

  Scenario: Corrupted download with mismatched MD5
    Given a remote file has MD5 checksum "correct_md5"
    When the file is downloaded but its MD5 is "corrupted_md5"
    Then the system should reject the file, delete it, and retry the download
