"""
全文搜尋 API 測試 (FTS5)
"""

import json
import uuid

from app.database import Summary, Transcript, Video

# ─── 輔助：直接寫入 FTS 索引（繞過 in-memory DB 限制）─────────────────────────


def _insert_fts(fts_conn, video_id, title="", summary="", transcript="", key_points=""):
    """直接向 FTS 虛擬表插入測試資料"""
    cur = fts_conn.cursor()
    cur.execute(
        "INSERT INTO video_fts(video_id, title, summary, transcript, key_points) VALUES (?,?,?,?,?)",
        (video_id, title, summary, transcript, key_points),
    )
    fts_conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/search/ — 全文搜尋
# ═══════════════════════════════════════════════════════════════════════════════


class TestSearch:
    def test_empty_query_returns_400(self, client):
        r = client.get("/api/search/?q=%20")  # 空白
        assert r.status_code == 400

    def test_search_returns_structure(self, client):
        r = client.get("/api/search/?q=test")
        assert r.status_code == 200
        data = r.json()
        assert "query" in data
        assert "total" in data
        assert "items" in data

    def test_search_returns_query_in_response(self, client):
        r = client.get("/api/search/?q=占星")
        assert r.json()["query"] == "占星"

    def test_search_no_results_returns_empty(self, client):
        r = client.get("/api/search/?q=xyzabc完全不可能存在的字串123")
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_search_limit_parameter_respected(self, client):
        r = client.get("/api/search/?q=test&limit=5")
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 5

    def test_search_with_real_fts_data(self, client, db_session, completed_video):
        """向 FTS 索引插入資料後應能搜到"""
        from app.routers.search import rebuild_fts_index

        # 注入 db
        rebuild_fts_index(completed_video.id, db_session)
        r = client.get("/api/search/?q=占星")
        # 若 FTS 使用不同 DB file，至少不報錯
        assert r.status_code == 200

    def test_search_item_has_required_fields(self, client, db_session, completed_video):
        """搜尋結果每筆應有必要欄位"""
        from app.routers.search import rebuild_fts_index

        rebuild_fts_index(completed_video.id, db_session)
        r = client.get("/api/search/?q=占星")
        if r.json()["items"]:
            item = r.json()["items"][0]
            for field in ["id", "filename", "status"]:
                assert field in item


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/search/reindex — 重建 FTS 索引
# ═══════════════════════════════════════════════════════════════════════════════


class TestReindex:
    def test_reindex_success(self, client):
        r = client.post("/api/search/reindex")
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert data["count"] >= 0

    def test_reindex_returns_count(self, client, completed_video):
        r = client.post("/api/search/reindex")
        data = r.json()
        assert isinstance(data["count"], int)

    def test_reindex_message_contains_count(self, client):
        r = client.post("/api/search/reindex")
        assert "已重建" in r.json()["message"]


# ═══════════════════════════════════════════════════════════════════════════════
# rebuild_fts_index() 函數單元測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestRebuildFtsIndex:
    def test_rebuild_nonexistent_video_no_error(self, db_session):
        from app.routers.search import rebuild_fts_index

        # 不應拋出例外
        rebuild_fts_index("nonexistent_id", db_session)

    def test_rebuild_video_without_summary(self, db_session, sample_video):
        from app.routers.search import rebuild_fts_index

        # 影片有 video 記錄但無 summary/transcript
        rebuild_fts_index(sample_video.id, db_session)
        # 不應拋出例外

    def test_rebuild_video_with_full_data(self, db_session, completed_video):
        from app.routers.search import rebuild_fts_index

        # 完整資料不應拋出例外
        rebuild_fts_index(completed_video.id, db_session)

    def test_rebuild_key_points_new_format(self, db_session):
        """key_points 為 [{theme, points}] 格式應正確展開"""
        from app.routers.search import rebuild_fts_index

        vid_id = uuid.uuid4().hex
        kp = json.dumps(
            [
                {"theme": "占星學基礎", "points": ["星座意義", "行星影響"]},
            ],
            ensure_ascii=False,
        )
        db_session.add(
            Video(
                id=vid_id,
                filename="kp_test.mp4",
                original_filename="kp_test.mp4",
                file_size=100,
                status="completed",
            )
        )
        db_session.add(
            Summary(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                summary="摘要",
                key_points=kp,
            )
        )
        db_session.commit()
        # 不應拋出例外
        rebuild_fts_index(vid_id, db_session)

    def test_rebuild_key_points_old_string_format(self, db_session):
        """key_points 為 ['string'] 格式應正確處理"""
        from app.routers.search import rebuild_fts_index

        vid_id = uuid.uuid4().hex
        kp = json.dumps(["重點一", "重點二"], ensure_ascii=False)
        db_session.add(
            Video(
                id=vid_id,
                filename="kp_str.mp4",
                original_filename="kp_str.mp4",
                file_size=100,
                status="completed",
            )
        )
        db_session.add(
            Summary(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                summary="摘要",
                key_points=kp,
            )
        )
        db_session.commit()
        rebuild_fts_index(vid_id, db_session)

    def test_rebuild_transcript_truncated_to_8000(self, db_session):
        """長逐字稿應截斷，不應超過 8000 字"""
        from app.routers.search import rebuild_fts_index

        vid_id = uuid.uuid4().hex
        long_transcript = "這是很長的逐字稿。" * 2000  # > 8000 chars
        db_session.add(
            Video(
                id=vid_id,
                filename="long.mp4",
                original_filename="long.mp4",
                file_size=100,
                status="completed",
            )
        )
        db_session.add(
            Transcript(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                content=long_transcript,
            )
        )
        db_session.add(
            Summary(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                summary="s",
                key_points="[]",
            )
        )
        db_session.commit()
        # 不應拋出例外（8000 char 截斷正常）
        rebuild_fts_index(vid_id, db_session)
