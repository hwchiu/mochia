"""Unit tests for the GPT analyzer service and utility helpers."""
from __future__ import annotations

from app.services.analyzer import MAX_TRANSCRIPT_CHARS, _prepare_transcript


class TestPrepareTranscript:
    def test_short_transcript_unchanged(self):
        text = "Hello world"
        assert _prepare_transcript(text) == text

    def test_long_transcript_truncated(self):
        text = "A" * (MAX_TRANSCRIPT_CHARS + 100)
        result = _prepare_transcript(text)
        assert len(result) < len(text)
        assert "省略" in result

    def test_long_transcript_preserves_start_and_end(self):
        start = "START" * 100
        end = "END" * 100
        middle = "MIDDLE" * 10000
        text = start + middle + end
        result = _prepare_transcript(text)
        assert result.startswith("START")
        assert "END" in result[-50:]

    def test_exact_limit_not_truncated(self):
        text = "X" * MAX_TRANSCRIPT_CHARS
        result = _prepare_transcript(text)
        assert result == text

    def test_truncated_result_fits_max_chars(self):
        text = "Z" * (MAX_TRANSCRIPT_CHARS * 2)
        result = _prepare_transcript(text)
        # start + separator + end, separator is fixed text
        assert len(result) <= MAX_TRANSCRIPT_CHARS + 50

    def test_separator_present_only_when_truncated(self):
        short = "short text"
        long_text = "Y" * (MAX_TRANSCRIPT_CHARS + 1)
        assert "省略" not in _prepare_transcript(short)
        assert "省略" in _prepare_transcript(long_text)


class TestSafeJsonLoads:
    def test_valid_json_returns_parsed(self):
        from app.utils import safe_json_loads

        assert safe_json_loads('["a", "b"]', []) == ["a", "b"]

    def test_invalid_json_returns_fallback(self):
        from app.utils import safe_json_loads

        assert safe_json_loads("not json {{{", []) == []

    def test_none_returns_fallback(self):
        from app.utils import safe_json_loads

        assert safe_json_loads(None, {}) == {}

    def test_empty_string_returns_fallback(self):
        from app.utils import safe_json_loads

        assert safe_json_loads("", []) == []

    def test_valid_dict_json(self):
        from app.utils import safe_json_loads

        result = safe_json_loads('{"key": "value"}', {})
        assert result == {"key": "value"}

    def test_fallback_type_preserved(self):
        from app.utils import safe_json_loads

        result = safe_json_loads("bad json", {"default": True})
        assert result == {"default": True}
