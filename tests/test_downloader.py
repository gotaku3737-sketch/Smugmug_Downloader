"""Unit tests for the downloader utility functions."""

import pytest
from src.downloader import sanitize_dirname, extract_image_key, extract_album_key, get_image_filename

class TestSanitizeDirname:
    def test_normal_name(self):
        assert sanitize_dirname("Vacation 2023") == "Vacation 2023"

    def test_unsafe_characters(self):
        # r'[<>:"/\\|?*]'
        assert sanitize_dirname("Album: Summer/Winter?") == "Album- Summer-Winter"

    def test_multiple_unsafe_characters(self):
        assert sanitize_dirname("Album:::Test") == "Album-Test"

    def test_leading_trailing_special_characters(self):
        assert sanitize_dirname(". -Album. ") == "Album"

    def test_empty_or_only_unsafe(self):
        assert sanitize_dirname("???") == "untitled"
        assert sanitize_dirname("") == "untitled"

class TestExtractKey:
    def test_extract_image_key_direct(self):
        assert extract_image_key({"ImageKey": "IMG123"}) == "IMG123"

    def test_extract_image_key_from_uri(self):
        assert extract_image_key({"Uri": "/api/v2/image/IMG456"}) == "IMG456"

    def test_extract_image_key_empty(self):
        assert extract_image_key({}) == ""

    def test_extract_album_key_direct(self):
        assert extract_album_key({"AlbumKey": "ALB123"}) == "ALB123"

    def test_extract_album_key_from_uri(self):
        assert extract_album_key({"Uri": "/api/v2/album/ALB456"}) == "ALB456"

    def test_extract_album_key_empty(self):
        assert extract_album_key({}) == ""

class TestGetImageFilename:
    def test_with_filename(self):
        assert get_image_filename({"FileName": "vacation.jpg"}) == "vacation.jpg"

    def test_path_traversal_unix(self):
        assert get_image_filename({"FileName": "../../../etc/passwd"}) == "passwd"

    def test_path_traversal_windows(self):
        assert get_image_filename({"FileName": "..\\..\\windows\\system32\\cmd.exe"}) == "cmd.exe"

    def test_without_filename_with_key_and_format(self):
        assert get_image_filename({"ImageKey": "IMG1", "Format": "PNG"}) == "IMG1.png"

    def test_format_case_insensitivity(self):
        assert get_image_filename({"ImageKey": "IMG1", "Format": "png"}) == "IMG1.png"

    @pytest.mark.parametrize("fmt,expected_ext", [
        ("JPG", "jpg"),
        ("JPEG", "jpg"),
        ("PNG", "png"),
        ("GIF", "gif"),
        ("HEIC", "heic"),
        ("MP4", "mp4"),
        ("MOV", "mov"),
        ("TIFF", "tiff"),
        ("TIF", "tif"),
    ])
    def test_format_mappings(self, fmt, expected_ext):
        assert get_image_filename({"ImageKey": "IMG1", "Format": fmt}) == f"IMG1.{expected_ext}"

    def test_unknown_format_defaults_to_jpg(self):
        assert get_image_filename({"ImageKey": "IMG1", "Format": "RAW"}) == "IMG1.jpg"

    def test_missing_format_defaults_to_jpg(self):
        assert get_image_filename({"ImageKey": "IMG1"}) == "IMG1.jpg"
