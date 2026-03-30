"""NotebookLM 功能測試：心智圖、FAQ、學習筆記、問答"""

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

from app.database import ChatMessage, Video

# ─── Analyzer service tests ─────────────────────────────────────


class TestAnalyzerNotebookLM:
    """測試 analyzer.py 中的 NotebookLM 相關函數"""

    def _mock_client(self, return_content: str):
        """建立 mock AzureOpenAI client"""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices[0].message.content = return_content
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def test_generate_faq_success(self):
        """generate_faq 應返回 list of dict"""
        from app.services.analyzer import generate_faq

        faq_data = json.dumps(
            [
                {
                    "question": "什麼是占星學？",
                    "answer": "占星學是研究天體位置與人類事務關係的學問。",
                },
                {"question": "星座有幾種？", "answer": "傳統上有12個星座。"},
                {"question": "如何看本命盤？", "answer": "需要出生日期、時間和地點。"},
                {"question": "水星逆行有什麼影響？", "answer": "通常與溝通和交通問題有關。"},
                {"question": "上升星座是什麼？", "answer": "是出生時東方地平線上的星座。"},
            ]
        )
        mock_client = self._mock_client(faq_data)

        with patch("app.services.analyzer._get_client", return_value=mock_client):
            result = generate_faq("這是關於占星學的逐字稿內容")

        assert isinstance(result, list)
        assert len(result) >= 1
        assert "question" in result[0]
        assert "answer" in result[0]

    def test_generate_faq_with_markdown_wrapper(self):
        """generate_faq 應能處理 GPT 回傳的 markdown code block 包裹"""
        from app.services.analyzer import generate_faq

        faq_data = '```json\n[{"question": "Q1", "answer": "A1"}]\n```'
        mock_client = self._mock_client(faq_data)

        with patch("app.services.analyzer._get_client", return_value=mock_client):
            result = generate_faq("逐字稿")

        assert isinstance(result, list)
        assert result[0]["question"] == "Q1"

    def test_ask_question_success(self):
        """ask_question 應返回回答字串"""
        from app.services.analyzer import ask_question

        mock_client = self._mock_client("太陽星座代表您的核心個性和自我表達方式。")

        with patch("app.services.analyzer._get_client", return_value=mock_client):
            result = ask_question(
                transcript="這是關於占星學的逐字稿", question="什麼是太陽星座？", chat_history=[]
            )

        assert isinstance(result, str)
        assert len(result) > 0

    def test_ask_question_uses_chat_history(self):
        """ask_question 應將歷史對話傳入 GPT"""
        from app.services.analyzer import ask_question

        mock_client = self._mock_client("根據上一個問題，月亮星座代表您的情感反應。")

        history = [
            {"role": "user", "content": "什麼是太陽星座？"},
            {"role": "assistant", "content": "太陽星座代表您的核心個性。"},
        ]

        with patch("app.services.analyzer._get_client", return_value=mock_client):
            result = ask_question(
                transcript="占星學逐字稿", question="那月亮星座呢？", chat_history=history
            )

        # Verify that create was called with messages including history
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        # Should have system message + history + current question
        assert any(m["role"] == "user" and "太陽星座" in m["content"] for m in messages)
        assert isinstance(result, str)


# ─── API endpoint tests ─────────────────────────────────────────


class TestNotebookLMAPI:
    """測試 NotebookLM 相關 API 端點"""

    def test_get_faq_success(self, client, completed_video_full):
        """成功獲取 FAQ"""
        resp = client.get(f"/api/analysis/{completed_video_full.id}/faq")
        assert resp.status_code == 200
        data = resp.json()
        assert "faq" in data
        assert isinstance(data["faq"], list)
        assert len(data["faq"]) >= 1
        assert "question" in data["faq"][0]
        assert "answer" in data["faq"][0]

    def test_get_faq_not_completed(self, client, sample_video):
        """分析未完成時返回 400"""
        resp = client.get(f"/api/analysis/{sample_video.id}/faq")
        assert resp.status_code == 409

    def test_get_faq_not_generated(self, client, completed_video):
        """FAQ 未生成時返回 404"""
        resp = client.get(f"/api/analysis/{completed_video.id}/faq")
        assert resp.status_code == 404

    def test_get_study_notes_success(self, client, completed_video_full):
        """成功獲取學習筆記"""
        resp = client.get(f"/api/analysis/{completed_video_full.id}/study-notes")
        assert resp.status_code == 200
        data = resp.json()
        assert "study_notes" in data
        assert "##" in data["study_notes"]

    def test_get_study_notes_not_completed(self, client, sample_video):
        """分析未完成時返回 400"""
        resp = client.get(f"/api/analysis/{sample_video.id}/study-notes")
        assert resp.status_code == 409

    def test_get_study_notes_not_generated(self, client, completed_video):
        """學習筆記未生成時返回 404"""
        resp = client.get(f"/api/analysis/{completed_video.id}/study-notes")
        assert resp.status_code == 404

    def test_ask_question_success(self, client, completed_video):
        """成功提問並獲取回答，且對話記錄被儲存"""
        with patch("app.routers.analysis.ask_question", return_value="太陽星座代表您的核心個性。"):
            resp = client.post(
                f"/api/analysis/{completed_video.id}/ask", json={"question": "什麼是太陽星座？"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert data["answer"] == "太陽星座代表您的核心個性。"

    def test_ask_question_not_completed(self, client, sample_video):
        """分析未完成時返回 400"""
        resp = client.post(f"/api/analysis/{sample_video.id}/ask", json={"question": "問題"})
        assert resp.status_code == 409

    def test_ask_question_no_transcript(self, client, db_session):
        """沒有逐字稿時返回 400"""
        vid_id = uuid.uuid4().hex
        video = Video(
            id=vid_id,
            filename="notrans.mp4",
            original_filename="notrans.mp4",
            file_path="/fake/path/notrans.mp4",
            source="local_scan",
            file_size=1024,
            duration=10.0,
            status="completed",
        )
        db_session.add(video)
        db_session.commit()

        resp = client.post(f"/api/analysis/{vid_id}/ask", json={"question": "問題"})
        assert resp.status_code == 400

    def test_ask_question_saves_messages(self, client, completed_video, db_session):
        """提問後應在資料庫中儲存對話記錄"""
        with patch("app.routers.analysis.ask_question", return_value="這是回答。"):
            client.post(f"/api/analysis/{completed_video.id}/ask", json={"question": "測試問題"})

        db_session.expire_all()
        messages = (
            db_session.query(ChatMessage).filter(ChatMessage.video_id == completed_video.id).all()
        )
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "測試問題"
        assert messages[1].role == "assistant"
        assert messages[1].content == "這是回答。"

    def test_get_chat_history(self, client, completed_video, db_session):
        """應返回對話歷史（按時間順序）"""
        vid_id = completed_video.id
        msgs = [
            ChatMessage(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                role="user",
                content="問題1",
                created_at=datetime(2024, 1, 1, 10, 0, 0),
            ),
            ChatMessage(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                role="assistant",
                content="回答1",
                created_at=datetime(2024, 1, 1, 10, 0, 1),
            ),
            ChatMessage(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                role="user",
                content="問題2",
                created_at=datetime(2024, 1, 1, 10, 0, 2),
            ),
        ]
        for m in msgs:
            db_session.add(m)
        db_session.commit()

        resp = client.get(f"/api/analysis/{vid_id}/chat-history")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert len(data["messages"]) == 3
        assert data["messages"][0]["content"] == "問題1"
        assert data["messages"][1]["content"] == "回答1"

    def test_delete_chat_history(self, client, completed_video, db_session):
        """清除對話歷史"""
        vid_id = completed_video.id
        for i in range(3):
            db_session.add(
                ChatMessage(id=uuid.uuid4().hex, video_id=vid_id, role="user", content=f"問題{i}")
            )
        db_session.commit()

        resp = client.delete(f"/api/analysis/{vid_id}/chat-history")
        assert resp.status_code == 200
        assert resp.json()["message"] == "已清除"

        # Verify cleared
        db_session.expire_all()
        count = db_session.query(ChatMessage).filter(ChatMessage.video_id == vid_id).count()
        assert count == 0

    def test_regenerate_faq(self, client, completed_video_full):
        """重新生成 FAQ"""
        new_faq = [{"question": "新問題", "answer": "新答案"}]
        with patch("app.routers.analysis.generate_faq", return_value=new_faq):
            resp = client.post(f"/api/analysis/{completed_video_full.id}/regenerate/faq")
        assert resp.status_code == 200
        data = resp.json()
        assert "faq" in data

    def test_regenerate_invalid_type(self, client, completed_video_full):
        """無效的 content_type 應返回 400"""
        resp = client.post(f"/api/analysis/{completed_video_full.id}/regenerate/invalid_type")
        assert resp.status_code == 400

    def test_regenerate_not_completed(self, client, sample_video):
        """未完成的影片不能重新生成"""
        resp = client.post(f"/api/analysis/{sample_video.id}/regenerate/faq")
        assert resp.status_code == 409
