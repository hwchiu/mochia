# find_duplicates.py — Design Document

**Date:** 2026-03-19

## Summary

A CLI tool in `tools/find_duplicates.py` that recursively scans a directory, identifies duplicate files via SHA256, and writes a sorted report to a text file.

## Usage

```
python tools/find_duplicates.py <path> [--output <file>] [--no-recursive]
```

| Argument | Default | Description |
|---|---|---|
| `path` | (required) | Root directory to scan |
| `--output` | `duplicates.txt` | Output report file path |
| `--no-recursive` | off | Disable recursive scanning |

## Output Format

Plain text file, one line per duplicate file, sorted by SHA256 hash:

```
<sha256hex>  <absolute_path>
<sha256hex>  <absolute_path>
...
```

- Only files that appear more than once (same hash) are listed
- Files with the same hash are grouped together (naturally via sort)
- Two spaces between hash and path for easy splitting

## Architecture

1. Walk directory with `pathlib.Path.rglob` (or `glob` for non-recursive)
2. Compute SHA256 for each file using `hashlib` (streaming reads for large files)
3. Group paths by hash using a `dict[str, list[Path]]`
4. Filter groups with `len >= 2` (duplicates only)
5. Sort by hash, write to output file

## Implementation Notes

- Pure Python stdlib only (`hashlib`, `pathlib`, `argparse`) — no external dependencies
- Stream file reads in 64KB chunks to handle large files without excessive memory use
- Style consistent with existing `tools/convert_to_mp4.py`
