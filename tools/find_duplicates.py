#!/usr/bin/env python3
"""
find_duplicates.py — Duplicate file finder
==========================================

Recursively scans a directory and finds duplicate files.

Fast mode (default): groups by filename + file size — no file reads,
safe for Google Drive "Files On-Demand" / offline-stub scenarios.

Deep mode (--deep): groups by SHA-256 hash — definitive but requires
reading every file (triggers download for cloud-stub files).

Usage:
    python tools/find_duplicates.py <path>
    python tools/find_duplicates.py <path> --output report.txt
    python tools/find_duplicates.py <path> --no-recursive
    python tools/find_duplicates.py <path> --deep
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

_CHUNK = 65536  # 64 KB streaming reads


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of *path*."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def find_duplicates(
    root: Path,
    *,
    recursive: bool,
    deep: bool,
) -> dict[str, list[Path]]:
    """Return groups of duplicate files.

    Fast mode (deep=False): key is ``filename|size_bytes``.
    Deep mode (deep=True):  key is SHA-256 hex digest.
    Groups with fewer than 2 files are excluded.
    """
    glob = root.rglob("*") if recursive else root.glob("*")
    buckets: dict[str, list[Path]] = defaultdict(list)
    for path in glob:
        if not path.is_file():
            continue
        if deep:
            key = sha256_file(path)
        else:
            key = f"{path.name}|{path.stat().st_size}"
        buckets[key].append(path)
    return {k: paths for k, paths in buckets.items() if len(paths) >= 2}
