"""
個人筆記 API 測試
"""
import uuid
import pytest
from app.database import VideoNote


class TestGetNote:
    def test_get_note_empty_when_not_exists(self, client, completed_video):
        r = client.get(f"/api/notes/{completed_video.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == ""
        assert data["updated_at"] is None

    def test_get_note_returns_content(self, client, video_with_note):
        video, note = video_with_note
        r = client.get(f"/api/notes/{video.id}")
        assert r.status_code == 200
        assert r.json()["content"] == note.content

    def test_get_note_video_not_found(self, client):
        r = client.get("/api/notes/nonexistent")
        assert r.status_code == 404

    def test_get_note_returns_video_id(self, client, completed_video):
        r = client.get(f"/api/notes/{completed_video.id}")
        assert r.json()["video_id"] == completed_video.id


class TestUpsertNote:
    def test_create_new_note(self, client, completed_video):
        vid_id = completed_video.id
        r = client.put(f"/api/notes/{vid_id}", json={"content": "# 新筆記\n\n- 重點"})
        assert r.status_code == 200
        data = r.json()
        assert data["content"] == "# 新筆記\n\n- 重點"
        assert data["updated_at"] is not None

    def test_update_existing_note(self, client, video_with_note):
        video, _ = video_with_note
        r = client.put(f"/api/notes/{video.id}", json={"content": "更新後的內容"})
        assert r.status_code == 200
        assert r.json()["content"] == "更新後的內容"

    def test_update_note_only_one_record(self, client, db_session, completed_video):
        vid_id = completed_video.id
        client.put(f"/api/notes/{vid_id}", json={"content": "第一次"})
        client.put(f"/api/notes/{vid_id}", json={"content": "第二次"})
        count = db_session.query(VideoNote).filter(VideoNote.video_id == vid_id).count()
        assert count == 1

    def test_upsert_note_video_not_found(self, client):
        r = client.put("/api/notes/nonexistent", json={"content": "test"})
        assert r.status_code == 404

    def test_upsert_note_empty_content(self, client, completed_video):
        r = client.put(f"/api/notes/{completed_video.id}", json={"content": ""})
        assert r.status_code == 200
        assert r.json()["content"] == ""

    def test_upsert_note_unicode_content(self, client, completed_video):
        content = "# 筆記\n\n- 占星學 🌟\n- 風水 ☯️\n- 奇門遁甲"
        r = client.put(f"/api/notes/{completed_video.id}", json={"content": content})
        assert r.status_code == 200
        assert r.json()["content"] == content

    def test_upsert_note_large_content(self, client, completed_video):
        large_content = "# 長筆記\n\n" + ("重要內容 " * 500)
        r = client.put(f"/api/notes/{completed_video.id}", json={"content": large_content})
        assert r.status_code == 200
        assert len(r.json()["content"]) > 1000

    def test_get_after_create_returns_same(self, client, completed_video):
        vid_id = completed_video.id
        content = "## 測試筆記\n**粗體** *斜體*"
        client.put(f"/api/notes/{vid_id}", json={"content": content})
        r = client.get(f"/api/notes/{vid_id}")
        assert r.json()["content"] == content

    def test_markdown_symbols_preserved(self, client, completed_video):
        """Markdown 特殊符號不應被轉義或修改"""
        content = "# H1\n## H2\n> 引用\n```python\nprint('hello')\n```"
        client.put(f"/api/notes/{completed_video.id}", json={"content": content})
        r = client.get(f"/api/notes/{completed_video.id}")
        assert r.json()["content"] == content


class TestDeleteNote:
    def test_delete_existing_note(self, client, db_session, video_with_note):
        video, _ = video_with_note
        r = client.delete(f"/api/notes/{video.id}")
        assert r.status_code == 200
        count = db_session.query(VideoNote).filter(VideoNote.video_id == video.id).count()
        assert count == 0

    def test_delete_nonexistent_note_succeeds(self, client, completed_video):
        """刪除不存在的筆記應回傳 200，不報錯"""
        r = client.delete(f"/api/notes/{completed_video.id}")
        assert r.status_code == 200

    def test_get_after_delete_returns_empty(self, client, video_with_note):
        video, _ = video_with_note
        client.delete(f"/api/notes/{video.id}")
        r = client.get(f"/api/notes/{video.id}")
        assert r.json()["content"] == ""
