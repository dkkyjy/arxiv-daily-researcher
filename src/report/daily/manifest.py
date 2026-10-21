"""写出供研究助手（research-assistant）消费的机器可读报告清单。

清单与 Markdown 报告同名、同批次落在 ``daily_research/manifest/<source>/``，
`schema 1.0` 是两端共享的契约：``report``、``papers``、``outputs.markdown``。
消费端会忽略未知字段，因此契约只允许向后兼容地增加字段，不重命名已有字段。
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


def _arxiv_id(meta: Any, paper: Dict[str, Any]) -> str:
    """Return the arXiv identifier (version stripped) when the paper has one."""
    candidate = str(getattr(meta, "arxiv_id", "") or "")
    if not candidate and str(getattr(meta, "source", "") or "") == "arxiv":
        candidate = str(
            getattr(meta, "canonical_id", None) or getattr(meta, "paper_id", "") or ""
        )
    if not candidate:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", str(paper.get("url") or ""))
        candidate = match.group(1) if match else ""
    return re.sub(r"v\d+$", "", candidate)


def _published_date(meta: Any, paper: Dict[str, Any]) -> str:
    published = getattr(meta, "published_date", None)
    if isinstance(published, datetime):
        return published.strftime("%Y-%m-%d")
    value = str(paper.get("published") or "")
    return "" if value == "N/A" else value


def _archived_pdf(meta: Any, paper_id: str) -> Optional[str]:
    """Path of the locally archived PDF, when this run/gallery stored one."""
    ref_dir = Path(settings.REF_PDF_DIR)
    for key in (paper_id, getattr(meta, "canonical_id", None)):
        if not key:
            continue
        try:
            candidate = ref_dir / f"{key}.pdf"
        except (OSError, ValueError):
            continue
        if candidate.is_file():
            return str(candidate)
    return None


def _paper_record(paper: Dict[str, Any]) -> Dict[str, Any]:
    meta = paper.get("paper_metadata")
    score = paper.get("score_response")
    paper_id = str(paper.get("paper_id") or getattr(meta, "paper_id", "") or "")

    keyword_scores: Dict[str, Any] = dict(getattr(score, "keyword_scores", None) or {})
    keyword_scores.update(getattr(score, "core_keyword_scores", None) or {})
    matched = [
        key
        for key, value in keyword_scores.items()
        if isinstance(value, (int, float)) and value > 0
    ]

    authors = list(getattr(meta, "authors", None) or [])
    if not authors:
        authors = [a for a in str(paper.get("authors") or "").split(",") if a.strip()]
        authors = [a.strip() for a in authors]

    score_value = getattr(score, "ranking_score", None)
    if score_value is None:
        score_value = getattr(score, "total_score", None)

    return {
        "arxiv_id": _arxiv_id(meta, paper),
        "title": str(paper.get("title") or getattr(meta, "title", "") or ""),
        "abstract": str(paper.get("abstract") or getattr(meta, "abstract", "") or ""),
        "abstract_cn": str(paper.get("abstract_cn") or ""),
        "authors": authors,
        "published_date": _published_date(meta, paper),
        "url": str(paper.get("url") or getattr(meta, "url", "") or ""),
        "doi": str(getattr(meta, "doi", "") or ""),
        "keywords": list(getattr(score, "extracted_keywords", None) or []),
        "score": score_value,
        "matched_keywords": matched,
        "qualified": bool(getattr(score, "is_qualified", False)),
        "tldr": str(getattr(score, "tldr", "") or ""),
        "pdf": _archived_pdf(meta, paper_id),
    }


def _relative_to_project(path: Optional[Path]) -> Optional[str]:
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        # 报告目录被配置到项目之外时给出绝对路径：消费端按绝对路径也能定位。
        return str(Path(path).resolve())


def build_manifest(
    *,
    source: str,
    papers: List[Dict[str, Any]],
    generated_at: datetime,
    report_kind: str = "daily",
    markdown_path: Optional[Path] = None,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "report": {
            "date": generated_at.strftime("%Y-%m-%d"),
            "generated_at": generated_at.isoformat(timespec="seconds"),
            "source": source,
            "kind": report_kind,
        },
        "outputs": {"markdown": _relative_to_project(markdown_path)},
        "papers": [_paper_record(paper) for paper in papers],
    }


def write_report_manifest(
    filepath: Path,
    *,
    source: str,
    papers: List[Dict[str, Any]],
    generated_at: datetime,
    report_kind: str = "daily",
    markdown_path: Optional[Path] = None,
) -> Path:
    """Write the manifest atomically; callers treat failures as best effort."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    payload = build_manifest(
        source=source,
        papers=papers,
        generated_at=generated_at,
        report_kind=report_kind,
        markdown_path=markdown_path,
    )
    descriptor, temp_path = tempfile.mkstemp(
        dir=str(filepath.parent), prefix=f".{filepath.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(temp_path, filepath)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return filepath
