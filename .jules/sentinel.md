## 2024-05-10 - [Path Traversal in API Filenames]
**Vulnerability:** The application was directly using the `FileName` field from the SmugMug API to construct local file paths for downloads without sanitization, allowing for potential path traversal attacks (e.g., `../../../etc/passwd`).
**Learning:** External API responses, even from trusted or authenticated sources, must not be implicitly trusted when interacting with the local filesystem. Malicious or malformed data could be returned by the API, intentionally or accidentally.
**Prevention:** Always sanitize filenames derived from external sources using `os.path.basename` (after converting any backslashes to forward slashes to handle Windows-style paths) before using them to write files to disk.
