"""知識庫主題分類樹建構器

使用 GPT 將現有概念組織成有層級的主題分類樹，並寫入 topics / concept_topics 表。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import Concept, ConceptTopic, Topic

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    import unicodedata

    # Normalize unicode (NFC → lower)
    text = unicodedata.normalize("NFKC", text).lower()
    # Replace spaces and common separators with hyphens
    text = re.sub(r"[\s/\\()（）【】「」：:]+", "-", text)
    # Remove characters that aren't alphanumeric, CJK, or hyphens
    text = re.sub(r"[^\w\-\u4e00-\u9fff]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or uuid.uuid4().hex[:8]


def _unique_slug(base: str, existing: set[str]) -> str:
    """Ensure slug is unique by appending a counter suffix if needed."""
    slug = base
    counter = 2
    while slug in existing:
        slug = f"{base}-{counter}"
        counter += 1
    existing.add(slug)
    return slug


def build_taxonomy(db: Session) -> dict:
    """GPT 分析現有概念，建立層級主題分類樹，寫入 DB。

    Returns:
        dict with keys: domains_created, topics_created, concept_links_created
    """
    from app.services.analyzer import _chat

    # ── 取得所有概念名稱 ──────────────────────────────────────────────────────
    concepts = db.query(Concept).all()
    if not concepts:
        logger.info("build_taxonomy: 無概念可分類，跳過")
        return {"domains_created": 0, "topics_created": 0, "concept_links_created": 0}

    concept_names = [c.name for c in concepts]
    concept_name_to_id = {c.name: str(c.id) for c in concepts}

    logger.info("build_taxonomy: 開始分類 %d 個概念", len(concept_names))

    # ── 呼叫 GPT 建立分類樹 ───────────────────────────────────────────────────
    system_prompt = """你是一位知識管理專家，擅長將玄學、命理、占星等領域的知識組織成學習路徑。
請將提供的概念列表，組織成 2-3 層的主題分類樹，以幫助學習者系統地學習。
只以 JSON 格式回傳，不要額外說明或 markdown。"""

    names_text = "\n".join(f"- {n}" for n in concept_names[:200])  # limit input size
    user_content = f"""請將以下知識概念組織成有層級的主題分類樹（2-3 層）。

概念列表：
{names_text}

請以 JSON 格式回傳（純 JSON，不要 markdown code block）：
[
  {{
    "name": "領域名稱（如：占星學）",
    "description": "領域說明（2-4句）",
    "learning_order": 1,
    "children": [
      {{
        "name": "子主題名稱（如：行星）",
        "description": "子主題說明",
        "learning_order": 1,
        "concepts": ["概念名稱1", "概念名稱2"],
        "children": [
          {{
            "name": "更細主題（選配）",
            "description": "說明",
            "learning_order": 1,
            "concepts": ["概念名稱"]
          }}
        ]
      }}
    ]
  }}
]

要求：
- 分類必須根據概念內容，不要虛構不存在的概念
- concepts 陣列只能包含輸入概念列表中確實存在的概念名稱
- 每個主題的 description 要說明學習此主題的重要性
- learning_order 從 1 開始排序，代表建議學習順序
- 頂層為領域（domain），第二層為分類（category），第三層（選配）為子主題"""

    raw = _chat(system_prompt, user_content, max_tokens=4000)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        taxonomy = json.loads(raw)
        if not isinstance(taxonomy, list):
            logger.warning("build_taxonomy: GPT 回傳非列表")
            return {"domains_created": 0, "topics_created": 0, "concept_links_created": 0}
    except json.JSONDecodeError:
        logger.warning("build_taxonomy: JSON 解析失敗, raw=%r", raw[:300])
        return {"domains_created": 0, "topics_created": 0, "concept_links_created": 0}

    # ── 寫入 DB ───────────────────────────────────────────────────────────────
    now = datetime.utcnow()
    existing_slugs: set[str] = {str(t.slug) for t in db.query(Topic).all()}
    concept_links_created = 0
    topics_created = 0
    domains_created = 0

    def _upsert_topic(
        name: str,
        description: str | None,
        learning_order: int,
        parent_id: str | None,
        domain: str | None,
    ) -> str:
        nonlocal topics_created, domains_created
        existing = db.query(Topic).filter(Topic.name == name).first()
        if existing:
            existing.description = description or existing.description  # type: ignore[assignment]
            existing.learning_order = learning_order  # type: ignore[assignment]
            existing.updated_at = now  # type: ignore[assignment]
            return str(existing.id)
        slug = _unique_slug(_slugify(name), existing_slugs)
        topic_id = uuid.uuid4().hex
        db.add(
            Topic(
                id=topic_id,
                name=name,
                slug=slug,
                parent_id=parent_id,
                domain=domain,
                description=description,
                learning_order=learning_order,
                created_at=now,
                updated_at=now,
            )
        )
        if parent_id is None:
            domains_created += 1
        else:
            topics_created += 1
        return topic_id

    def _link_concepts(concept_names_list: list[str], topic_id: str) -> None:
        nonlocal concept_links_created
        for cname in concept_names_list:
            concept_id = concept_name_to_id.get(cname)
            if not concept_id:
                continue
            exists = (
                db.query(ConceptTopic)
                .filter(
                    ConceptTopic.concept_id == concept_id,
                    ConceptTopic.topic_id == topic_id,
                )
                .first()
            )
            if not exists:
                db.add(
                    ConceptTopic(
                        id=uuid.uuid4().hex,
                        concept_id=concept_id,
                        topic_id=topic_id,
                        created_at=now,
                    )
                )
                concept_links_created += 1

    def _process_node(
        node: dict,
        parent_id: str | None,
        domain_name: str | None,
    ) -> None:
        if not isinstance(node, dict):
            return
        name = str(node.get("name", "")).strip()
        if not name:
            return
        description = node.get("description") or None
        learning_order = int(node.get("learning_order") or 0)
        domain = domain_name or name  # top-level nodes are their own domain

        topic_id = _upsert_topic(name, description, learning_order, parent_id, domain)
        db.flush()

        # Link concepts at this level
        concepts_here = node.get("concepts") or []
        if isinstance(concepts_here, list):
            _link_concepts(concepts_here, topic_id)

        # Recurse into children
        children = node.get("children") or []
        if isinstance(children, list):
            for child in children:
                _process_node(child, topic_id, domain)

    for domain_node in taxonomy:
        _process_node(domain_node, parent_id=None, domain_name=None)

    db.commit()
    logger.info(
        "build_taxonomy: 完成 — 領域 %d, 主題 %d, 概念連結 %d",
        domains_created,
        topics_created,
        concept_links_created,
    )
    return {
        "domains_created": domains_created,
        "topics_created": topics_created,
        "concept_links_created": concept_links_created,
    }
