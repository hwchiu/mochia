"""使用 Azure OpenAI GPT 進行影片內容分析：摘要、重點提取、分類"""

from __future__ import annotations

import json
import logging
import threading

import openai
from openai import AzureOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.constants import ASK_CONTEXT_CHARS, MAX_TRANSCRIPT_CHARS

logger = logging.getLogger(__name__)

_client: AzureOpenAI | None = None
_client_lock = threading.Lock()


def _prepare_transcript(transcript: str, max_chars: int | None = None) -> str:
    """Truncate transcript to fit GPT context window, preserving start and end."""
    limit = max_chars if max_chars is not None else MAX_TRANSCRIPT_CHARS
    if len(transcript) <= limit:
        return transcript
    half = limit // 2
    return transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]


def _get_client() -> AzureOpenAI:
    global _client
    with _client_lock:
        if _client is None:
            if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
                raise ValueError("AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 未設定")
            _client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_version=settings.AZURE_OPENAI_API_VERSION,
            )
    return _client


@retry(
    retry=retry_if_exception_type(
        (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)
    ),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _chat(system_prompt: str, user_content: str, max_tokens: int = 2000) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=max_tokens,  # 新一代模型（o1/o3/gpt-5系列）使用此參數
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def generate_faq(transcript: str) -> list[dict]:
    """Generate FAQ list (5-8 Q&A pairs) from transcript.

    Args:
        transcript: Full transcript text to extract questions and answers from.

    Returns:
        List of dicts with 'question' and 'answer' keys. Returns empty list
        if JSON parsing fails.

    Raises:
        openai.APIError: If API call fails after retries.
    """
    transcript_for_gpt = _prepare_transcript(transcript)

    system_prompt = """你是一位教育內容專家，擅長從影片內容提取常見問題。
請根據影片逐字稿，生成 5-8 個常見問答（FAQ）。
以 JSON 陣列格式回傳，不要有任何額外說明。"""

    user_content = f"""請根據以下逐字稿生成 FAQ：

{transcript_for_gpt}

請以 JSON 格式回傳（純 JSON，不要 markdown code block）：
[
  {{"question": "問題1", "answer": "回答1"}},
  {{"question": "問題2", "answer": "回答2"}},
  ...
]

要求：
- 5-8 個問答對
- 問題要實際且有教育價值
- 回答要簡潔但完整
- 使用繁體中文"""

    logger.info("開始生成 FAQ...")
    raw = _chat(system_prompt, user_content)

    # Parse JSON, handle markdown code blocks
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        raw = raw.strip()

    try:
        faq_list = json.loads(raw)
        if not isinstance(faq_list, list):
            faq_list = []
    except json.JSONDecodeError:
        logger.warning("FAQ JSON 解析失敗，返回空列表")
        faq_list = []

    logger.info(f"FAQ 生成完成，共 {len(faq_list)} 個問答")
    return faq_list


def ask_question(transcript: str, question: str, chat_history: list[dict]) -> str:
    """Answer a question about the video using multi-turn conversation.

    Args:
        transcript: Context string for the answer — ideally a pre-built summary
            (summary + key_points) passed from the router, which is much shorter
            than a raw transcript and cuts input tokens by ~70-80% per call.
            Falls back gracefully to raw transcript if summary is unavailable.
        question: The user's question string.
        chat_history: List of previous message dicts with 'role' and 'content' keys.

    Returns:
        Assistant's answer as a string.

    Raises:
        ValueError: If Azure OpenAI credentials are not configured.
        openai.APIError: If the API call fails.
    """
    # Use a smaller context window for Q&A — we don't need the full raw transcript
    # because the caller passes summary + key_points as context (see analysis.py).
    context = _prepare_transcript(transcript, max_chars=ASK_CONTEXT_CHARS)

    system_prompt = f"""你是一位專業的影片內容助手，負責回答關於這支影片的問題。
請根據以下影片內容來回答問題，使用繁體中文。
如果問題與影片內容無關，請禮貌地重新引導回影片相關話題。

影片內容：
{context}"""

    client = _get_client()
    # list[Any] satisfies OpenAI's Iterable[ChatCompletionMessageParam] without
    # requiring a full cast chain for the mixed message dicts we build here.
    from typing import Any

    messages: list[Any] = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-10:])
    messages.append({"role": "user", "content": question})

    logger.info("開始 ask_question...")
    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=messages,
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def suggest_labels(summary: str) -> list[str]:
    """根據影片摘要，用 GPT 建議 3-5 個繁體中文標籤"""
    system_prompt = """你是一個影片內容標籤分類專家。
根據使用者提供的影片摘要，建議 3 到 5 個簡短的繁體中文標籤。

標籤要求：
- 每個標籤 2-6 個字
- 反映影片的核心主題、關鍵概念或應用領域
- 避免太模糊的標籤（如「知識」、「介紹」）
- 請用 JSON 陣列格式回傳，例如：["標籤1", "標籤2", "標籤3"]
- 只回傳 JSON 陣列，不要有其他文字"""

    raw = _chat(system_prompt, f"影片摘要：\n{summary[:1500]}")
    try:
        # 嘗試解析 JSON
        start = raw.find("[")
        end = raw.rfind("]") + 1
        labels = json.loads(raw[start:end])
        return [str(item).strip() for item in labels if str(item).strip()][:5]
    except json.JSONDecodeError:
        logger.warning("suggest_labels JSON 解析失敗: %r", raw)
        return []


def analyze_all(
    transcript: str,
) -> tuple[str, list[dict], str, float, list[dict]]:
    """Single GPT call combining analyze + faq to reduce token usage.

    Returns:
        Tuple of (summary, key_points, category, confidence, faq_list)
    """
    transcript_for_gpt = _prepare_transcript(transcript)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        logger.info(f"逐字稿過長 ({len(transcript)} 字)，已截斷送分析")

    categories_str = "\n".join(f"- {c}" for c in settings.CATEGORIES)

    system_prompt = """你是一位專業的玄學內容分析師，擅長占星學、風水、奇門遁甲等東方玄學領域。
請根據影片逐字稿，以 JSON 格式一次回傳所有分析結果，不要有任何額外文字。"""

    user_content = f"""請分析以下影片逐字稿，以 JSON 格式回傳（所有欄位必填）：

逐字稿：
{transcript_for_gpt}

JSON 格式：
{{
  "summary": "影片內容完整摘要（繁體中文，600-1000字）",
  "key_points": [
    {{
      "theme": "主題名稱（4-12字）",
      "points": ["具體說明", "..."]
    }}
  ],
  "category": "從可選類別選一",
  "confidence": 0.85,
  "faq": [
    {{"question": "問題1", "answer": "回答1"}},
    {{"question": "問題2", "answer": "回答2"}}
  ]
}}

可選類別：
{categories_str}

注意：
- summary 詳盡完整，600-1000字，繁體中文，段落間有邏輯銜接
- key_points 列出 5-8 個主題，每個主題 3-5 條具體說明
- faq 提供 5-8 個問答，問題有教育價值，回答簡潔完整
- category 必須完全符合可選類別之一
- confidence 為 0-1 之間的浮點數"""

    logger.info("開始 GPT 合併分析（摘要 + 分類 + FAQ）")
    raw = _chat(system_prompt, user_content, max_tokens=5000)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("analyze_all GPT 回傳無效 JSON，raw=%r", raw[:200])
        raise ValueError(f"GPT 回傳無效 JSON: {raw[:100]}") from exc

    summary = result.get("summary", "")
    raw_kp = result.get("key_points", [])
    if raw_kp and isinstance(raw_kp[0], str):
        key_points = [{"theme": "重點整理", "points": raw_kp}]
    else:
        key_points = raw_kp

    category = result.get("category", "未分類 (Uncategorized)")
    confidence = float(result.get("confidence", 0.5))
    if category not in settings.CATEGORIES:
        logger.warning(f"GPT 回傳未知分類 '{category}'，改用未分類")
        category = "未分類 (Uncategorized)"
        confidence = 0.0

    faq_raw = result.get("faq", [])
    faq_list = faq_raw if isinstance(faq_raw, list) else []

    logger.info(f"合併分析完成 - 分類: {category} ({confidence:.0%})")
    return summary, key_points, category, confidence, faq_list


def _seg_to_line(seg: dict) -> str:
    """Convert a Whisper segment dict to a '[MM:SS] text' line."""
    mm, ss = divmod(int(seg.get("start", 0)), 60)
    return f"[{mm:02d}:{ss:02d}] {seg.get('text', '').strip()}"


def _format_timestamped_transcript(
    segments: list[dict], max_chars: int = MAX_TRANSCRIPT_CHARS
) -> str:
    """Format Whisper segments as [MM:SS] timestamped lines, truncated to max_chars.

    When the full text exceeds max_chars, keeps the first half and last half of
    lines with an ellipsis marker in between to preserve context for the LLM.

    Args:
        segments: List of Whisper segment dicts with 'start', 'end', and 'text' keys.
        max_chars: Maximum total characters to include in the output.

    Returns:
        Newline-joined string of "[MM:SS] text" lines.
    """
    all_lines = [_seg_to_line(s) for s in segments]
    full_text = "\n".join(all_lines)
    if len(full_text) <= max_chars:
        return full_text

    half = max_chars // 2

    head: list[str] = []
    head_chars = 0
    for line in all_lines:
        if head_chars + len(line) + 1 > half:
            break
        head.append(line)
        head_chars += len(line) + 1

    tail: list[str] = []
    tail_chars = 0
    for line in reversed(all_lines):
        if tail_chars + len(line) + 1 > half:
            break
        tail.insert(0, line)
        tail_chars += len(line) + 1

    return "\n".join(head) + "\n\n[... 中間內容省略 ...]\n\n" + "\n".join(tail)


def generate_deep_content(transcript: str, segments: list[dict] | None = None) -> tuple[str, str]:
    """Single GPT call combining study_notes + case_analysis to reduce token usage.

    Args:
        transcript: Full transcript text. Used when segments is None.
        segments: Optional list of Whisper segment dicts with 'start', 'end', and 'text'.
            When provided, a timestamped transcript is passed to GPT and the LLM is
            instructed to annotate case analyses with [MM:SS] markers.

    Returns:
        Tuple of (study_notes, case_analysis) where case_analysis is empty string
        if no cases are found in the transcript.
    """
    if segments:
        transcript_for_gpt = _format_timestamped_transcript(segments)
        timestamp_instruction = "在案例分析中，請以 [MM:SS] 格式標注每個案例的對應影片時間點"
    else:
        transcript_for_gpt = _prepare_transcript(transcript)
        timestamp_instruction = ""

    system_prompt = """你是一位專業的學習顧問與玄學分析師。
請根據影片逐字稿，以 JSON 格式同時回傳學習筆記與案例分析，不要有任何額外文字。"""

    timestamp_note = f"\n- {timestamp_instruction}" if timestamp_instruction else ""
    user_content = f"""請根據以下逐字稿生成學習筆記和案例分析，以 JSON 格式回傳：

{transcript_for_gpt}

JSON 格式：
{{
  "study_notes": "## 核心概念\\n（影片的核心思想）\\n\\n## 重要術語\\n（術語及解釋）\\n\\n## 學習重點\\n（條列重點）\\n\\n## 實踐建議\\n（應用建議）\\n\\n## 延伸思考\\n（深度思考問題）",
  "case_analysis": "## 案例1\\n（若無案例請填入字串 NO_CASE_ANALYSIS）"
}}

study_notes 要求：包含核心概念、重要術語、學習重點、實踐建議、延伸思考，繁體中文 Markdown。
case_analysis 要求：若有案例詳細記錄（背景、分析要點、推論、結論）；若完全無案例填 NO_CASE_ANALYSIS。{timestamp_note}"""

    logger.info("開始生成深度內容（學習筆記 + 案例分析）")
    raw = _chat(system_prompt, user_content, max_tokens=2500)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("generate_deep_content JSON 解析失敗，返回空結果")
        return "", ""

    study_notes = result.get("study_notes", "")
    case_raw = result.get("case_analysis", "").strip()
    case_analysis = "" if case_raw == "NO_CASE_ANALYSIS" or not case_raw else case_raw

    logger.info("深度內容生成完成")
    return study_notes, case_analysis


def extract_case_analysis(transcript: str) -> str:
    """Detect and extract case analysis content from transcript.

    Args:
        transcript: Full transcript text to scan for case study content.

    Returns:
        Markdown-formatted case analysis string, or empty string if no cases
        are found in the transcript.

    Raises:
        openai.APIError: If API call fails after retries.
    """
    transcript_for_gpt = _prepare_transcript(transcript)

    system_prompt = """你是一位專業的玄學內容分析師。
你的任務是從影片逐字稿中識別並詳細記錄所有「案例分析」內容。

案例分析的定義：
- 老師以具體的真實或假設案例（如某人的命盤、八字、風水格局、奇門布局等）進行分析演示
- 包含具體的人物背景、問題情境、分析推論過程、以及結論

輸出規範：
- 若有案例，使用 Markdown 格式詳細記錄，每個案例以 ## 案例N 為標題
- 每個案例包含：背景說明、分析要點（條列）、推論過程、結論
- 盡量保留原始分析的細節，讓讀者能完整複習
- 若逐字稿中完全沒有案例分析內容，只回傳：NO_CASE_ANALYSIS
- 不要有任何其他說明文字，只輸出案例內容或 NO_CASE_ANALYSIS"""

    user_content = f"""請從以下影片逐字稿中擷取所有案例分析內容：

{transcript_for_gpt}"""

    logger.info("開始擷取案例分析...")
    raw = _chat(system_prompt, user_content, max_tokens=3000)
    raw = raw.strip()

    if raw == "NO_CASE_ANALYSIS" or not raw:
        logger.info("影片無案例分析內容")
        return ""

    logger.info("案例分析擷取完成")
    return raw
