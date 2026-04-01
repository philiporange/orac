"""Tests for read_file and list_directory skills.

Covers text reading, binary detection, truncation, glob filtering,
recursive listing, and error cases.
"""

import pytest
from pathlib import Path

from orac.skills.read_file import execute as read_file, _is_binary
from orac.skills.list_directory import execute as list_directory


@pytest.fixture
def sample_dir(tmp_path):
    """Create a sample directory structure for testing."""
    # Text files
    (tmp_path / "hello.txt").write_text("Hello, world!")
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3\n4,5,6")
    (tmp_path / "script.py").write_text("print('hello')\n")

    # Subdirectory
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content")
    (sub / "config.yaml").write_text("key: value\n")

    # Binary file (contains null bytes)
    (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

    # Empty file
    (tmp_path / "empty.txt").write_text("")

    return tmp_path


# ── read_file ──────────────────────────────────────────────────────


class TestReadFile:
    def test_reads_text_file(self, sample_dir):
        result = read_file({"path": str(sample_dir / "hello.txt")})
        assert isinstance(result, dict)
        assert result["content"] == "Hello, world!"
        assert result["size_bytes"] == 13
        assert str(sample_dir / "hello.txt") in result["path"]

    def test_reads_empty_file(self, sample_dir):
        result = read_file({"path": str(sample_dir / "empty.txt")})
        assert isinstance(result, dict)
        assert result["content"] == ""
        assert result["size_bytes"] == 0

    def test_truncates_large_content(self, sample_dir):
        large = sample_dir / "large.txt"
        large.write_text("x" * 1000)
        result = read_file({"path": str(large), "max_chars": 100})
        assert isinstance(result, dict)
        assert "[TRUNCATED" in result["content"]
        # Content before truncation notice should be exactly max_chars
        assert result["content"].startswith("x" * 100)

    def test_detects_binary_by_extension(self, sample_dir):
        result = read_file({"path": str(sample_dir / "image.png")})
        assert isinstance(result, str)
        assert "binary" in result.lower()
        assert "transcribe_file" in result

    def test_detects_binary_by_null_bytes(self, tmp_path):
        binary_file = tmp_path / "mystery.dat"
        binary_file.write_bytes(b"some text\x00more data")
        result = read_file({"path": str(binary_file)})
        assert isinstance(result, str)
        assert "binary" in result.lower()

    def test_file_not_found(self):
        result = read_file({"path": "/nonexistent/file.txt"})
        assert isinstance(result, str)
        assert "Error" in result

    def test_not_a_file(self, sample_dir):
        result = read_file({"path": str(sample_dir / "subdir")})
        assert isinstance(result, str)
        assert "Error" in result

    def test_expands_home_dir(self, tmp_path, monkeypatch):
        test_file = tmp_path / "test.txt"
        test_file.write_text("home content")
        monkeypatch.setenv("HOME", str(tmp_path))
        result = read_file({"path": "~/test.txt"})
        assert isinstance(result, dict)
        assert result["content"] == "home content"


class TestIsBinary:
    def test_known_binary_extensions(self, tmp_path):
        for ext in [".png", ".pdf", ".zip", ".exe", ".mp4"]:
            f = tmp_path / f"test{ext}"
            f.write_bytes(b"content")
            assert _is_binary(f) is True

    def test_text_extensions(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("plain text")
        assert _is_binary(f) is False

    def test_null_byte_detection(self, tmp_path):
        f = tmp_path / "test.unknown"
        f.write_bytes(b"text\x00binary")
        assert _is_binary(f) is True


# ── list_directory ─────────────────────────────────────────────────


class TestListDirectory:
    def test_lists_directory(self, sample_dir):
        result = list_directory({"path": str(sample_dir)})
        assert isinstance(result, dict)
        assert result["count"] > 0
        assert "hello.txt" in result["listing"]
        assert "subdir/" in result["listing"]

    def test_glob_filter(self, sample_dir):
        result = list_directory({"path": str(sample_dir), "pattern": "*.py"})
        assert isinstance(result, dict)
        assert "script.py" in result["listing"]
        assert "hello.txt" not in result["listing"]

    def test_recursive_listing(self, sample_dir):
        result = list_directory({"path": str(sample_dir), "recursive": True})
        assert isinstance(result, dict)
        assert "nested.txt" in result["listing"]

    def test_recursive_with_pattern(self, sample_dir):
        result = list_directory({
            "path": str(sample_dir),
            "pattern": "*.yaml",
            "recursive": True,
        })
        assert isinstance(result, dict)
        assert "config.yaml" in result["listing"]
        assert "hello.txt" not in result["listing"]

    def test_empty_directory(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = list_directory({"path": str(empty)})
        assert isinstance(result, dict)
        assert result["count"] == 0
        assert "empty" in result["listing"].lower()

    def test_no_matching_pattern(self, sample_dir):
        result = list_directory({"path": str(sample_dir), "pattern": "*.xyz"})
        assert isinstance(result, dict)
        assert result["count"] == 0

    def test_directory_not_found(self):
        result = list_directory({"path": "/nonexistent/dir"})
        assert isinstance(result, str)
        assert "Error" in result

    def test_not_a_directory(self, sample_dir):
        result = list_directory({"path": str(sample_dir / "hello.txt")})
        assert isinstance(result, str)
        assert "Error" in result

    def test_shows_file_sizes(self, sample_dir):
        result = list_directory({"path": str(sample_dir)})
        assert "FILE" in result["listing"]
        assert "DIR" in result["listing"]
