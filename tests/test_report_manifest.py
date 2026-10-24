import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agents.analysis_agent import WeightedScoreResponse  # noqa: E402
from config import settings  # noqa: E402
from report.daily.manifest import build_manifest, write_report_manifest  # noqa: E402
from sources.base_source import PaperMetadata  # noqa: E402


def _scored_paper(paper_id: str, matched: float, qualified: bool) -> dict:
    paper = PaperMetadata(
        paper_id=paper_id,
        title=f"Title {paper_id}",
        authors=["Alice", "Bob"],
        abstract="Abstract EN",
        published_date=datetime(2026, 10, 20, tzinfo=timezone.utc),
        url=f"https://arxiv.org/abs/{paper_id}",
        doi="10.1103/PhysRevLett.1",
        source="arxiv",
    )
    score_response = WeightedScoreResponse(
        total_score=matched,
        keyword_scores={"blazar": matched, "unrelated": 0},
        author_bonus=0,
        expert_authors_found=[],
        passing_score=5,
        is_qualified=qualified,
        reasoning="test",
        tldr="中文 TL;DR",
        extracted_keywords=["blazar"],
    )
    return {
        "paper_metadata": paper,
        "paper_id": paper_id,
        "title": paper.title,
        "authors": paper.get_authors_string(),
        "abstract": paper.abstract,
        "abstract_cn": "中文摘要",
        "url": paper.url,
        "published": "2026-10-20",
        "score_response": score_response,
    }


class ReportManifestTests(unittest.TestCase):
    def test_manifest_maps_scored_papers_to_the_consumer_contract(self):
        generated_at = datetime(2026, 10, 20, 14, 45, 31)
        manifest = build_manifest(
            source="arxiv",
            papers=[_scored_paper("2301.12345v2", 7.5, True)],
            generated_at=generated_at,
            markdown_path=settings.PROJECT_ROOT
            / "data/reports/daily_research/markdown/arxiv/ARXIV_Report_2026-10-20.md",
        )

        self.assertEqual(manifest["schema"], "1.1")
        self.assertEqual(manifest["report"]["date"], "2026-10-20")
        self.assertEqual(manifest["report"]["source"], "arxiv")
        self.assertEqual(
            manifest["outputs"]["markdown"],
            "data/reports/daily_research/markdown/arxiv/ARXIV_Report_2026-10-20.md",
        )

        paper = manifest["papers"][0]
        self.assertEqual(paper["arxiv_id"], "2301.12345")
        self.assertEqual(paper["authors"], ["Alice", "Bob"])
        self.assertEqual(paper["published_date"], "2026-10-20")
        self.assertEqual(paper["abstract_cn"], "中文摘要")
        self.assertEqual(paper["keywords"], ["blazar"])
        self.assertEqual(paper["matched_keywords"], ["blazar"])
        self.assertEqual(paper["score"], 7.5)
        self.assertTrue(paper["qualified"])
        self.assertEqual(paper["tldr"], "中文 TL;DR")
        self.assertEqual(paper["doi"], "10.1103/PhysRevLett.1")
        self.assertIsNone(paper["pdf"])
        self.assertIsNone(paper["verdict"])

    def test_manifest_points_at_archived_pdf_when_one_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archived = Path(temp_dir) / "2301.12345v2.pdf"
            archived.write_bytes(b"%PDF-1.4")
            with patch.object(settings, "REF_PDF_DIR", Path(temp_dir)):
                manifest = build_manifest(
                    source="arxiv",
                    papers=[_scored_paper("2301.12345v2", 7.5, True)],
                    generated_at=datetime(2026, 10, 20),
                )
        self.assertEqual(manifest["papers"][0]["pdf"], str(archived))

    def test_write_report_manifest_is_atomic_and_loadable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "manifest" / "arxiv" / "ARXIV_Report_2026-10-20.json"
            write_report_manifest(
                target,
                source="arxiv",
                papers=[_scored_paper("2301.12345", 3.0, False)],
                generated_at=datetime(2026, 10, 20, 9, 0, 0),
            )
            payload = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(payload["papers"][0]["score"], 3.0)
            self.assertFalse(payload["papers"][0]["qualified"])
            self.assertEqual(list(target.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
