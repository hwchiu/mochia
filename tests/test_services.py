"""Services 單元測試（mock 外部依賴）"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAudioExtractor:
    def test_extract_audio_success(self, tmp_path, fake_video_file):
        """FFmpeg 執行成功時回傳音頻路徑"""
        with (
            patch("app.services.audio_extractor.settings") as mock_settings,
            patch("app.services.audio_extractor.subprocess.Popen") as mock_popen,
        ):
            audio_dir = tmp_path / "audio_temp"
            audio_dir.mkdir()
            mock_settings.AUDIO_TEMP_DIR = audio_dir

            from app.services.audio_extractor import extract_audio

            with patch("app.services.audio_extractor.settings", mock_settings):
                # 模擬 FFmpeg Popen 產生輸出檔案
                def fake_popen(cmd, **kwargs):
                    output_path = cmd[-1]
                    Path(output_path).write_bytes(b"\x00" * 100)
                    mock_proc = MagicMock()
                    mock_proc.stderr = iter([])  # no stderr lines
                    mock_proc.returncode = 0
                    mock_proc.wait.return_value = 0
                    return mock_proc

                mock_popen.side_effect = fake_popen

                result = extract_audio(fake_video_file)
                assert result.exists()
                assert result.suffix == ".mp3"

    def test_extract_audio_file_not_found(self, tmp_path):
        """影片不存在時拋出 FileNotFoundError"""
        from app.services.audio_extractor import extract_audio

        with pytest.raises(FileNotFoundError, match="影片檔案不存在"):
            extract_audio(tmp_path / "nonexistent.mp4")

    def test_extract_audio_ffmpeg_fails(self, fake_video_file, tmp_path):
        """FFmpeg 失敗時拋出 RuntimeError"""
        with (
            patch("app.services.audio_extractor.settings") as mock_settings,
            patch("app.services.audio_extractor.subprocess.Popen") as mock_popen,
        ):
            audio_dir = tmp_path / "audio_temp"
            audio_dir.mkdir()
            mock_settings.AUDIO_TEMP_DIR = audio_dir

            mock_proc = MagicMock()
            mock_proc.stderr = iter([])
            mock_proc.returncode = 1
            mock_proc.wait.return_value = 1
            mock_popen.return_value = mock_proc

            from app.services.audio_extractor import extract_audio

            with pytest.raises(RuntimeError, match="FFmpeg 提取失敗"):
                extract_audio(fake_video_file)

    def test_get_video_duration_success(self, fake_video_file):
        """ffprobe 成功回傳時長"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="125.5\n")
            from app.services.audio_extractor import get_video_duration

            duration = get_video_duration(fake_video_file)
            assert duration == 125.5

    def test_get_video_duration_failure_returns_none(self, fake_video_file):
        """ffprobe 失敗時回傳 None，不拋出例外"""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            from app.services.audio_extractor import get_video_duration

            assert get_video_duration(fake_video_file) is None

    def test_cleanup_audio_removes_file(self, tmp_path):
        """cleanup_audio 刪除檔案"""
        f = tmp_path / "temp.mp3"
        f.write_bytes(b"data")
        from app.services.audio_extractor import cleanup_audio

        cleanup_audio(f)
        assert not f.exists()

    def test_cleanup_audio_missing_file_no_error(self, tmp_path):
        """cleanup_audio 對不存在的檔案不拋出例外"""
        from app.services.audio_extractor import cleanup_audio

        cleanup_audio(tmp_path / "not_there.mp3")  # should not raise


class TestTranscriber:
    def test_transcribe_success(self, fake_audio_file):
        """Azure Whisper API 成功呼叫時回傳文字與空段落列表"""
        mock_response = MagicMock()
        mock_response.text = "測試逐字稿內容"
        mock_response.segments = []

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response

        from app.services import transcriber

        with (
            patch.object(transcriber, "_get_client", return_value=mock_client),
            patch("app.services.transcriber.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_WHISPER_DEPLOYMENT = "whisper"
            text, segments = transcriber.transcribe(fake_audio_file)
            assert text == "測試逐字稿內容"
            assert segments == []

    def test_transcribe_returns_segments(self, fake_audio_file):
        """Whisper verbose_json segments 應正確回傳到呼叫端"""
        seg1 = MagicMock()
        seg1.start = 0.0
        seg1.end = 5.0
        seg1.text = " 第一段 "
        seg2 = MagicMock()
        seg2.start = 5.5
        seg2.end = 10.0
        seg2.text = " 第二段 "

        mock_response = MagicMock()
        mock_response.text = "第一段 第二段"
        mock_response.segments = [seg1, seg2]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_response

        from app.services import transcriber

        with (
            patch.object(transcriber, "_get_client", return_value=mock_client),
            patch("app.services.transcriber.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_WHISPER_DEPLOYMENT = "whisper"
            text, segments = transcriber.transcribe(fake_audio_file)

        assert text == "第一段 第二段"
        assert len(segments) == 2
        assert segments[0] == {"start": 0.0, "end": 5.0, "text": "第一段"}
        assert segments[1] == {"start": 5.5, "end": 10.0, "text": "第二段"}

    def test_transcribe_file_not_found(self, tmp_path):
        """音頻不存在時拋出 FileNotFoundError"""
        from app.services.transcriber import transcribe

        with pytest.raises(FileNotFoundError):
            transcribe(tmp_path / "no_audio.mp3")

    def test_transcribe_no_api_key(self, fake_audio_file):
        """未設定 API Key 時拋出 ValueError"""
        with (
            patch("app.services.transcriber.settings") as mock_settings,
            patch("app.services.transcriber._client", None),
        ):
            mock_settings.AZURE_OPENAI_API_KEY = ""
            mock_settings.AZURE_OPENAI_ENDPOINT = ""
            mock_settings.AZURE_OPENAI_WHISPER_API_KEY = ""
            mock_settings.AZURE_OPENAI_WHISPER_ENDPOINT = ""
            mock_settings.whisper_api_key = ""
            mock_settings.whisper_endpoint = ""

            from app.services import transcriber

            transcriber._client = None

            with pytest.raises(ValueError, match="AZURE_OPENAI_API_KEY"):
                transcriber.transcribe(fake_audio_file)

    def test_split_audio_small_file(self, fake_audio_file):
        """小於 24MB 的檔案不切割，直接回傳原路徑"""
        from app.services.transcriber import _split_audio

        # fake_audio_file 很小，不需切割
        result = _split_audio(fake_audio_file)
        assert result == [fake_audio_file]

    def test_split_audio_large_file(self, tmp_path):
        """超過 24MB 的音頻應被切割為多個 chunk"""
        from app.services import transcriber

        # 建立一個假的 "大" 音頻檔案（邏輯上超限）
        large_audio = tmp_path / "large.mp3"
        large_audio.write_bytes(b"\x00" * 100)

        with (
            patch("app.services.transcriber.WHISPER_MAX_BYTES", 50),
            patch("app.services.transcriber._get_audio_duration", return_value=120.0),
            patch("subprocess.run") as mock_run,
        ):

            def fake_ffmpeg(cmd, **kwargs):
                # 模擬 FFmpeg 產生 chunk 檔案
                output = Path(cmd[-1])
                output.parent.mkdir(exist_ok=True)
                output.write_bytes(b"\x00" * 10)
                return MagicMock(returncode=0)

            mock_run.side_effect = fake_ffmpeg
            chunks = transcriber._split_audio(large_audio)

        assert len(chunks) > 1

    def test_transcribe_large_file_chunks_merged(self, tmp_path):
        """大檔案切割後各段轉錄結果應合併為一段文字，並包含 segments"""
        from app.services import transcriber

        large_audio = tmp_path / "large.mp3"
        large_audio.write_bytes(b"\x00" * 100)

        chunk1 = tmp_path / "chunk_000.mp3"
        chunk2 = tmp_path / "chunk_001.mp3"
        chunk1.write_bytes(b"\x00" * 10)
        chunk2.write_bytes(b"\x00" * 10)

        def make_response(text_val: str):
            r = MagicMock()
            r.text = text_val
            r.segments = []
            return r

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = [
            make_response("第一段文字"),
            make_response("第二段文字"),
        ]

        with (
            patch("app.services.transcriber.WHISPER_MAX_BYTES", 50),
            patch.object(transcriber, "_split_audio", return_value=[chunk1, chunk2]),
            patch.object(transcriber, "_get_client", return_value=mock_client),
            patch.object(transcriber, "_get_audio_duration", return_value=20.0),
            patch("app.services.transcriber.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_WHISPER_DEPLOYMENT = "whisper"
            text, segments = transcriber.transcribe(large_audio)

        assert "第一段文字" in text
        assert "第二段文字" in text
        assert isinstance(segments, list)


class TestAnalyzer:
    """Tests for analyze_all() — the combined GPT analysis function used in production."""

    def _make_mock_response(self, content: str):
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        response = MagicMock()
        response.choices = [choice]
        return response

    def _full_result_json(self, overrides: dict | None = None) -> str:
        base = {
            "summary": "這是一部占星學入門影片",
            "key_points": [
                {"theme": "星座基礎", "points": ["星座介紹", "行星關係"]},
                {"theme": "應用技巧", "points": ["實占技巧"]},
                {"theme": "其他", "points": ["延伸閱讀"]},
            ],
            "category": "占星學 (Astrology)",
            "confidence": 0.88,
            "faq": [{"question": "Q1", "answer": "A1"}],
        }
        if overrides:
            base.update(overrides)
        return json.dumps(base, ensure_ascii=False)

    def test_analyze_all_success(self):
        """analyze_all 回傳正確 JSON 時解析成功"""
        with (
            patch("app.services.analyzer.settings") as mock_settings,
            patch("app.services.analyzer._client", None),
            patch("app.services.analyzer._get_client") as mock_get,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                self._full_result_json()
            )

            from app.services.analyzer import analyze_all

            summary, key_points, category, confidence, faq_list = analyze_all("這是測試逐字稿")

            assert summary == "這是一部占星學入門影片"
            assert len(key_points) == 3
            assert category == "占星學 (Astrology)"
            assert abs(confidence - 0.88) < 0.001
            assert len(faq_list) == 1

    def test_analyze_all_with_markdown_code_block(self):
        """GPT 回傳包含 markdown code block 時正確處理"""
        wrapped = f"```json\n{self._full_result_json({'summary': '摘要內容', 'category': '未分類 (Uncategorized)'})}\n```"

        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(wrapped)

            from app.services.analyzer import analyze_all

            summary, _, category, _, _ = analyze_all("測試")
            assert summary == "摘要內容"
            assert category == "未分類 (Uncategorized)"

    def test_analyze_all_unknown_category_falls_back(self):
        """GPT 回傳未知分類時改用「未分類」"""
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                self._full_result_json({"category": "不存在的分類", "confidence": 0.9})
            )

            from app.services.analyzer import analyze_all

            _, _, category, confidence, _ = analyze_all("測試")
            assert category == "未分類 (Uncategorized)"
            assert confidence == 0.0

    def test_analyze_all_missing_faq_field_returns_empty_list(self):
        """If GPT omits the 'faq' field entirely, analyze_all returns empty list.

        Root cause of the FAQ-token-starvation incident: mindmap markdown
        consumed ~300 tokens in the GPT response, leaving too little room for
        the faq field.  GPT would either omit it or the JSON would be truncated.
        This test documents the safe fallback behaviour.
        """
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            # GPT returns valid JSON but without 'faq' key
            no_faq = self._full_result_json()
            no_faq_dict = json.loads(no_faq)
            del no_faq_dict["faq"]
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                json.dumps(no_faq_dict)
            )

            from app.services.analyzer import analyze_all

            _, _, _, _, faq_list = analyze_all("逐字稿內容")
            assert faq_list == []

    def test_analyze_all_truncated_json_raises_value_error(self):
        """If GPT returns truncated / invalid JSON, analyze_all raises ValueError.

        This is the 'worst case' of the token-starvation incident: GPT cuts off
        mid-JSON, producing a parse error.  The caller (worker.py) catches this
        and marks the task as failed so the user knows to retry.
        """
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                '{"summary": "部分摘要", "key_points": [{"theme": "占'  # truncated
            )

            import pytest

            from app.services.analyzer import analyze_all

            with pytest.raises(ValueError, match="無效 JSON"):
                analyze_all("逐字稿內容")

    def test_analyze_all_all_fields_populated(self):
        """analyze_all with a well-formed GPT response populates all 5 return fields.

        This is the 'happy path completeness' test: ensures that after a
        successful GPT call, every field (summary, key_points, category,
        confidence, faq_list) is present and non-empty.  Had this test existed,
        the empty-FAQ regression would have been caught immediately.
        """
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                self._full_result_json()
            )

            from app.services.analyzer import analyze_all

            summary, key_points, category, confidence, faq_list = analyze_all("測試逐字稿")

            assert summary, "summary must not be empty"
            assert key_points, "key_points must not be empty"
            assert category, "category must not be empty"
            assert confidence > 0, "confidence must be > 0"
            assert faq_list, "faq_list must not be empty"
            assert all("question" in item and "answer" in item for item in faq_list)

        """逐字稿超長時截斷後送分析，prompt 包含省略提示"""
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
            patch("app.services.analyzer.MAX_TRANSCRIPT_CHARS", 100),
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(
                self._full_result_json({"category": "未分類 (Uncategorized)"})
            )

            from app.services.analyzer import analyze_all

            analyze_all("A" * 500)

            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_msg = messages[1]["content"]
            assert "省略" in user_msg


# ═══════════════════════════════════════════════════════════════════════════════
# suggest_labels() 單元測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestSuggestLabels:
    def _chat(self, response_text):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=response_text))]
        )
        return mock_client

    def test_suggest_labels_returns_list(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat('["占星學", "命盤解析", "風水"]')
            from app.services.analyzer import suggest_labels

            result = suggest_labels("這是一部占星學課程")
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_suggest_labels_returns_max_5(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat('["A","B","C","D","E","F","G"]')
            from app.services.analyzer import suggest_labels

            result = suggest_labels("摘要")
        assert len(result) <= 5

    def test_suggest_labels_json_error_returns_empty(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat("這不是 JSON")
            from app.services.analyzer import suggest_labels

            result = suggest_labels("摘要")
        assert result == []

    def test_suggest_labels_extracts_json_from_text(self):
        """GPT 有時在 JSON 前後加了說明文字"""
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat('以下是標籤：["風水", "奇門遁甲"]，希望對您有幫助。')
            from app.services.analyzer import suggest_labels

            result = suggest_labels("摘要")
        assert "風水" in result
        assert "奇門遁甲" in result

    def test_suggest_labels_strips_whitespace(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat('[" 占星學 ", " 風水 "]')
            from app.services.analyzer import suggest_labels

            result = suggest_labels("摘要")
        assert all(label == label.strip() for label in result)

    def test_suggest_labels_truncates_long_summary(self):
        """超過 1500 字的摘要應截斷"""
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_client = self._chat('["標籤1"]')
            mock_get.return_value = mock_client
            from app.services.analyzer import suggest_labels

            long_summary = "長摘要" * 1000
            suggest_labels(long_summary)
        # 驗證被截斷（prompt 不含超長文字）
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        if isinstance(messages, list):
            user_text = " ".join(str(m.get("content", "")) for m in messages)
            assert len(user_text) < len(long_summary)


# ═══════════════════════════════════════════════════════════════════════════════
# extract_case_analysis() 單元測試
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtractCaseAnalysis:
    def _chat(self, response_text):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=response_text))]
        )
        return mock_client

    def test_no_case_analysis_returns_empty_string(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat("NO_CASE_ANALYSIS")
            from app.services.analyzer import extract_case_analysis

            result = extract_case_analysis("這是沒有案例分析的逐字稿")
        assert result == ""

    def test_empty_response_returns_empty_string(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat("")
            from app.services.analyzer import extract_case_analysis

            result = extract_case_analysis("逐字稿")
        assert result == ""

    def test_whitespace_only_returns_empty(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat("   ")
            from app.services.analyzer import extract_case_analysis

            result = extract_case_analysis("逐字稿")
        assert result == ""

    def test_with_case_analysis_returns_content(self):
        case_md = "## 案例1\n背景：...\n分析：...\n結論：..."
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat(case_md)
            from app.services.analyzer import extract_case_analysis

            result = extract_case_analysis("包含案例的逐字稿")
        assert result == case_md

    def test_long_transcript_triggers_truncation(self):
        """超過 MAX_TRANSCRIPT_CHARS 的逐字稿應被截斷送出"""
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
            patch("app.services.analyzer.MAX_TRANSCRIPT_CHARS", 100),
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_client = self._chat("## 案例1\n內容")
            mock_get.return_value = mock_client
            from app.services.analyzer import extract_case_analysis

            long_text = "X" * 500
            extract_case_analysis(long_text)
        call_args = mock_client.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_text = messages[1]["content"] if isinstance(messages, list) else ""
        assert "省略" in user_text

    def test_result_is_stripped(self):
        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_get.return_value = self._chat("  ## 案例1\n內容  ")
            from app.services.analyzer import extract_case_analysis

            result = extract_case_analysis("逐字稿")
        assert result == result.strip()
