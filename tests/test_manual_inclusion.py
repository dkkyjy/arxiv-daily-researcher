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
    MANUAL_EXCLUSION_REASON,
    MANUAL_INCLUSION_REASON,
    REINCLUSION_REASON,
    force_manual_exclusion,
    force_manual_inclusion,
    override_keys,
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

            self.assertTrue(store.set_paper_override(override_keys(source="arxiv", paper_id=paper.paper_id), "include", source="arxiv", paper_id=paper.paper_id))

            self.assertEqual(store.paper_override(override_keys(source="arxiv", paper_id=paper.paper_id)), "include")
            record = store.get_paper_record("arxiv", paper.paper_id)
            payload = json.loads(record["score_json"])
            self.assertTrue(payload["is_qualified"])
            # The paper was already delivered, so the report says "re-included"
            # instead of the plain "included" reason.
            self.assertEqual(payload["qualification_reason"], REINCLUSION_REASON)
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
            store.set_paper_override(override_keys(source="arxiv", paper_id=paper.paper_id), "include", source="arxiv", paper_id=paper.paper_id)

            self.assertIsNone(
                store.set_paper_override(
                    override_keys(source="arxiv", paper_id=paper.paper_id),
                    None,
                    source="arxiv",
                    paper_id=paper.paper_id,
                )
            )

            self.assertIsNone(store.paper_override(override_keys(source="arxiv", paper_id=paper.paper_id)))
            payload = json.loads(store.get_paper_record("arxiv", paper.paper_id)["score_json"])
            self.assertTrue(payload["is_qualified"])

    def test_report_rows_learn_which_papers_are_marked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            marked = _paper("2301.11111")
            plain = _paper("2301.22222")
            self._seed_delivered_paper(store, marked)
            store.set_paper_override(override_keys(source="arxiv", paper_id=marked.paper_id), "include", source="arxiv", paper_id=marked.paper_id)

            rows = [{"source": "arxiv", "paper_id": marked.paper_id},
                    {"source": "arxiv", "paper_id": plain.paper_id}]
            verdicts = store.override_map()
            self.assertEqual(
                store.resolve_override(
                    verdicts, override_keys(source="arxiv", paper_id=marked.paper_id)
                ),
                "include",
            )
            self.assertIsNone(
                store.resolve_override(
                    verdicts, override_keys(source="arxiv", paper_id=plain.paper_id)
                )
            )

    def test_marking_requires_an_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with self.assertRaises(ValueError):
                store.set_paper_override(override_keys(source="", paper_id="2301.12345"), "include", source="", paper_id="2301.12345")


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

                store.set_paper_override(override_keys(source="arxiv", paper_id="2301.12345"), "include", source="arxiv", paper_id="2301.12345")
                after = backend.report_papers("token")
                marked = {row["paper_id"] for row in after if row["manual_include"]}
                self.assertEqual(marked, {"2301.12345"})


class OverrideIdentityTests(unittest.TestCase):
    def test_verdict_follows_new_versions_and_mirrors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            v2 = _paper("2301.12345v2")
            store.upsert_paper_seen(store.start_run(0), "arxiv", v2, {})
            store.set_paper_override(
                override_keys(source="arxiv", paper_id=v2.paper_id),
                "exclude",
                source="arxiv",
                paper_id=v2.paper_id,
            )

            # A later version has a different paper_id but the same identity.
            self.assertEqual(
                store.paper_override(
                    override_keys(
                        source="arxiv",
                        paper_id="2301.12345v3",
                        canonical_id="2301.12345",
                    )
                ),
                "exclude",
            )
            # A journal mirror reaches the verdict through its arXiv alias only.
            self.assertIsNone(
                store.paper_override(
                    override_keys(source="prl", paper_id="10.1103/PhysRevLett.1")
                )
            )
            self.assertEqual(
                store.paper_override(
                    override_keys(
                        source="prl",
                        paper_id="10.1103/PhysRevLett.1",
                        canonical_id="10.1103/PhysRevLett.1",
                        arxiv_id="2301.12345",
                    )
                ),
                "exclude",
            )

    def test_a_new_verdict_replaces_the_previous_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            paper = _paper("2301.12345")
            store.upsert_paper_seen(store.start_run(0), "arxiv", paper, {})
            keys = override_keys(source="arxiv", paper_id=paper.paper_id)

            store.set_paper_override(keys, "exclude", source="arxiv", paper_id=paper.paper_id)
            store.set_paper_override(keys, "include", source="arxiv", paper_id=paper.paper_id)
            self.assertEqual(store.paper_override(keys), "include")
            self.assertEqual(len(store.override_map()), 1)


class ManualExclusionTests(unittest.TestCase):
    def test_exclusion_demotes_the_stored_score_without_re_queueing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            paper = _paper("2301.77777")
            store.upsert_paper_seen(store.start_run(0), "arxiv", paper, {})
            store.update_score(
                "seed",
                "arxiv",
                {
                    "paper_metadata": paper,
                    "paper_id": paper.paper_id,
                    "score_response": _score(True),
                },
            )
            with store._connect() as conn:
                conn.execute(
                    "UPDATE daily_papers SET completed_at = '2026-10-23' "
                    "WHERE source = 'arxiv' AND paper_id = ?",
                    (paper.paper_id,),
                )

            self.assertEqual(
                store.set_paper_override(
                    override_keys(source="arxiv", paper_id=paper.paper_id),
                    "exclude",
                    source="arxiv",
                    paper_id=paper.paper_id,
                ),
                "exclude",
            )

            record = store.get_paper_record("arxiv", paper.paper_id)
            payload = json.loads(record["score_json"])
            self.assertFalse(payload["is_qualified"])
            self.assertEqual(payload["qualification_reason"], MANUAL_EXCLUSION_REASON)
            # Exclusion never re-queues: no re-analysis, no second delivery.
            self.assertEqual(record["completed_at"], "2026-10-23")

    def test_exclusion_survives_re_scoring(self):
        forced = force_manual_exclusion(_score(True))
        self.assertFalse(forced.is_qualified)
        self.assertEqual(forced.qualification_reason, MANUAL_EXCLUSION_REASON)
        already_out = _score(False)
        self.assertIs(force_manual_exclusion(already_out), already_out)

    def test_backend_records_the_exclusion_verdict(self):
        from unittest.mock import patch

        from modern_webui import backend

        with tempfile.TemporaryDirectory() as temp_dir:
            store = DailyResearchStore(Path(temp_dir) / "daily.db")
            store.start_run(0)
            with patch.object(backend, "open_store", return_value=store):
                saved = backend.set_paper_interest(
                    {"source": "arxiv", "paper_id": "2301.88888", "state": "excluded"}
                )
                self.assertEqual(saved["state"], "excluded")
                self.assertEqual(saved["preference"], "dislike")
                self.assertFalse(saved["manual_include"])
                self.assertTrue(saved["excluded"])
                self.assertEqual(store.paper_override(override_keys(source="arxiv", paper_id="2301.88888")), "exclude")
                self.assertEqual(
                    store.get_paper_preference("arxiv", "2301.88888")["preference"],
                    "dislike",
                )


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
                self.assertEqual(store.paper_override(override_keys(source="arxiv", paper_id="2301.12345")), "include")
                self.assertEqual(
                    store.get_paper_preference("arxiv", "2301.12345")["preference"],
                    "like",
                )

                saved = backend.set_paper_interest(
                    {"source": "arxiv", "paper_id": "2301.12345", "interested": False}
                )
                self.assertFalse(saved["manual_include"])
                self.assertEqual(saved["preference"], "none")
                self.assertIsNone(store.paper_override(override_keys(source="arxiv", paper_id="2301.12345")))

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
