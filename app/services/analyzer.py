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
  "summary": "影片內容完整摘要（繁體中文）",
  "key_points": [
    {{
      "theme": "主題名稱（4-12字）",
      "points": ["具體說明或重點敘述", "..."]
    }}
  ],
  "category": "從以下類別選擇最符合的一個",
  "confidence": 0.85
}}

可選類別：
{categories_str}

注意：
- summary 要詳盡完整，至少 600 字，最多 1200 字，繁體中文
  * 第一段：概述影片整體主題、講師立場與核心論點（3-4句）
  * 中間多個段落：依序詳細介紹影片各重要段落的內容、概念說明與觀點（每段落至少3-4句）
  * 最後一段：總結影片整體的實用價值、學習重點與核心結論（2-3句）
  * 段落與段落之間要有明確的邏輯銜接
- key_points 列出 5-8 個主題，涵蓋影片所有重要段落
  * 主題名稱要精準概括該段落的核心概念
  * 每個主題下至少 3-5 條敘述說明
  * 每條敘述要完整具體，至少 2-3 句話，包含概念說明、背景脈絡或實際應用
  * 讓讀者光看重點就能完整複習整部影片的內容
- category 必須完全符合可選類別之一
- confidence 為 0-1 之間的浮點數"""

    logger.info("開始 GPT 分析（摘要 + 重點 + 分類）")
    raw = _chat(system_prompt, user_content, max_tokens=5000)

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


def suggest_labels(summary: str) -> List[str]:
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
        return [str(l).strip() for l in labels if str(l).strip()][:5]
    except Exception:
        logger.warning(f"suggest_labels JSON 解析失敗: {raw}")
        return []


def extract_case_analysis(transcript: str) -> str:
    """
    從逐字稿中偵測並擷取案例分析內容。

    若影片包含案例分析、實例演示或具體案例，回傳詳細的 Markdown 格式紀錄。
    若影片沒有案例分析內容，回傳空字串。
    """
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        half = MAX_TRANSCRIPT_CHARS // 2
        transcript_for_gpt = transcript[:half] + "\n\n[... 中間內容省略 ...]\n\n" + transcript[-half:]
    else:
        transcript_for_gpt = transcript

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
