# find_duplicates Tool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `tools/find_duplicates.py` — a CLI tool that recursively scans a directory, finds duplicate files via SHA256, and writes a sorted report.

**Architecture:** Walk all files with `pathlib.Path.rglob`, hash each file with `hashlib.sha256` using streaming 64KB reads, group paths by hash, then filter for groups with 2+ files and write sorted output.

**Tech Stack:** Python stdlib only — `hashlib`, `pathlib`, `argparse`, `sys`

---

### Task 1: Core logic — hash and find duplicates

**Files:**
- Create: `tools/find_duplicates.py`
- Test: `tests/test_find_duplicates.py`

**Step 1: Create the test file with sys.path setup and first failing test**

```python
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
        # SHA256 of empty string is known
        assert sha256_file(f) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

**Step 2: Run to verify it fails**

```
pytest tests/test_find_duplicates.py::TestSha256File -v
```
Expected: `ImportError` — `find_duplicates` module not found

**Step 3: Create `tools/find_duplicates.py` with `sha256_file`**

```python
#!/usr/bin/env python3
"""
find_duplicates.py — Duplicate file finder
==========================================

Recursively scans a directory and finds duplicate files by SHA-256 hash.
Writes a sorted report listing every duplicate file grouped by hash.

Usage:
    python tools/find_duplicates.py <path>
    python tools/find_duplicates.py <path> --output report.txt
    python tools/find_duplicates.py <path> --no-recursive
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

_CHUNK = 65536  # 64 KB streaming reads


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_find_duplicates.py::TestSha256File -v
```
Expected: 3 PASS

**Step 5: Commit**

```bash
git add tools/find_duplicates.py tests/test_find_duplicates.py
git commit -m "feat: add sha256_file to find_duplicates tool"
```

---

### Task 2: `find_duplicates` function

**Files:**
- Modify: `tools/find_duplicates.py`
- Test: `tests/test_find_duplicates.py`

**Step 1: Add failing tests for `find_duplicates`**

Append to `tests/test_find_duplicates.py`:

```python
class TestFindDuplicates:
    def test_returns_only_duplicates(self, tmp_path: Path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        unique = tmp_path / "unique.txt"
        a.write_bytes(b"same")
        b.write_bytes(b"same")
        unique.write_bytes(b"different")
        result = find_duplicates(tmp_path, recursive=True)
        assert len(result) == 1
        hash_val, paths = list(result.items())[0]
        assert set(paths) == {a, b}

    def test_no_duplicates_returns_empty(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"aaa")
        (tmp_path / "b.txt").write_bytes(b"bbb")
        assert find_duplicates(tmp_path, recursive=True) == {}

    def test_recursive_finds_nested_duplicates(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_bytes(b"dup")
        (sub / "b.txt").write_bytes(b"dup")
        result = find_duplicates(tmp_path, recursive=True)
        assert len(result) == 1

    def test_no_recursive_ignores_subdirs(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_bytes(b"dup")
        (sub / "b.txt").write_bytes(b"dup")
        result = find_duplicates(tmp_path, recursive=False)
        assert result == {}
```

**Step 2: Run to verify they fail**

```
pytest tests/test_find_duplicates.py::TestFindDuplicates -v
```
Expected: `ImportError` for `find_duplicates`

**Step 3: Add `find_duplicates` to `tools/find_duplicates.py`**

```python
def find_duplicates(root: Path, *, recursive: bool) -> dict[str, list[Path]]:
    """Return a mapping of SHA-256 hex → list of duplicate paths (2+ files)."""
    glob = root.rglob("*") if recursive else root.glob("*")
    buckets: dict[str, list[Path]] = defaultdict(list)
    for path in glob:
        if path.is_file():
            buckets[sha256_file(path)].append(path)
    return {h: paths for h, paths in buckets.items() if len(paths) >= 2}
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_find_duplicates.py::TestFindDuplicates -v
```
Expected: 4 PASS

**Step 5: Commit**

```bash
git add tools/find_duplicates.py tests/test_find_duplicates.py
git commit -m "feat: add find_duplicates function"
```

---

### Task 3: `write_report` function

**Files:**
- Modify: `tools/find_duplicates.py`
- Test: `tests/test_find_duplicates.py`

**Step 1: Add failing test**

Append to `tests/test_find_duplicates.py`:

```python
from find_duplicates import sha256_file, find_duplicates, write_report  # noqa: E402 (update import)


class TestWriteReport:
    def test_report_sorted_by_hash(self, tmp_path: Path):
        output = tmp_path / "out.txt"
        # Build a fake duplicates dict with known hashes
        duplicates = {
            "zzzzzz": [Path("/b/file2.txt"), Path("/a/file1.txt")],
            "aaaaaa": [Path("/c/file3.txt"), Path("/d/file4.txt")],
        }
        write_report(duplicates, output)
        lines = output.read_text().splitlines()
        assert lines[0].startswith("aaaaaa")
        assert lines[2].startswith("zzzzzz")

    def test_report_format(self, tmp_path: Path):
        output = tmp_path / "out.txt"
        duplicates = {"abc123": [Path("/foo/a.jpg"), Path("/bar/b.jpg")]}
        write_report(duplicates, output)
        lines = output.read_text().splitlines()
        assert len(lines) == 2
        for line in lines:
            hash_part, path_part = line.split("  ", 1)
            assert hash_part == "abc123"
            assert path_part in ("/foo/a.jpg", "/bar/b.jpg")

    def test_empty_duplicates_writes_empty_file(self, tmp_path: Path):
        output = tmp_path / "out.txt"
        write_report({}, output)
        assert output.read_text() == ""
```

**Step 2: Run to verify they fail**

```
pytest tests/test_find_duplicates.py::TestWriteReport -v
```
Expected: `ImportError` for `write_report`

**Step 3: Add `write_report` to `tools/find_duplicates.py`**

```python
def write_report(duplicates: dict[str, list[Path]], output: Path) -> None:
    """Write sorted duplicate report to *output*.

    Format: one line per file — ``<sha256>  <absolute_path>``
    Sorted by sha256 hash.
    """
    lines: list[str] = []
    for h in sorted(duplicates):
        for path in duplicates[h]:
            lines.append(f"{h}  {path}")
    output.write_text("\n".join(lines))
```

**Step 4: Run tests to verify they pass**

```
pytest tests/test_find_duplicates.py::TestWriteReport -v
```
Expected: 3 PASS

**Step 5: Commit**

```bash
git add tools/find_duplicates.py tests/test_find_duplicates.py
git commit -m "feat: add write_report to find_duplicates tool"
```

---

### Task 4: CLI entry point and full integration

**Files:**
- Modify: `tools/find_duplicates.py`
- Test: `tests/test_find_duplicates.py`

**Step 1: Add failing CLI integration test**

Append to `tests/test_find_duplicates.py`:

```python
from find_duplicates import sha256_file, find_duplicates, write_report, main  # noqa: E402 (update import)


class TestMain:
    def test_finds_and_writes_duplicates(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"dup")
        (tmp_path / "b.txt").write_bytes(b"dup")
        output = tmp_path / "report.txt"
        rc = main([str(tmp_path), "--output", str(output)])
        assert rc == 0
        assert output.exists()
        lines = output.read_text().splitlines()
        assert len(lines) == 2

    def test_no_duplicates_still_writes_empty_report(self, tmp_path: Path):
        (tmp_path / "a.txt").write_bytes(b"unique1")
        output = tmp_path / "report.txt"
        rc = main([str(tmp_path), "--output", str(output)])
        assert rc == 0
        assert output.read_text() == ""

    def test_invalid_path_returns_nonzero(self, tmp_path: Path):
        rc = main([str(tmp_path / "nonexistent")])
        assert rc == 1

    def test_no_recursive_flag(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "a.txt").write_bytes(b"dup")
        (sub / "b.txt").write_bytes(b"dup")
        output = tmp_path / "report.txt"
        main([str(tmp_path), "--output", str(output), "--no-recursive"])
        assert output.read_text() == ""
```

**Step 2: Run to verify they fail**

```
pytest tests/test_find_duplicates.py::TestMain -v
```
Expected: `ImportError` for `main`

**Step 3: Add `_build_parser` and `main` to `tools/find_duplicates.py`**

```python
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="find_duplicates",
        description="遞迴掃描目錄，找出 SHA-256 重複的檔案並寫入報告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("path", help="要掃描的根目錄")
    parser.add_argument(
        "--output",
        default="duplicates.txt",
        metavar="FILE",
        help="輸出報告路徑（預設: duplicates.txt）",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="不遞迴掃描子目錄",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"❌ 路徑不存在或不是目錄: {root}")
        return 1

    print(f"🔍 掃描中: {root}")
    duplicates = find_duplicates(root, recursive=not args.no_recursive)

    output = Path(args.output).resolve()
    write_report(duplicates, output)

    total_files = sum(len(paths) for paths in duplicates.values())
    total_groups = len(duplicates)

    if total_groups == 0:
        print("✅ 沒有找到重複檔案")
    else:
        print(f"✅ 找到 {total_groups} 組重複，共 {total_files} 個檔案")
        print(f"📄 報告已寫入: {output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 4: Run all tests to verify they pass**

```
pytest tests/test_find_duplicates.py -v
```
Expected: all PASS

**Step 5: Run the full suite to make sure nothing broke**

```
pytest
```
Expected: all existing tests still PASS

**Step 6: Commit**

```bash
git add tools/find_duplicates.py tests/test_find_duplicates.py
git commit -m "feat: add CLI entry point and complete find_duplicates tool"
```
