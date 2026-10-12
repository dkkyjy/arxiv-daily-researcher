"""Generic discovery of generated report files under ``data/reports/``.

Shared by the "报告查看" and "日报浏览" tabs.  Pure filesystem + stdlib: no
Streamlit, no i18n, so it is easy to test and reuse.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple

# src/webui/reader/report_files.py -> parents[3] == project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REPORTS_DIR = _PROJECT_ROOT / "data" / "reports"


class ReportFile(NamedTuple):
    path: Path
    display: str  # human-friendly label shown in UI
    source: str  # uppercase source name / keyword slug / "keyword_trend"
    report_type: str  # "daily" | "trend" | "keyword_trend"


# ─── label formatting ─────────────────────────────────────────────────────────


def _fmt_daily(stem: str) -> str:
    """ARXIV_Report_2026-03-10_12-27-47  →  2026-03-10  12:27:47"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})$", stem)
    if m:
        return f"{m.group(1)}  {m.group(2).replace('-', ':')}"
    return stem


def _fmt_trend(stem: str) -> str:
    """2025-03-10_2026-03-10  →  2025-03-10 → 2026-03-10"""
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", stem)
    if m:
        return f"{m.group(1)} → {m.group(2)}"
    return stem


def _fmt_kw(stem: str) -> str:
    """keyword_trends_2026-03-09  →  2026-03-09"""
    m = re.search(r"(\d{4}-\d{2}-\d{2})$", stem)
    return m.group(1) if m else stem


# ─── discovery ────────────────────────────────────────────────────────────────


def discover_reports(reports_dir: Path | None = None) -> dict[str, list[ReportFile]]:
    """Scan ``data/reports/`` and return three lists, each newest-first."""
    base = reports_dir or _REPORTS_DIR
    result: dict[str, list[ReportFile]] = {
        "daily": [],
        "trend": [],
        "keyword_trend": [],
    }

    # daily_research/html/{source}/*.html
    daily_html = base / "daily_research" / "html"
    if daily_html.exists():
        for src_dir in daily_html.iterdir():
            if src_dir.is_dir():
                src = src_dir.name.upper()
                for f in src_dir.glob("*.html"):
                    result["daily"].append(ReportFile(f, _fmt_daily(f.stem), src, "daily"))
        result["daily"].sort(key=lambda r: r.path.stat().st_mtime, reverse=True)

    # trend_research/html/{keyword-slug}/*.html
    trend_html = base / "trend_research" / "html"
    if trend_html.exists():
        for kw_dir in trend_html.iterdir():
            if kw_dir.is_dir():
                slug = kw_dir.name
                for f in kw_dir.glob("*.html"):
                    result["trend"].append(ReportFile(f, _fmt_trend(f.stem), slug, "trend"))
        result["trend"].sort(key=lambda r: r.path.stat().st_mtime, reverse=True)

    # keyword_trend/html/*.html
    kw_html = base / "keyword_trend" / "html"
    if kw_html.exists():
        for f in sorted(kw_html.glob("*.html"), reverse=True):
            result["keyword_trend"].append(
                ReportFile(f, _fmt_kw(f.stem), "keyword_trend", "keyword_trend")
            )

    return result


def reports_root() -> Path:
    """Absolute path of the reports directory (for UI display)."""
    return _REPORTS_DIR


def load_trend_metadata(html_path: Path) -> dict | None:
    """Read the sibling ``*_metadata.json`` for a trend report, if present."""
    md_dir = html_path.parent.parent.parent / "markdown" / html_path.parent.name
    meta_path = md_dir / f"{html_path.stem}_metadata.json"
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None
