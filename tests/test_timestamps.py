"""Tests for timestamped transcript formatting and generate_deep_content with segments."""

import json
from unittest.mock import MagicMock, patch


def _make_segments(entries: list[tuple[float, float, str]]) -> list[dict]:
    """Helper: build segment dicts from (start, end, text) tuples."""
    return [{"start": s, "end": e, "text": t} for s, e, t in entries]


class TestFormatTimestampedTranscript:
    def test_basic_formatting(self):
        """每個 segment 應格式化為 [MM:SS] text"""
        from app.services.analyzer import _format_timestamped_transcript

        segs = _make_segments([(0.0, 5.0, "開場"), (65.0, 70.0, "第二段")])
        result = _format_timestamped_transcript(segs)
        assert "[00:00] 開場" in result
        assert "[01:05] 第二段" in result

    def test_empty_segments_returns_empty_string(self):
        """空 segments 回傳空字串"""
        from app.services.analyzer import _format_timestamped_transcript

        result = _format_timestamped_transcript([])
        assert result == ""

    def test_truncation_inserts_ellipsis(self):
        """超過 max_chars 時應插入省略標記"""
        from app.services.analyzer import _format_timestamped_transcript

        long_text = "測" * 200
        segs = [
            {"start": float(i * 10), "end": float(i * 10 + 5), "text": long_text} for i in range(20)
        ]
        result = _format_timestamped_transcript(segs, max_chars=500)
        assert "省略" in result

    def test_within_limit_no_truncation(self):
        """未超過 max_chars 時不應有省略標記"""
        from app.services.analyzer import _format_timestamped_transcript

        segs = _make_segments([(0.0, 5.0, "短文"), (10.0, 15.0, "短文二")])
        result = _format_timestamped_transcript(segs, max_chars=8000)
        assert "省略" not in result
        assert "[00:00] 短文" in result
        assert "[00:10] 短文二" in result

    def test_hours_formatted_as_mm_ss(self):
        """超過 60 分鐘的 segment 應以 [MM:SS] 格式顯示分鐘數"""
        from app.services.analyzer import _format_timestamped_transcript

        segs = _make_segments([(3720.0, 3725.0, "長影片片段")])
        result = _format_timestamped_transcript(segs)
        assert "[62:00] 長影片片段" in result


class TestGenerateDeepContentWithSegments:
    def _make_mock_chat_response(self, content: str) -> MagicMock:
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_uses_timestamped_transcript_when_segments_provided(self):
        """segments 提供時，發給 GPT 的內容應包含時間戳格式"""
        from app.services import analyzer

        segs = _make_segments([(0.0, 5.0, "案例開始"), (10.0, 15.0, "案例結束")])
        result_json = json.dumps(
            {"study_notes": "## 學習筆記\n內容", "case_analysis": "## 案例\n[00:00] 案例開始"}
        )

        captured_calls: list[str] = []

        def fake_chat(system_prompt: str, user_content: str, max_tokens: int = 2000) -> str:
            captured_calls.append(user_content)
            return result_json

        with patch.object(analyzer, "_chat", side_effect=fake_chat):
            study_notes, case_analysis = analyzer.generate_deep_content(
                "transcript text", segments=segs
            )

        assert len(captured_calls) == 1
        assert "[00:00]" in captured_calls[0]
        assert "[00:10]" in captured_calls[0]
        assert "時間點" in captured_calls[0]

    def test_uses_plain_transcript_when_no_segments(self):
        """segments 為 None 時，發給 GPT 的內容應為純文字逐字稿"""
        from app.services import analyzer

        result_json = json.dumps({"study_notes": "筆記", "case_analysis": "NO_CASE_ANALYSIS"})
        captured_calls: list[str] = []

        def fake_chat(system_prompt: str, user_content: str, max_tokens: int = 2000) -> str:
            captured_calls.append(user_content)
            return result_json

        with patch.object(analyzer, "_chat", side_effect=fake_chat):
            study_notes, case_analysis = analyzer.generate_deep_content(
                "純文字逐字稿內容", segments=None
            )

        assert "純文字逐字稿內容" in captured_calls[0]
        assert "時間點" not in captured_calls[0]
        assert case_analysis == ""

    def test_no_case_analysis_returns_empty_string(self):
        """GPT 回傳 NO_CASE_ANALYSIS 時 case_analysis 應為空字串"""
        from app.services import analyzer

        result_json = json.dumps({"study_notes": "筆記", "case_analysis": "NO_CASE_ANALYSIS"})
        with patch.object(analyzer, "_chat", return_value=result_json):
            _, case_analysis = analyzer.generate_deep_content("transcript")

        assert case_analysis == ""

    def test_returns_study_notes_and_case_analysis(self):
        """成功時應回傳 (study_notes, case_analysis) tuple"""
        from app.services import analyzer

        result_json = json.dumps(
            {"study_notes": "## 核心概念\n內容", "case_analysis": "## 案例1\n詳細內容"}
        )
        with patch.object(analyzer, "_chat", return_value=result_json):
            study_notes, case_analysis = analyzer.generate_deep_content("transcript")

        assert "核心概念" in study_notes
        assert "案例1" in case_analysis
