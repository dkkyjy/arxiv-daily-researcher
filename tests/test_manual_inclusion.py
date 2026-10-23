import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.analysis_agent import WeightedScoreResponse  # noqa: E402
from sources.base_source import PaperMetadata  # noqa: E402
from utils.daily_research_store import DailyResearchStore  # noqa: E402
from utils.manual_inclusion import (  # noqa: E402
    MANUAL_INCLUSION_REASON,
    force_manual_inclusion,
)


def _paper(paper_id: str) -> PaperMetadata:
    return PaperMetadata(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        authors=["Author"],
        abstract="abstract",
        published_date=datetime.now(timezone.utc),
        url=f"https://arxiv.org/abs/{paper_id}",
        source="arxiv",
    )


def _score(is_qualified: bool) -> WeightedScoreResponse:
    return WeightedScoreResponse(
        total_score=3.0,
        keyword_scores={"blazar": 3.0},
        author_bonus=0,
        expert_authors_found=[],
        passing_score=6,
        is_qualified=is_qualified,
        reasoning="below threshold",
        tldr="中文 TL;DR",
        extracted_keywords=["blazar"],
    )


class ForceManualInclusionTests(unittest.TestCase):
    def test_unqualified_score_becomes_qualified_with_a_visible_reason(self):
        forced = force_manual_inclusion(_score(False))
        self.assertTrue(forced.is_qualified)
        self.assertEqual(forced.qualification_reason, MANUAL_INCLUSION_REASON)
        # The LLM numbers stay untouched so the report can still show them.
        self.assertEqual(forced.total_score, 3.0)
        self.assertEqual(forced.tldr, "中文 TL;DR")

    def test_already_qualified_score_is_left_alone(self):
        original = _score(True)
        self.assertIs(force_manual_inclusion(original), original)


class ManualInclusionStoreTests(unittest.TestCase):
    def _seed_delivered_paper(self, store: DailyResearchStore, paper: PaperMetadata):
        run_id = store.start_run(0)
        store.upsert_paper_seen(run_id, "arxiv", paper, {})
        store.update_score(
            run_id,
            "arxiv",
            {
                "paper_metadata": paper,
                "paper_id": paper.paper_id,
                "score_response": _score(False),
            },
        )
        with store._connect() as conn:
            conn.execute(
                "INSERT INTO paper_deliveries("
                "run_id, source, paper_id, canonical_id, version, "
                "report_path, report_at, delivered_at) "
                "VALUES (?, 'arxiv', ?, ?, ?, 'r.md', '2026-10-20', '2026-10-20')",
                (
                    run_id,
                    paper.paper_id,
                    paper.canonical_id or paper.paper_id,
                    paper.version or 0,
                ),
            )
            conn.execute(
                "UPDATE daily_papers SET completed_at = '2026-10-20' "
                "WHERE source = 'arxiv' AND paper_id = ?",
                (paper.paper_id,),
            )

    def test_marking_promotes_the_score_and_queues_the_paper_again(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            paper = _paper("2301.12345v2")
            self._seed_delivered_paper(store, paper)
            self.assertTrue(store.is_paper_delivered("arxiv", paper.paper_id))

            self.assertTrue(store.set_manual_inclusion("arxiv", paper.paper_id, True))

            self.assertTrue(store.is_manually_included("arxiv", paper.paper_id))
            record = store.get_paper_record("arxiv", paper.paper_id)
            payload = json.loads(record["score_json"])
            self.assertTrue(payload["is_qualified"])
            self.assertEqual(payload["qualification_reason"], MANUAL_INCLUSION_REASON)
            self.assertIsNone(record["completed_at"])
            self.assertEqual(record["analysis_status"], "pending")

            # The retired delivery row is what lets the next run deliver it.
            self.assertFalse(store.is_paper_delivered("arxiv", paper.paper_id))
            pending, total = store.select_pending_papers(["arxiv"], 0)
            self.assertEqual(total, 1)
            self.assertEqual([p.paper_id for p in pending["arxiv"]], [paper.paper_id])

    def test_unmarking_removes_only_the_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            paper = _paper("2301.12345")
            self._seed_delivered_paper(store, paper)
            store.set_manual_inclusion("arxiv", paper.paper_id, True)

            self.assertFalse(store.set_manual_inclusion("arxiv", paper.paper_id, False))

            self.assertFalse(store.is_manually_included("arxiv", paper.paper_id))
            payload = json.loads(store.get_paper_record("arxiv", paper.paper_id)["score_json"])
            self.assertTrue(payload["is_qualified"])

    def test_marking_requires_an_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with self.assertRaises(ValueError):
                store.set_manual_inclusion("", "2301.12345", True)


class ManualInclusionBackendTests(unittest.TestCase):
    def test_backend_toggles_the_flag_for_one_paper(self):
        from unittest.mock import patch

        from modern_webui import backend

        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with patch.object(backend, "open_store", return_value=store):
                saved = backend.set_manual_inclusion(
                    {"source": "arxiv", "paper_id": "2301.12345", "included": True}
                )
                self.assertTrue(saved["manual_include"])
                self.assertTrue(store.is_manually_included("arxiv", "2301.12345"))

                saved = backend.set_manual_inclusion(
                    {"source": "arxiv", "paper_id": "2301.12345", "included": False}
                )
                self.assertFalse(saved["manual_include"])
                self.assertFalse(store.is_manually_included("arxiv", "2301.12345"))

    def test_backend_rejects_an_empty_identity(self):
        from unittest.mock import patch

        from modern_webui import backend

        with patch.object(backend, "open_store", return_value=object()):
            with self.assertRaises(backend.ModernWebUIError):
                backend.set_manual_inclusion({"source": "", "paper_id": ""})


if __name__ == "__main__":
    unittest.main()
