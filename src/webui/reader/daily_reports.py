"""Read-only access layer for Daily Research reports.

Scans ``data/reports/daily_research/`` and exposes:

* :func:`list_daily_reports` — discovery + lightweight overview (parsed from the
  sibling Markdown file), newest first.
* :func:`load_html` — read a report's self-contained HTML for embedding.

Nothing here writes to disk or depends on Streamlit, so it can be unit-tested
directly.  The heavy per-paper parsing is intentionally *not* done here; the
overview only extracts the report-level stats needed by the viewer header.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# src/webui/reader/daily_reports.py -> parents[3] == project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_REPORTS_DIR = _PROJECT_ROOT / "data" / "reports" / "daily_research"
_HTML_DIR = _REPORTS_DIR / "html"
_MD_DIR = _REPORTS_DIR / "markdown"

_FNAME_RE = re.compile(r"^(?P<source>[A-Za-z0-9]+)_Report_(?P<ts>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})$")


@dataclass
class DailyReport:
    """One daily report (HTML + Markdown pair) with parsed overview."""

    source: str  # directory / file prefix, e.g. "ARXIV"
    timestamp: str  # "2026-10-09 11:09:25" (from filename)
    date: str  # "2026-10-09"
    stem: str  # "ARXIV_Report_2026-10-09_11-09-25"
    html_path: Path | None = None
    md_path: Path | None = None

    # parsed overview (from Markdown, when available)
    generated_at: str | None = None
    keywords: list[dict] = field(default_factory=list)
    passing_score: float | None = None
    fetched: int | None = None
    passed: int | None = None
    deep_analyzed: int | None = None
    pass_rate: float | None = None
    tokens: dict | None = None

    @property
    def label(self) -> str:
        """Human-friendly label, e.g. ``2026-10-09  11:09:25``."""
        if self.timestamp:
            d, t = self.timestamp.split(" ")
            return f"{d}  {t}"
        return self.stem

    @property
    def mtime(self) -> float:
        for p in (self.html_path, self.md_path):
            if p and p.exists():
                return p.stat().st_mtime
        return 0.0


# ─── Markdown overview parsing ────────────────────────────────────────────────


def _parse_markdown(text: str, report: DailyReport) -> None:
    """Fill ``report`` overview fields by parsing its Markdown source."""
    m = re.search(r">\s*生成时间:\s*(.+)", text)
    if m:
        report.generated_at = m.group(1).strip()

    # keywords table: 关键词 | 权重 | 类型
    km = re.search(r"### 关键词列表[^\n]*\n\n(.*?)\n\n", text, re.S)
    if km:
        for line in km.group(1).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3 and cells[0] and cells[0] != "关键词":
                if set(cells[0]) <= set("-: "):  # separator row
                    continue
                try:
                    weight = float(cells[1])
                except ValueError:
                    weight = None
                report.keywords.append(
                    {"name": cells[0], "weight": weight, "type": cells[2]}
                )

    m = re.search(r"\*\*当前及格分\*\*:\s*([\d.]+)", text)
    if m:
        report.passing_score = float(m.group(1))

    m = re.search(r"\*\*总抓取\*\*:\s*(\d+)", text)
    if m:
        report.fetched = int(m.group(1))

    m = re.search(r"\*\*及格论文\*\*:\s*(\d+)\s*篇\s*\(([\d.]+)%\)", text)
    if m:
        report.passed = int(m.group(1))
        report.pass_rate = float(m.group(2))
    else:
        m = re.search(r"\*\*及格论文\*\*:\s*(\d+)", text)
        if m:
            report.passed = int(m.group(1))

    m = re.search(r"\*\*深度分析\*\*:\s*(\d+)", text)
    if m:
        report.deep_analyzed = int(m.group(1))

    m = re.search(
        r"\*\*总计\*\*:\s*([\d,]+)\s*tokens（输入\s*([\d,]+)\s*/\s*输出\s*([\d,]+)",
        text,
    )
    if m:
        report.tokens = {
            "total": int(m.group(1).replace(",", "")),
            "prompt": int(m.group(2).replace(",", "")),
            "completion": int(m.group(3).replace(",", "")),
        }


# ─── discovery ────────────────────────────────────────────────────────────────


def _match_stem(stem: str) -> tuple[str, str, str] | None:
    m = _FNAME_RE.match(stem)
    if not m:
        return None
    source = m.group("source").upper()
    ts = m.group("ts")
    date = ts.split("_")[0]
    return source, ts, date


def _iter_files(base: Path, suffix: str) -> dict[str, Path]:
    """Return ``{stem: path}`` for all report files under ``base/{source}/``."""
    out: dict[str, Path] = {}
    if not base.exists():
        return out
    for src_dir in base.iterdir():
        if not src_dir.is_dir():
            continue
        for f in src_dir.glob(f"*{suffix}"):
            out[f.stem] = f
    return out


def list_daily_reports() -> list[DailyReport]:
    """Discover every daily report, newest first (by file mtime)."""
    html_files = _iter_files(_HTML_DIR, ".html")
    md_files = _iter_files(_MD_DIR, ".md")

    reports: list[DailyReport] = []
    for stem in sorted(set(html_files) | set(md_files)):
        matched = _match_stem(stem)
        if not matched:
            continue
        source, ts, date = matched
        d, t = ts.split("_")
        report = DailyReport(
            source=source,
            timestamp=f"{d} {t.replace('-', ':')}",
            date=date,
            stem=stem,
            html_path=html_files.get(stem),
            md_path=md_files.get(stem),
        )

        if report.md_path and report.md_path.exists():
            try:
                _parse_markdown(
                    report.md_path.read_text(encoding="utf-8", errors="replace"), report
                )
            except Exception:
                pass

        reports.append(report)

    reports.sort(key=lambda r: r.mtime, reverse=True)
    return reports


def available_sources(reports: list[DailyReport] | None = None) -> list[str]:
    """Sorted list of distinct sources."""
    reports = reports if reports is not None else list_daily_reports()
    return sorted({r.source for r in reports})


def load_html(report: DailyReport) -> str | None:
    """Read the report's HTML, or ``None`` if unavailable."""
    if report.html_path and report.html_path.exists():
        return report.html_path.read_text(encoding="utf-8", errors="replace")
    return None
