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

    def test_report_rows_learn_which_papers_are_marked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            marked = _paper("2301.11111")
            plain = _paper("2301.22222")
            self._seed_delivered_paper(store, marked)
            store.set_manual_inclusion("arxiv", marked.paper_id, True)

            rows = [{"source": "arxiv", "paper_id": marked.paper_id},
                    {"source": "arxiv", "paper_id": plain.paper_id}]
            self.assertEqual(
                store.manual_inclusion_keys(rows),
                {("arxiv", marked.paper_id)},
            )
            self.assertEqual(store.manual_inclusion_keys([]), set())

    def test_marking_requires_an_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with self.assertRaises(ValueError):
                store.set_manual_inclusion("", "2301.12345", True)


class ReportPreviewInclusionTests(unittest.TestCase):
    """The report preview decorates cards from ``/api/reports/<id>/papers``."""

    def test_report_papers_carry_the_manual_include_flag(self):
        from unittest.mock import patch

        from modern_webui import backend

        rows = [
            {"source": "arxiv", "paper_id": "2301.12345", "title": "A", "authors": []},
            {"source": "arxiv", "paper_id": "2301.99999", "title": "B", "authors": []},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with patch.object(backend, "_report_paper_rows", return_value=[dict(r) for r in rows]), patch.object(
                backend, "open_store", return_value=store
            ), patch.object(
                backend, "report_file", return_value=(Path(temp_dir) / "r.html", "text/html")
            ), patch.object(
                backend, "_report_source", return_value="arxiv"
            ):
                before = backend.report_papers("token")
                self.assertEqual([row["manual_include"] for row in before], [False, False])

                store.set_manual_inclusion("arxiv", "2301.12345", True)
                after = backend.report_papers("token")
                marked = {row["paper_id"] for row in after if row["manual_include"]}
                self.assertEqual(marked, {"2301.12345"})


class PaperInterestBackendTests(unittest.TestCase):
    def test_backend_writes_both_marks_and_clears_them_together(self):
        from unittest.mock import patch

        from modern_webui import backend

        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with patch.object(backend, "open_store", return_value=store):
                saved = backend.set_paper_interest(
                    {
                        "source": "arxiv",
                        "paper_id": "2301.12345",
                        "title": "A blazar paper",
                        "interested": True,
                    }
                )
                self.assertTrue(saved["manual_include"])
                self.assertEqual(saved["preference"], "like")
                self.assertTrue(store.is_manually_included("arxiv", "2301.12345"))
                self.assertEqual(
                    store.get_paper_preference("arxiv", "2301.12345")["preference"],
                    "like",
                )

                saved = backend.set_paper_interest(
                    {"source": "arxiv", "paper_id": "2301.12345", "interested": False}
                )
                self.assertFalse(saved["manual_include"])
                self.assertEqual(saved["preference"], "none")
                self.assertFalse(store.is_manually_included("arxiv", "2301.12345"))

    def test_backend_falls_back_to_stored_metadata_for_the_title(self):
        from unittest.mock import patch

        from modern_webui import backend

        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            paper = _paper("2301.55555")
            store.upsert_paper_seen(store.start_run(0), "arxiv", paper, {})
            with patch.object(backend, "open_store", return_value=store):
                backend.set_paper_interest(
                    {"source": "arxiv", "paper_id": paper.paper_id, "interested": True}
                )
            row = store.get_paper_preference("arxiv", paper.paper_id)
            self.assertEqual(row["title"], f"Title {paper.paper_id}")

    def test_backend_rejects_an_empty_identity(self):
        from unittest.mock import patch

        from modern_webui import backend

        with patch.object(backend, "open_store", return_value=object()):
            with self.assertRaises(backend.ModernWebUIError):
                backend.set_paper_interest({"source": "", "paper_id": ""})


if __name__ == "__main__":
    unittest.main()
