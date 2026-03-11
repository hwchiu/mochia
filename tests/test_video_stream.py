"""
影片串流 & 本地開啟 API 測試
"""
import pytest
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.database import Video


# ─── 輔助 fixture ──────────────────────────────────────────────────────────────

@pytest.fixture
def real_mp4_video(db_session, tmp_path) -> tuple:
    """建立有真實（假）MP4 檔案的影片記錄"""
    f = tmp_path / "test.mp4"
    f.write_bytes(b"\x00" * 2048)  # 假的 MP4 binary
    vid = Video(
        id=uuid.uuid4().hex,
        filename="test.mp4",
        original_filename="test.mp4",
        file_path=str(f),
        source="local_scan",
        file_size=2048,
        status="completed",
    )
    db_session.add(vid)
    db_session.commit()
    return vid, f


@pytest.fixture
def wmv_video(db_session, tmp_path) -> tuple:
    """建立 WMV 格式影片（瀏覽器不支援）"""
    f = tmp_path / "test.wmv"
    f.write_bytes(b"\x00" * 1024)
    vid = Video(
        id=uuid.uuid4().hex,
        filename="test.wmv",
        original_filename="test.wmv",
        file_path=str(f),
        source="local_scan",
        file_size=1024,
        status="completed",
    )
    db_session.add(vid)
    db_session.commit()
    return vid, f


@pytest.fixture
def missing_file_video(db_session) -> Video:
    """建立指向不存在檔案的影片記錄"""
    vid = Video(
        id=uuid.uuid4().hex,
        filename="ghost.mp4",
        original_filename="ghost.mp4",
        file_path="/nonexistent/path/ghost.mp4",
        source="local_scan",
        file_size=500,
        status="completed",
    )
    db_session.add(vid)
    db_session.commit()
    return vid


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/videos/{id}/stream — 影片串流
# ═══════════════════════════════════════════════════════════════════════════════

class TestVideoStream:
    def test_stream_mp4_success(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 200

    def test_stream_mp4_correct_mime(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert "video/mp4" in r.headers.get("content-type", "")

    def test_stream_mp4_accept_ranges_header(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.headers.get("accept-ranges") == "bytes"

    def test_stream_returns_file_content(self, client, real_mp4_video):
        vid, f = real_mp4_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert len(r.content) == f.stat().st_size

    def test_stream_wmv_returns_415(self, client, wmv_video):
        vid, _ = wmv_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 415

    def test_stream_wmv_error_message(self, client, wmv_video):
        vid, _ = wmv_video
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert "WMV" in r.json()["detail"].upper() or "wmv" in r.json()["detail"].lower()

    def test_stream_video_not_found(self, client):
        r = client.get("/api/videos/nonexistent/stream")
        assert r.status_code == 404

    def test_stream_missing_file_returns_404(self, client, missing_file_video):
        r = client.get(f"/api/videos/{missing_file_video.id}/stream")
        assert r.status_code == 404

    def test_stream_mov_format(self, client, db_session, tmp_path):
        f = tmp_path / "test.mov"
        f.write_bytes(b"\x00" * 512)
        vid = Video(
            id=uuid.uuid4().hex, filename="test.mov", original_filename="test.mov",
            file_path=str(f), source="local_scan", file_size=512, status="completed",
        )
        db_session.add(vid)
        db_session.commit()
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 200
        assert "quicktime" in r.headers.get("content-type", "").lower()

    def test_stream_mkv_returns_415(self, client, db_session, tmp_path):
        f = tmp_path / "test.mkv"
        f.write_bytes(b"\x00" * 512)
        vid = Video(
            id=uuid.uuid4().hex, filename="test.mkv", original_filename="test.mkv",
            file_path=str(f), source="local_scan", file_size=512, status="completed",
        )
        db_session.add(vid)
        db_session.commit()
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 415

    def test_stream_avi_returns_415(self, client, db_session, tmp_path):
        f = tmp_path / "test.avi"
        f.write_bytes(b"\x00" * 512)
        vid = Video(
            id=uuid.uuid4().hex, filename="test.avi", original_filename="test.avi",
            file_path=str(f), source="local_scan", file_size=512, status="completed",
        )
        db_session.add(vid)
        db_session.commit()
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 415

    def test_stream_video_with_null_file_path(self, client, db_session):
        vid = Video(
            id=uuid.uuid4().hex, filename="nopath.mp4", original_filename="nopath.mp4",
            file_path=None, source="uploaded", file_size=100, status="completed",
        )
        db_session.add(vid)
        db_session.commit()
        r = client.get(f"/api/videos/{vid.id}/stream")
        assert r.status_code == 404

    def test_stream_supported_formats_not_blocked(self, client, db_session, tmp_path):
        """MP4 / MOV / WebM / M4V 都應可以播放（不回 415）"""
        for ext in [".mp4", ".mov", ".webm", ".m4v"]:
            f = tmp_path / f"test{ext}"
            f.write_bytes(b"\x00" * 256)
            vid = Video(
                id=uuid.uuid4().hex, filename=f"test{ext}",
                original_filename=f"test{ext}", file_path=str(f),
                source="local_scan", file_size=256, status="completed",
            )
            db_session.add(vid)
            db_session.commit()
            r = client.get(f"/api/videos/{vid.id}/stream")
            assert r.status_code == 200, f"{ext} should be supported but got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/videos/{id}/open-local — 本地開啟
# ═══════════════════════════════════════════════════════════════════════════════

class TestOpenLocal:
    def test_open_local_macos_success(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        with patch("subprocess.Popen") as mock_popen, \
             patch("platform.system", return_value="Darwin"):
            r = client.post(f"/api/videos/{vid.id}/open-local")
            assert r.status_code == 200
            mock_popen.assert_called_once()
            args = mock_popen.call_args[0][0]
            assert args[0] == "open"

    def test_open_local_linux_uses_xdg_open(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        with patch("subprocess.Popen") as mock_popen, \
             patch("platform.system", return_value="Linux"):
            r = client.post(f"/api/videos/{vid.id}/open-local")
            assert r.status_code == 200
            args = mock_popen.call_args[0][0]
            assert args[0] == "xdg-open"

    def test_open_local_video_not_found(self, client):
        with patch("platform.system", return_value="Darwin"):
            r = client.post("/api/videos/nonexistent/open-local")
        assert r.status_code == 404

    def test_open_local_missing_file_returns_404(self, client, missing_file_video):
        with patch("platform.system", return_value="Darwin"):
            r = client.post(f"/api/videos/{missing_file_video.id}/open-local")
        assert r.status_code == 404

    def test_open_local_subprocess_failure_returns_500(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        with patch("subprocess.Popen", side_effect=FileNotFoundError("open not found")), \
             patch("platform.system", return_value="Darwin"):
            r = client.post(f"/api/videos/{vid.id}/open-local")
        assert r.status_code == 500

    def test_open_local_response_message(self, client, real_mp4_video):
        vid, _ = real_mp4_video
        with patch("subprocess.Popen"), patch("platform.system", return_value="Darwin"):
            r = client.post(f"/api/videos/{vid.id}/open-local")
        assert "message" in r.json()
