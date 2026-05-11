"""
Wiki 知識庫測試
"""

from __future__ import annotations

import uuid

from app.database import (
    Concept,
    ConceptTopic,
    Topic,
    WikiPage,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_concept(db, name: str, video_count: int = 1) -> Concept:
    c = Concept(id=uuid.uuid4().hex, name=name, description=f"{name}的說明", video_count=video_count)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_topic(db, name: str, slug: str, parent_id=None, domain=None) -> Topic:
    t = Topic(
        id=uuid.uuid4().hex,
        name=name,
        slug=slug,
        parent_id=parent_id,
        domain=domain or name,
        description=f"{name}的說明",
        learning_order=1,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _make_wiki_page(db, concept_id: str, title: str, slug: str, status: str = "published") -> WikiPage:
    from datetime import datetime

    wp = WikiPage(
        id=uuid.uuid4().hex,
        concept_id=concept_id,
        title=title,
        slug=slug,
        synthesized_content=f"## 定義\n{title}的合成說明",
        source_video_count=1,
        last_synthesized_at=datetime.utcnow(),
        status=status,
    )
    db.add(wp)
    db.commit()
    db.refresh(wp)
    return wp


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/wiki/stats
# ═══════════════════════════════════════════════════════════════════════════════


class TestWikiStats:
    def test_returns_structure(self, client):
        r = client.get("/api/wiki/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ["total_topics", "total_domains", "total_wiki_pages", "published_wiki_pages"]:
            assert key in data

    def test_empty_when_no_data(self, client):
        r = client.get("/api/wiki/stats")
        data = r.json()
        assert data["total_topics"] == 0
        assert data["total_wiki_pages"] == 0

    def test_counts_after_data_added(self, client, db_session):
        domain = _make_topic(db_session, "占星學", "astrology", domain="占星學")
        _make_topic(db_session, "行星", "planets", parent_id=domain.id, domain="占星學")
        c = _make_concept(db_session, "太陽星座")
        _make_wiki_page(db_session, c.id, "太陽星座", "sun-sign")
        r = client.get("/api/wiki/stats")
        data = r.json()
        assert data["total_topics"] >= 2
        assert data["total_domains"] >= 1
        assert data["published_wiki_pages"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/wiki/topics
# ═══════════════════════════════════════════════════════════════════════════════


class TestListTopics:
    def test_empty(self, client):
        r = client.get("/api/wiki/topics")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["tree"] == []

    def test_returns_tree(self, client, db_session):
        domain = _make_topic(db_session, "占星學", "astro", domain="占星學")
        _make_topic(db_session, "行星", "planets", parent_id=domain.id, domain="占星學")
        r = client.get("/api/wiki/topics")
        data = r.json()
        assert data["total"] == 2
        tree = data["tree"]
        assert len(tree) == 1
        assert tree[0]["name"] == "占星學"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["name"] == "行星"

    def test_topic_has_required_fields(self, client, db_session):
        _make_topic(db_session, "風水", "fengshui")
        tree = client.get("/api/wiki/topics").json()["tree"]
        item = tree[0]
        for field in ["id", "name", "slug", "description", "concept_count", "children"]:
            assert field in item


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/wiki/topics/{topic_id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetTopic:
    def test_not_found(self, client):
        r = client.get("/api/wiki/topics/nonexistent")
        assert r.status_code == 404

    def test_returns_topic(self, client, db_session):
        t = _make_topic(db_session, "奇門遁甲", "qimen")
        r = client.get(f"/api/wiki/topics/{t.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "奇門遁甲"
        assert data["slug"] == "qimen"


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/wiki/pages
# ═══════════════════════════════════════════════════════════════════════════════


class TestListWikiPages:
    def test_empty(self, client):
        r = client.get("/api/wiki/pages")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_returns_published(self, client, db_session):
        c = _make_concept(db_session, "月亮星座")
        _make_wiki_page(db_session, c.id, "月亮星座", "moon-sign")
        r = client.get("/api/wiki/pages")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "月亮星座"

    def test_filters_by_status(self, client, db_session):
        c1 = _make_concept(db_session, "A概念")
        c2 = _make_concept(db_session, "B概念")
        _make_wiki_page(db_session, c1.id, "A概念", "a-concept", status="published")
        _make_wiki_page(db_session, c2.id, "B概念", "b-concept", status="stale")
        r = client.get("/api/wiki/pages?status=stale")
        data = r.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "B概念"

    def test_items_have_required_fields(self, client, db_session):
        c = _make_concept(db_session, "測試頁面")
        _make_wiki_page(db_session, c.id, "測試頁面", "test-page")
        item = client.get("/api/wiki/pages").json()["items"][0]
        for field in ["id", "title", "slug", "status", "source_video_count"]:
            assert field in item


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/wiki/pages/{id_or_slug}
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetWikiPage:
    def test_not_found(self, client):
        r = client.get("/api/wiki/pages/nonexistent")
        assert r.status_code == 404

    def test_by_id(self, client, db_session):
        c = _make_concept(db_session, "上升星座")
        wp = _make_wiki_page(db_session, c.id, "上升星座", "rising-sign")
        r = client.get(f"/api/wiki/pages/{wp.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "上升星座"
        assert "synthesized_content" in data
        assert "sources" in data

    def test_by_slug(self, client, db_session):
        c = _make_concept(db_session, "宮位")
        _make_wiki_page(db_session, c.id, "宮位", "house-system")
        r = client.get("/api/wiki/pages/house-system")
        assert r.status_code == 200
        assert r.json()["slug"] == "house-system"


# ═══════════════════════════════════════════════════════════════════════════════
# HTML Pages
# ═══════════════════════════════════════════════════════════════════════════════


class TestWikiHTMLPages:
    def test_wiki_index_ok(self, client):
        r = client.get("/wiki")
        assert r.status_code == 200
        assert "知識庫" in r.text

    def test_wiki_index_shows_domains(self, client, db_session):
        _make_topic(db_session, "占星學", "astro-html", domain="占星學")
        r = client.get("/wiki")
        assert r.status_code == 200
        assert "占星學" in r.text

    def test_wiki_topic_page(self, client, db_session):
        domain = _make_topic(db_session, "風水學", "fengshui-html", domain="風水學")
        c = _make_concept(db_session, "山形")
        ct = ConceptTopic(id=uuid.uuid4().hex, concept_id=c.id, topic_id=domain.id)
        db_session.add(ct)
        db_session.commit()
        r = client.get("/wiki/fengshui-html")
        assert r.status_code == 200
        assert "風水學" in r.text

    def test_wiki_topic_not_found(self, client):
        r = client.get("/wiki/nonexistent-topic")
        assert r.status_code == 404

    def test_wiki_concept_page(self, client, db_session):
        c = _make_concept(db_session, "紫微星")
        wp = _make_wiki_page(db_session, c.id, "紫微星", "ziwei-star")
        r = client.get(f"/wiki/concept/{wp.slug}")
        assert r.status_code == 200
        assert "紫微星" in r.text

    def test_wiki_concept_not_found(self, client):
        r = client.get("/wiki/concept/no-such-concept")
        assert r.status_code == 404

    def test_wiki_concept_shows_content(self, client, db_session):
        c = _make_concept(db_session, "土星回歸")
        wp = _make_wiki_page(db_session, c.id, "土星回歸", "saturn-return")
        r = client.get(f"/wiki/concept/{wp.slug}")
        assert "土星回歸" in r.text


# ═══════════════════════════════════════════════════════════════════════════════
# taxonomy_builder._slugify unit tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSlugify:
    def test_basic(self):
        from app.services.taxonomy_builder import _slugify

        assert _slugify("占星學") == "占星學"

    def test_spaces_become_hyphens(self):
        from app.services.taxonomy_builder import _slugify

        assert _slugify("行星 逆行") == "行星-逆行"

    def test_parentheses_removed(self):
        from app.services.taxonomy_builder import _slugify

        # Parentheses become hyphens and then cleaned
        result = _slugify("占星學 (Astrology)")
        assert "astrology" in result

    def test_unique_slug_adds_counter(self):
        from app.services.taxonomy_builder import _unique_slug

        existing = {"test", "test-2"}
        result = _unique_slug("test", existing)
        assert result == "test-3"
        assert "test-3" in existing


# ═══════════════════════════════════════════════════════════════════════════════
# wiki_synthesizer unit tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestWikiSynthesizer:
    def test_synthesize_nonexistent_concept(self, db_session):
        from app.services.wiki_synthesizer import synthesize_wiki_page

        result = synthesize_wiki_page("nonexistent", db_session)
        assert result is None

    def test_synthesize_with_no_segments(self, db_session, monkeypatch):
        from unittest.mock import patch

        from app.services.wiki_synthesizer import synthesize_wiki_page

        c = _make_concept(db_session, "虛構概念")
        # Concept has a description; patch GPT to avoid real API call
        with patch("app.services.analyzer._chat", return_value="## 定義\n虛構概念是一個測試概念。"):
            result = synthesize_wiki_page(c.id, db_session)
        # With description as fallback, GPT is called and a WikiPage is created
        assert isinstance(result, WikiPage)
        assert result.title == "虛構概念"

    def test_mark_stale(self, db_session):
        from app.services.wiki_synthesizer import mark_concept_wiki_stale

        c = _make_concept(db_session, "需更新概念")
        _make_wiki_page(db_session, c.id, "需更新概念", "stale-test")
        mark_concept_wiki_stale(c.id, db_session)
        db_session.commit()
        wp = db_session.query(WikiPage).filter(WikiPage.slug == "stale-test").first()
        assert wp.status == "stale"

    def test_format_mmss(self):
        from app.services.wiki_synthesizer import _format_mmss

        assert _format_mmss(0) == "00:00"
        assert _format_mmss(65) == "01:05"
        assert _format_mmss(3600) == "60:00"
        assert _format_mmss(None) is None
