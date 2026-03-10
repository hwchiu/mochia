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
        """Azure Whisper API 成功呼叫時回傳文字"""
        with (
            patch("app.services.transcriber.settings") as mock_settings,
            patch("app.services.transcriber._client", None),
            patch("app.services.transcriber.AzureOpenAI") as MockAzureOpenAI,
        ):
            mock_settings.AZURE_OPENAI_API_KEY = "test-key"
            mock_settings.AZURE_OPENAI_ENDPOINT = "https://test.openai.azure.com/"
            mock_settings.AZURE_OPENAI_API_VERSION = "2024-02-01"
            mock_settings.AZURE_OPENAI_WHISPER_DEPLOYMENT = "whisper"

            mock_client = MagicMock()
            MockAzureOpenAI.return_value = mock_client
            mock_client.audio.transcriptions.create.return_value = "測試逐字稿內容"

            from app.services import transcriber

            transcriber._client = None  # 強制重新建立 client

            with patch.object(transcriber, "_get_client", return_value=mock_client):
                result = transcriber.transcribe(fake_audio_file)
                assert result == "測試逐字稿內容"

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
        """大檔案切割後各段轉錄結果應合併為一段文字"""
        from app.services import transcriber

        large_audio = tmp_path / "large.mp3"
        large_audio.write_bytes(b"\x00" * 100)

        chunk1 = tmp_path / "chunk_000.mp3"
        chunk2 = tmp_path / "chunk_001.mp3"
        chunk1.write_bytes(b"\x00" * 10)
        chunk2.write_bytes(b"\x00" * 10)

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.side_effect = ["第一段文字", "第二段文字"]

        with (
            patch("app.services.transcriber.WHISPER_MAX_BYTES", 50),
            patch.object(transcriber, "_split_audio", return_value=[chunk1, chunk2]),
            patch.object(transcriber, "_get_client", return_value=mock_client),
            patch("app.services.transcriber.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_WHISPER_DEPLOYMENT = "whisper"
            result = transcriber.transcribe(large_audio)

        assert "第一段文字" in result
        assert "第二段文字" in result


class TestAnalyzer:
    def _make_mock_response(self, content: str):
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        response = MagicMock()
        response.choices = [choice]
        return response

    def test_analyze_success(self):
        """GPT 回傳正確 JSON 時解析成功"""
        result_json = json.dumps(
            {
                "summary": "這是一部占星學入門影片",
                "key_points": [
                    {"theme": "星座基礎", "points": ["星座介紹", "行星關係"]},
                    {"theme": "應用技巧", "points": ["實占技巧"]},
                    {"theme": "其他", "points": ["延伸閱讀"]},
                ],
                "category": "占星學 (Astrology)",
                "confidence": 0.88,
            },
            ensure_ascii=False,
        )

        with (
            patch("app.services.analyzer.settings") as mock_settings,
            patch("app.services.analyzer._client", None),
            patch("app.services.analyzer._get_client") as mock_get,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]
            mock_settings.MAX_TRANSCRIPT_CHARS = 12000

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(result_json)

            from app.services.analyzer import analyze

            summary, key_points, category, confidence = analyze("這是測試逐字稿")

            assert summary == "這是一部占星學入門影片"
            assert len(key_points) == 3
            assert category == "占星學 (Astrology)"
            assert abs(confidence - 0.88) < 0.001

    def test_analyze_with_markdown_code_block(self):
        """GPT 回傳包含 markdown code block 時正確處理"""
        result_json = json.dumps(
            {
                "summary": "摘要內容",
                "key_points": ["重點"],
                "category": "未分類 (Uncategorized)",
                "confidence": 0.5,
            },
            ensure_ascii=False,
        )

        wrapped = f"```json\n{result_json}\n```"

        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["未分類 (Uncategorized)"]
            mock_settings.MAX_TRANSCRIPT_CHARS = 12000

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(wrapped)

            from app.services.analyzer import analyze

            summary, _, category, _ = analyze("測試")
            assert summary == "摘要內容"

    def test_analyze_unknown_category_falls_back(self):
        """GPT 回傳未知分類時改用「未分類」"""
        result_json = json.dumps(
            {
                "summary": "摘要",
                "key_points": [],
                "category": "不存在的分類",
                "confidence": 0.9,
            },
            ensure_ascii=False,
        )

        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["占星學 (Astrology)", "未分類 (Uncategorized)"]
            mock_settings.MAX_TRANSCRIPT_CHARS = 12000

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(result_json)

            from app.services.analyzer import analyze

            _, _, category, confidence = analyze("測試")
            assert category == "未分類 (Uncategorized)"
            assert confidence == 0.0

    def test_analyze_truncates_long_transcript(self):
        """逐字稿超長時截斷後送分析"""
        result_json = json.dumps(
            {
                "summary": "摘要",
                "key_points": ["重點"],
                "category": "未分類 (Uncategorized)",
                "confidence": 0.5,
            },
            ensure_ascii=False,
        )

        with (
            patch("app.services.analyzer._get_client") as mock_get,
            patch("app.services.analyzer.settings") as mock_settings,
            patch("app.services.analyzer.MAX_TRANSCRIPT_CHARS", 100),
        ):
            mock_settings.AZURE_OPENAI_DEPLOYMENT = "gpt-35-turbo"
            mock_settings.CATEGORIES = ["未分類 (Uncategorized)"]

            mock_client = MagicMock()
            mock_get.return_value = mock_client
            mock_client.chat.completions.create.return_value = self._make_mock_response(result_json)

            from app.services.analyzer import analyze

            long_text = "A" * 500
            analyze(long_text)

            # 確認送給 GPT 的 prompt 包含省略提示
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args.kwargs["messages"]
            user_msg = messages[1]["content"]
            assert "省略" in user_msg
