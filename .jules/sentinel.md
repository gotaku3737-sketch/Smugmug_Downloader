## 2024-05-09 - Path Traversal in Image Filenames
**Vulnerability:** The API returned attribute `FileName` was used without any sanitization in `get_image_filename()`. An attacker controlling the SmugMug API or the payload could provide `FileName: "../../../etc/passwd"`, causing the engine to write the downloaded file outside of the intended album download directory, which leads to path traversal.
**Learning:** External API data should never be trusted when constructing file paths on the local file system. Even if it is a 3rd party API, we must sanitize paths (such as `FileName`) locally before downloading them.
**Prevention:** Use `os.path.basename(filename.replace("\\", "/"))` to strictly extract just the intended filename component of the provided payload, blocking both Unix and Windows directory traversal characters.

## 2024-05-13 - Path Traversal Bypass via Empty Basename
**Vulnerability:** The fix for path traversal in `get_image_filename()` used `os.path.basename` to extract a safe filename. However, if an attacker provided "." or ".." as the `FileName` parameter, `os.path.basename` would simply return "." or "..", allowing them to traverse up the directory tree or pollute the directory with non-image names.
**Learning:** `os.path.basename` is not always sufficient for stripping directory traversal strings because "." and ".." are considered valid file basenames in Unix paths. Always sanitize and reject these specific paths after extracting the basename.
**Prevention:** In addition to using `os.path.basename`, explicitly check `if filename in (".", "..")` and reject those values to ensure only valid filenames are created.

## 2026-05-14 - TOCTOU Vulnerability in OAuth Token Storage
**Vulnerability:** In `src/auth.py`, `save_tokens` saved OAuth tokens containing secrets to a file using the standard `open(TOKEN_FILE, "w")` followed by `os.chmod(TOKEN_FILE, 0o600)`. This created a Time-Of-Check to Time-Of-Use (TOCTOU) race condition where the token file was briefly written with default system permissions (like `0o644`) before being restricted.
**Learning:** Saving sensitive files by first creating them with wide permissions and modifying them afterwards is insecure, as an attacker or unauthorized user on the system might read the token during the brief window before `chmod` is called.
**Prevention:** Use `os.open` with the flags `os.O_CREAT | os.O_WRONLY | os.O_TRUNC` and explicit `0o600` mode to ensure the file is created with secure permissions right from the start.
