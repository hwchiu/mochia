"""Project-wide constants — single source of truth for magic numbers and shared literals.

Keeping all tunable values here makes cost / performance trade-offs explicit and easy
to adjust in one place without hunting through multiple files.
"""

from __future__ import annotations

# ── Video streaming ───────────────────────────────────────────────────────────

# Formats that require server-side FFmpeg transcoding before the browser can play them.
BROWSER_UNSUPPORTED_FORMATS: frozenset[str] = frozenset({".wmv", ".mkv", ".avi", ".flv"})

# Byte-count for each chunk yielded by the FFmpeg streaming generator (64 KB).
STREAM_CHUNK_SIZE: int = 64 * 1024

# ── Transcript / GPT token budgets ───────────────────────────────────────────

# Maximum characters of raw transcript fed to GPT per analysis request.
# Preserving start + end sections and omitting the middle keeps most context
# while staying well within GPT context limits and controlling input token cost.
MAX_TRANSCRIPT_CHARS: int = 8_000

# Smaller context window used for Q&A chat.  Summary + key_points already
# capture all essential information; the full raw transcript is not needed per
# question, which cuts input tokens by ~70-80% on every /ask call.
ASK_CONTEXT_CHARS: int = 3_000

# Maximum number of chat message rows loaded from DB per Q&A request.
# Prevents unbounded memory use on long-running video conversations.
CHAT_HISTORY_LIMIT: int = 200
