"""使用 Azure OpenAI GPT 進行影片內容分析：摘要、重點提取、分類"""
import json
import logging
from typing import Tuple, List, Dict

from openai import AzureOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: AzureOpenAI | None = None

# Whisper API 單次最大 25MB；超過此長度的逐字稿需截斷再送 GPT
MAX_TRANSCRIPT_CHARS = 12000


def _get_client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not settings.AZURE_OPENAI_API_KEY or not settings.AZURE_OPENAI_ENDPOINT:
            raise ValueError("AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 未設定")
        _client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version=settings.AZURE_OPENAI_API_VERSION,
        )
    return _client


def _chat(system_prompt: str, user_content: str) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_completion_tokens=2000,  # 新一代模型（o1/o3/gpt-5系列）使用此參數
    )
    return response.choices[0].message.content.strip()


def analyze(transcript: str) -> Tuple[str, list[str], str, float]:
    """
    對逐字稿執行完整分析：摘要、重點、分類。

    Args:
        transcript: 影片逐字稿文字

    Returns:
        (summary, key_points, category, confidence)
        - summary: 摘要文字
        - key_points: 重點清單（List[str]）
        - category: 分類名稱
        - confidence: 分類信心分數 0-1
    """
    # 逐字稿太長時截取前後各部分送 GPT
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = (
            transcript[:half]
            + "\n\n[... 中間內容省略 ...]\n\n"
            + transcript[-half:]
        )
        logger.info(f"逐字稿過長 ({len(transcript)} 字)，已截斷送分析")
    else:
        transcript_for_gpt = transcript

    categories_str = "\n".join(f"- {c}" for c in settings.CATEGORIES)

    system_prompt = """你是一位專業的玄學內容分析師，擅長占星學、風水、奇門遁甲等東方玄學領域。
請根據影片逐字稿，以 JSON 格式回傳分析結果，不要有任何額外文字。"""

    user_content = f"""請分析以下影片逐字稿，並以 JSON 格式回傳：

逐字稿：
{transcript_for_gpt}

請回傳以下 JSON 格式（所有欄位必填）：
{{
  "summary": "影片內容摘要（200字以內，繁體中文）",
  "key_points": [
    {{
      "theme": "主題名稱（4-10字）",
      "points": ["具體說明或重點敘述（1-2句話）", "..."]
    }}
  ],
  "category": "從以下類別選擇最符合的一個",
  "confidence": 0.85
}}

可選類別：
{categories_str}

注意：
- summary 限 200 字以內，繁體中文
- key_points 列出 3-5 個主題，每個主題下有 2-4 條敘述說明，讓讀者快速複習影片內容
- 主題名稱要精準概括該段落的核心概念
- 每條敘述要具體、有內容，不要太短
- category 必須完全符合可選類別之一
- confidence 為 0-1 之間的浮點數"""

    logger.info("開始 GPT 分析（摘要 + 重點 + 分類）")
    raw = _chat(system_prompt, user_content)

    # 清除可能的 markdown code block
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0].strip()

    result = json.loads(raw)

    summary = result.get("summary", "")
    raw_kp = result.get("key_points", [])

    # 相容舊格式（字串陣列）自動轉換為新格式
    if raw_kp and isinstance(raw_kp[0], str):
        key_points = [{"theme": "重點整理", "points": raw_kp}]
    else:
        key_points = raw_kp

    category = result.get("category", "未分類 (Uncategorized)")
    confidence = float(result.get("confidence", 0.5))

    # 確保 category 在合法清單內
    if category not in settings.CATEGORIES:
        logger.warning(f"GPT 回傳未知分類 '{category}'，改用未分類")
        category = "未分類 (Uncategorized)"
        confidence = 0.0

    logger.info(f"分析完成 - 分類: {category} ({confidence:.0%})")
    return summary, key_points, category, confidence


def generate_mindmap(transcript: str) -> str:
    """Generate Markmap-compatible Markdown mind map from transcript."""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]
    else:
        transcript_for_gpt = transcript

    system_prompt = """你是一位專業的知識整理專家，擅長將內容整理成結構化的心智圖。
請根據影片逐字稿，生成 Markmap 相容的 Markdown 格式心智圖。
直接輸出 Markdown，不要有任何額外說明。"""

    user_content = f"""請將以下逐字稿整理成心智圖（Markmap Markdown 格式）：

{transcript_for_gpt}

要求：
- 使用 # 作為根節點（影片主題）
- 使用 ## 作為主要分支（3-5個）
- 使用 ### 作為子分支
- 使用 #### 作為細節（如有必要）
- 使用繁體中文
- 只輸出 Markdown，不要有任何額外說明"""

    logger.info("開始生成心智圖...")
    result = _chat(system_prompt, user_content)
    logger.info("心智圖生成完成")
    return result


def generate_faq(transcript: str) -> List[Dict]:
    """Generate FAQ list (5-8 Q&A pairs) from transcript."""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]
    else:
        transcript_for_gpt = transcript

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


def generate_study_notes(transcript: str) -> str:
    """Generate structured study notes in Markdown."""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]
    else:
        transcript_for_gpt = transcript

    system_prompt = """你是一位專業的學習顧問，擅長將影片內容整理成結構化的學習筆記。
請根據影片逐字稿，生成完整的學習筆記。
使用繁體中文，直接輸出 Markdown 格式。"""

    user_content = f"""請將以下逐字稿整理成學習筆記：

{transcript_for_gpt}

請以 Markdown 格式輸出，包含以下章節：

## 核心概念
（影片的核心思想和主要概念）

## 重要術語
（列出重要的術語及其解釋）

## 學習重點
（條列式的學習重點）

## 實踐建議
（如何應用所學的具體建議）

## 延伸思考
（引發深度思考的問題或觀點）"""

    logger.info("開始生成學習筆記...")
    result = _chat(system_prompt, user_content)
    logger.info("學習筆記生成完成")
    return result


def ask_question(transcript: str, question: str, chat_history: List[Dict]) -> str:
    """Answer a question about the video using multi-turn conversation."""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]
    else:
        transcript_for_gpt = transcript

    system_prompt = f"""你是一位專業的影片內容助手，負責回答關於這支影片的問題。
請根據以下影片逐字稿來回答問題，使用繁體中文。
如果問題與影片內容無關，請禮貌地重新引導回影片相關話題。

影片逐字稿：
{transcript_for_gpt}"""

    client = _get_client()
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-10:])
    messages.append({"role": "user", "content": question})

    logger.info("開始 ask_question...")
    response = client.chat.completions.create(
        model=settings.AZURE_OPENAI_DEPLOYMENT,
        messages=messages,
        max_completion_tokens=1000,
    )
    answer = response.choices[0].message.content.strip()
    logger.info("ask_question 完成")
    return answer
