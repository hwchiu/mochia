"""
知識點（概念）API 測試
"""

import json
import uuid

from app.database import Concept, ConceptRelation, SegmentConcept, Transcript, Video

# ─── 輔助：建立概念資料 ───────────────────────────────────────────────────────


def _make_concept(db, name: str, description: str = "", video_count: int = 0) -> Concept:
    c = Concept(
        id=uuid.uuid4().hex,
        name=name,
        description=description,
        video_count=video_count,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _make_seg_concept(
    db,
    video_id: str,
    concept_id: str,
    seg_idx: int = 0,
    start_sec: float = 0.0,
    end_sec: float = 5.0,
) -> SegmentConcept:
    sc = SegmentConcept(
        id=uuid.uuid4().hex,
        video_id=video_id,
        concept_id=concept_id,
        seg_idx=seg_idx,
        start_sec=start_sec,
        end_sec=end_sec,
    )
    db.add(sc)
    db.commit()
    return sc


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/concepts/ — 列出知識點
# ═══════════════════════════════════════════════════════════════════════════════


class TestListConcepts:
    def test_empty_returns_structure(self, client):
        r = client.get("/api/concepts/")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data
        assert "items" in data
        assert data["total"] == 0

    def test_returns_created_concept(self, client, db_session):
        _make_concept(db_session, "占星學基礎", "占星學的入門概念", video_count=2)
        r = client.get("/api/concepts/")
        data = r.json()
        assert data["total"] == 1
        item = data["items"][0]
        assert item["name"] == "占星學基礎"
        assert item["video_count"] == 2

    def test_sorted_by_video_count_desc(self, client, db_session):
        _make_concept(db_session, "A概念", video_count=1)
        _make_concept(db_session, "B概念", video_count=5)
        _make_concept(db_session, "C概念", video_count=3)
        r = client.get("/api/concepts/")
        counts = [i["video_count"] for i in r.json()["items"]]
        assert counts == sorted(counts, reverse=True)

    def test_limit_parameter(self, client, db_session):
        for i in range(10):
            _make_concept(db_session, f"概念{i}")
        r = client.get("/api/concepts/?limit=3")
        assert len(r.json()["items"]) <= 3

    def test_items_have_required_fields(self, client, db_session):
        _make_concept(db_session, "測試概念", "說明")
        item = client.get("/api/concepts/").json()["items"][0]
        for field in ["id", "name", "description", "video_count"]:
            assert field in item


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/concepts/{concept_id} — 取得單一知識點
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetConcept:
    def test_not_found_returns_404(self, client):
        r = client.get("/api/concepts/nonexistent")
        assert r.status_code == 404

    def test_returns_concept_data(self, client, db_session):
        c = _make_concept(db_session, "月亮星座", "月亮所在星座代表情緒反應模式")
        r = client.get(f"/api/concepts/{c.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "月亮星座"
        assert "relations" in data
        assert "segments" in data

    def test_includes_relations(self, client, db_session):
        c1 = _make_concept(db_session, "太陽星座")
        c2 = _make_concept(db_session, "上升星座")
        rel = ConceptRelation(
            id=uuid.uuid4().hex,
            source_concept_id=c1.id,
            target_concept_id=c2.id,
            relation_type="related",
        )
        db_session.add(rel)
        db_session.commit()

        r = client.get(f"/api/concepts/{c1.id}")
        data = r.json()
        assert len(data["relations"]) >= 1
        assert any(rel["name"] == "上升星座" for rel in data["relations"])

    def test_includes_segment_links(self, client, db_session, completed_video):
        c = _make_concept(db_session, "行星逆行")
        _make_seg_concept(
            db_session, completed_video.id, c.id, seg_idx=0, start_sec=83.0, end_sec=91.0
        )
        # Update video_count
        db_session.query(Concept).filter(Concept.id == c.id).update({"video_count": 1})
        db_session.commit()

        r = client.get(f"/api/concepts/{c.id}")
        data = r.json()
        assert len(data["segments"]) == 1
        seg = data["segments"][0]
        assert seg["start_sec"] == 83.0
        assert seg["timestamp"] == "01:23"

    def test_segment_has_required_fields(self, client, db_session, completed_video):
        c = _make_concept(db_session, "命盤解讀")
        _make_seg_concept(db_session, completed_video.id, c.id)
        r = client.get(f"/api/concepts/{c.id}")
        seg = r.json()["segments"][0]
        for field in ["video_id", "video_filename", "seg_idx", "start_sec", "end_sec", "timestamp"]:
            assert field in seg


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/concepts/by-video/{video_id} — 取得影片的知識點
# ═══════════════════════════════════════════════════════════════════════════════


class TestConceptsByVideo:
    def test_not_found_returns_404(self, client):
        r = client.get("/api/concepts/by-video/nonexistent")
        assert r.status_code == 404

    def test_empty_when_no_concepts(self, client, completed_video):
        r = client.get(f"/api/concepts/by-video/{completed_video.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_returns_concepts_with_segments(self, client, db_session, completed_video):
        c1 = _make_concept(db_session, "天王星")
        c2 = _make_concept(db_session, "土星回歸")
        _make_seg_concept(
            db_session, completed_video.id, c1.id, seg_idx=0, start_sec=10.0, end_sec=18.0
        )
        _make_seg_concept(
            db_session, completed_video.id, c2.id, seg_idx=1, start_sec=30.0, end_sec=40.0
        )

        r = client.get(f"/api/concepts/by-video/{completed_video.id}")
        data = r.json()
        assert data["total"] == 2
        names = {item["name"] for item in data["items"]}
        assert "天王星" in names
        assert "土星回歸" in names

    def test_sorted_by_first_segment_time(self, client, db_session, completed_video):
        c1 = _make_concept(db_session, "較晚概念")
        c2 = _make_concept(db_session, "較早概念")
        _make_seg_concept(
            db_session, completed_video.id, c1.id, seg_idx=2, start_sec=60.0, end_sec=70.0
        )
        _make_seg_concept(
            db_session, completed_video.id, c2.id, seg_idx=0, start_sec=5.0, end_sec=12.0
        )
        r = client.get(f"/api/concepts/by-video/{completed_video.id}")
        items = r.json()["items"]
        assert items[0]["name"] == "較早概念"

    def test_items_have_required_fields(self, client, db_session, completed_video):
        c = _make_concept(db_session, "測試知識點")
        _make_seg_concept(db_session, completed_video.id, c.id)
        item = client.get(f"/api/concepts/by-video/{completed_video.id}").json()["items"][0]
        for field in ["id", "name", "description", "segments"]:
            assert field in item


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/concepts/rebuild/{video_id} — 重建知識點
# ═══════════════════════════════════════════════════════════════════════════════


class TestRebuildConcepts:
    def test_not_found_returns_404(self, client):
        r = client.post("/api/concepts/rebuild/nonexistent")
        assert r.status_code == 404

    def test_video_without_transcript_returns_zero(self, client, sample_video):
        r = client.post(f"/api/concepts/rebuild/{sample_video.id}")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_response_structure(self, client, sample_video):
        r = client.post(f"/api/concepts/rebuild/{sample_video.id}")
        data = r.json()
        assert "message" in data
        assert "count" in data
        assert "video_id" in data


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/concepts/rebuild-all — 全部重建
# ═══════════════════════════════════════════════════════════════════════════════


class TestRebuildAllConcepts:
    def test_returns_structure(self, client):
        r = client.post("/api/concepts/rebuild-all")
        assert r.status_code == 200
        data = r.json()
        for key in ["message", "processed", "total_concepts", "errors"]:
            assert key in data

    def test_processed_count_non_negative(self, client):
        r = client.post("/api/concepts/rebuild-all")
        assert r.json()["processed"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# rebuild_concepts_for_video() 單元測試（不呼叫 LLM）
# ═══════════════════════════════════════════════════════════════════════════════


class TestRebuildConceptsForVideo:
    def test_nonexistent_video_returns_zero(self, db_session):
        from app.routers.concepts import rebuild_concepts_for_video

        result = rebuild_concepts_for_video("nonexistent", db_session)
        assert result == 0

    def test_video_without_transcript_returns_zero(self, db_session, sample_video):
        from app.routers.concepts import rebuild_concepts_for_video

        result = rebuild_concepts_for_video(sample_video.id, db_session)
        assert result == 0

    def test_creates_concepts_from_mocked_extractor(self, db_session, monkeypatch):
        from app.routers.concepts import rebuild_concepts_for_video

        vid_id = uuid.uuid4().hex
        db_session.add(
            Video(
                id=vid_id,
                filename="c.mp4",
                original_filename="c.mp4",
                file_size=100,
                status="completed",
            )
        )
        db_session.add(
            Transcript(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                content="逐字稿內容：行星逆行會帶來挑戰",
                segments=json.dumps(
                    [{"start": 0.0, "end": 5.0, "text": "行星逆行會帶來挑戰"}],
                    ensure_ascii=False,
                ),
            )
        )
        db_session.commit()

        mock_concepts = [
            {
                "name": "行星逆行",
                "description": "行星視運動逆行的天文現象",
                "relations": [],
                "segments": [{"seg_idx": 0, "start_sec": 0.0, "end_sec": 5.0}],
            }
        ]

        from unittest.mock import patch

        with patch("app.services.analyzer.extract_concepts", return_value=mock_concepts):
            count = rebuild_concepts_for_video(vid_id, db_session)

        assert count == 1
        concept = db_session.query(Concept).filter(Concept.name == "行星逆行").first()
        assert concept is not None
        sc = db_session.query(SegmentConcept).filter(SegmentConcept.video_id == vid_id).all()
        assert len(sc) == 1

    def test_idempotent_rebuild(self, db_session, monkeypatch):
        """重複呼叫不應產生重複的 segment_concept 記錄"""
        vid_id = uuid.uuid4().hex
        db_session.add(
            Video(
                id=vid_id,
                filename="idem.mp4",
                original_filename="idem.mp4",
                file_size=100,
                status="completed",
            )
        )
        db_session.add(
            Transcript(
                id=uuid.uuid4().hex,
                video_id=vid_id,
                content="風水基礎知識",
                segments=json.dumps(
                    [{"start": 0.0, "end": 4.0, "text": "風水基礎"}],
                    ensure_ascii=False,
                ),
            )
        )
        db_session.commit()

        mock_concepts = [
            {
                "name": "風水基礎",
                "description": "風水的基本概念",
                "relations": [],
                "segments": [{"seg_idx": 0, "start_sec": 0.0, "end_sec": 4.0}],
            }
        ]
        from unittest.mock import patch

        with patch("app.services.analyzer.extract_concepts", return_value=mock_concepts):
            from app.routers.concepts import rebuild_concepts_for_video

            rebuild_concepts_for_video(vid_id, db_session)
            rebuild_concepts_for_video(vid_id, db_session)

        sc_count = (
            db_session.query(SegmentConcept).filter(SegmentConcept.video_id == vid_id).count()
        )
        assert sc_count == 1  # 冪等：不重複

    def test_concept_reused_across_videos(self, db_session, monkeypatch):
        """同名概念跨影片應複用同一個 concepts 記錄"""
        mock_concepts = [
            {
                "name": "紫微斗數",
                "description": "東方命理學體系",
                "relations": [],
                "segments": [{"seg_idx": 0, "start_sec": 0.0, "end_sec": 3.0}],
            }
        ]

        for i in range(2):
            vid_id = uuid.uuid4().hex
            db_session.add(
                Video(
                    id=vid_id,
                    filename=f"v{i}.mp4",
                    original_filename=f"v{i}.mp4",
                    file_size=100,
                    status="completed",
                )
            )
            db_session.add(
                Transcript(
                    id=uuid.uuid4().hex,
                    video_id=vid_id,
                    content="紫微斗數的解說",
                    segments=json.dumps(
                        [{"start": 0.0, "end": 3.0, "text": "紫微斗數"}],
                        ensure_ascii=False,
                    ),
                )
            )
            db_session.commit()

            from unittest.mock import patch

            with patch("app.services.analyzer.extract_concepts", return_value=mock_concepts):
                from app.routers.concepts import rebuild_concepts_for_video

                rebuild_concepts_for_video(vid_id, db_session)

        total_concepts = db_session.query(Concept).filter(Concept.name == "紫微斗數").count()
        assert total_concepts == 1  # 只有一個概念記錄
