"""Tests for tools/convert_to_mp4.py — no FFmpeg or real files required."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make sure tools/ is importable even without an __init__.py
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from convert_to_mp4 import (  # noqa: E402
    ConvertResult,
    _build_output_path,
    _print_summary,
    convert_one,
    find_targets,
    main,
    run_conversion,
)


# ── find_targets ──────────────────────────────────────────────────────────────


class TestFindTargets:
    def test_single_file_matching_format(self, tmp_path: Path):
        f = tmp_path / "clip.avi"
        f.touch()
        assert find_targets(f, frozenset({".avi"})) == [f]

    def test_single_file_not_matching(self, tmp_path: Path):
        f = tmp_path / "clip.mp4"
        f.touch()
        assert find_targets(f, frozenset({".avi"})) == []

    def test_recursive_scan(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        a = tmp_path / "a.avi"
        b = tmp_path / "sub" / "b.flv"
        c = tmp_path / "keep.mp4"
        a.touch(); b.touch(); c.touch()  # noqa: E702
        result = find_targets(tmp_path, frozenset({".avi", ".flv"}))
        assert set(result) == {a, b}

    def test_no_recursive(self, tmp_path: Path):
        (tmp_path / "sub").mkdir()
        a = tmp_path / "a.avi"
        b = tmp_path / "sub" / "b.avi"
        a.touch(); b.touch()  # noqa: E702
        result = find_targets(tmp_path, frozenset({".avi"}), recursive=False)
        assert result == [a]

    def test_empty_directory(self, tmp_path: Path):
        assert find_targets(tmp_path, frozenset({".avi"})) == []

    def test_uppercase_extension(self, tmp_path: Path):
        f = tmp_path / "clip.AVI"
        f.touch()
        result = find_targets(tmp_path, frozenset({".avi"}))
        assert f in result


# ── _build_output_path ────────────────────────────────────────────────────────


class TestBuildOutputPath:
    def test_same_dir_default(self, tmp_path: Path):
        src = tmp_path / "video.avi"
        assert _build_output_path(src, None) == tmp_path / "video.mp4"

    def test_custom_output_dir(self, tmp_path: Path):
        src = tmp_path / "video.avi"
        dest_dir = tmp_path / "converted"
        assert _build_output_path(src, dest_dir) == dest_dir / "video.mp4"

    def test_stem_with_dots(self, tmp_path: Path):
        src = tmp_path / "my.movie.v2.mkv"
        assert _build_output_path(src, None) == tmp_path / "my.movie.v2.mp4"


# ── convert_one ───────────────────────────────────────────────────────────────


class TestConvertOne:
    _lock = threading.Lock()

    def _dest(self, tmp_path: Path, name: str = "out.mp4") -> Path:
        return tmp_path / name

    def test_skip_existing_no_overwrite(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"; dest.touch()
        r = convert_one(src, dest, overwrite=False, dry_run=False,
                        delete_original=False, lock=self._lock)
        assert r.skipped is True
        assert r.success is False

    def test_dry_run_returns_success_without_conversion(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"
        r = convert_one(src, dest, overwrite=False, dry_run=True,
                        delete_original=False, lock=self._lock)
        assert r.dry_run is True
        assert r.success is True
        assert not dest.exists()

    def test_ffmpeg_success(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"
        dest.write_bytes(b"fake mp4 data")  # pre-create so stat() succeeds

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            # overwrite=True so the pre-existing dest doesn't trigger skip
            r = convert_one(src, dest, overwrite=True, dry_run=False,
                            delete_original=False, lock=self._lock)
        assert r.success is True
        assert r.error == ""

    def test_ffmpeg_failure_captures_error(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"

        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Conversion failed\nsome reason"

        with patch("subprocess.run", return_value=mock_proc):
            r = convert_one(src, dest, overwrite=False, dry_run=False,
                            delete_original=False, lock=self._lock)
        assert r.success is False
        assert "some reason" in r.error

    def test_delete_original_after_success(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"
        dest.write_bytes(b"fake")  # pre-create so stat() succeeds

        mock_proc = MagicMock()
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            # overwrite=True so the pre-existing dest doesn't trigger skip
            r = convert_one(src, dest, overwrite=True, dry_run=False,
                            delete_original=True, lock=self._lock)
        assert r.success is True
        assert not src.exists()

    def test_overwrite_existing(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"; dest.touch()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        dest.write_bytes(b"new content")

        with patch("subprocess.run", return_value=mock_proc):
            r = convert_one(src, dest, overwrite=True, dry_run=False,
                            delete_original=False, lock=self._lock)
        assert r.success is True
        assert r.skipped is False

    def test_ffmpeg_not_installed(self, tmp_path: Path):
        src = tmp_path / "v.avi"; src.touch()
        dest = tmp_path / "v.mp4"

        with patch("subprocess.run", side_effect=FileNotFoundError):
            r = convert_one(src, dest, overwrite=False, dry_run=False,
                            delete_original=False, lock=self._lock)
        assert r.success is False
        assert "ffmpeg" in r.error.lower()


# ── run_conversion ────────────────────────────────────────────────────────────


class TestRunConversion:
    def test_empty_dir_returns_no_results(self, tmp_path: Path):
        results = run_conversion(
            tmp_path, formats=frozenset({".avi"}), output_dir=None,
            workers=1, overwrite=False, dry_run=True,
            delete_original=False, recursive=True,
        )
        assert results == []

    def test_dry_run_all_succeed(self, tmp_path: Path):
        for name in ["a.avi", "b.flv", "c.mkv"]:
            (tmp_path / name).touch()

        results = run_conversion(
            tmp_path, formats=frozenset({".avi", ".flv", ".mkv"}),
            output_dir=None, workers=2, overwrite=False, dry_run=True,
            delete_original=False, recursive=True,
        )
        assert len(results) == 3
        assert all(r.success for r in results)
        assert all(r.dry_run for r in results)

    def test_custom_output_dir(self, tmp_path: Path):
        src = tmp_path / "clip.avi"; src.touch()
        out_dir = tmp_path / "out"

        results = run_conversion(
            tmp_path, formats=frozenset({".avi"}), output_dir=out_dir,
            workers=1, overwrite=False, dry_run=True,
            delete_original=False, recursive=True,
        )
        assert results[0].dest.parent == out_dir


# ── _print_summary ────────────────────────────────────────────────────────────


class TestPrintSummary:
    def test_all_success_returns_zero(self, capsys):
        results = [
            ConvertResult(source=Path("a.avi"), dest=Path("a.mp4"), success=True),
        ]
        code = _print_summary(results)
        assert code == 0

    def test_failure_returns_nonzero(self, capsys):
        results = [
            ConvertResult(source=Path("a.avi"), dest=Path("a.mp4"),
                          success=False, error="codec error"),
        ]
        code = _print_summary(results)
        assert code == 1
        out = capsys.readouterr().out
        assert "codec error" in out

    def test_skipped_does_not_count_as_failure(self, capsys):
        results = [
            ConvertResult(source=Path("a.avi"), dest=Path("a.mp4"), skipped=True),
        ]
        code = _print_summary(results)
        assert code == 0


# ── main() CLI entry ──────────────────────────────────────────────────────────


class TestMain:
    def test_no_ffmpeg_exits_1(self, tmp_path: Path):
        with patch("shutil.which", return_value=None):
            code = main([str(tmp_path)])
        assert code == 1

    def test_nonexistent_path_exits_1(self, tmp_path: Path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path / "nope")])
        assert code == 1

    def test_dry_run_flag(self, tmp_path: Path):
        (tmp_path / "clip.avi").touch()
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path), "--dry-run"])
        assert code == 0

    def test_formats_flag(self, tmp_path: Path):
        (tmp_path / "clip.mp4").touch()  # mp4 not in target
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path), "--formats", ".avi", "--dry-run"])
        assert code == 0  # nothing to convert, no failures

    def test_workers_flag(self, tmp_path: Path):
        for i in range(4):
            (tmp_path / f"v{i}.avi").touch()
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path), "--workers", "4", "--dry-run"])
        assert code == 0

    def test_no_recursive_flag(self, tmp_path: Path):
        sub = tmp_path / "sub"; sub.mkdir()
        (tmp_path / "top.avi").touch()
        (sub / "nested.avi").touch()
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path), "--no-recursive", "--dry-run"])
        assert code == 0

    def test_output_dir_flag(self, tmp_path: Path):
        (tmp_path / "clip.avi").touch()
        out = tmp_path / "output"
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            code = main([str(tmp_path), "--output-dir", str(out), "--dry-run"])
        assert code == 0
