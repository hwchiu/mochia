# tests/test_find_duplicates.py
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from find_duplicates import sha256_file, find_duplicates  # noqa: E402


class TestSha256File:
    def test_same_content_same_hash(self, tmp_path: Path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"hello world")
        b.write_bytes(b"hello world")
        assert sha256_file(a) == sha256_file(b)

    def test_different_content_different_hash(self, tmp_path: Path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_bytes(b"hello")
        b.write_bytes(b"world")
        assert sha256_file(a) != sha256_file(b)

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        assert sha256_file(f) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestFindDuplicatesFast:
    """Fast mode: key = filename|size — no file reads."""

    def test_same_name_same_size_are_duplicates(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "img.jpg").write_bytes(b"data")
        (sub / "img.jpg").write_bytes(b"data")
        result = find_duplicates(tmp_path, recursive=True, deep=False)
        assert len(result) == 1

    def test_same_name_different_size_not_duplicate(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "img.jpg").write_bytes(b"aaaa")
        (sub / "img.jpg").write_bytes(b"bb")
        result = find_duplicates(tmp_path, recursive=True, deep=False)
        assert result == {}

    def test_no_duplicates_returns_empty(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"aaa")
        (tmp_path / "b.txt").write_bytes(b"aaa")  # same content, different name
        result = find_duplicates(tmp_path, recursive=True, deep=False)
        assert result == {}

    def test_no_recursive_ignores_subdirs(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "img.jpg").write_bytes(b"data")
        (sub / "img.jpg").write_bytes(b"data")
        result = find_duplicates(tmp_path, recursive=False, deep=False)
        assert result == {}


class TestFindDuplicatesDeep:
    """Deep mode: key = sha256 — reads file content."""

    def test_same_content_are_duplicates(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"same")
        (tmp_path / "b.txt").write_bytes(b"same")
        result = find_duplicates(tmp_path, recursive=True, deep=True)
        assert len(result) == 1

    def test_different_name_same_content_is_duplicate(self, tmp_path: Path):
        (tmp_path / "original.jpg").write_bytes(b"pixels")
        (tmp_path / "copy.jpg").write_bytes(b"pixels")
        result = find_duplicates(tmp_path, recursive=True, deep=True)
        assert len(result) == 1

    def test_no_duplicates_returns_empty(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"aaa")
        (tmp_path / "b.txt").write_bytes(b"bbb")
        result = find_duplicates(tmp_path, recursive=True, deep=True)
        assert result == {}
