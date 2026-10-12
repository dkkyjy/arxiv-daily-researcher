"""Reports Viewer tab for the Streamlit config panel.

Browses all generated reports (daily / trend / keyword trend) in a left-hand
file browser with a live, Animal-Crossing-themed preview on the right.
"""

from __future__ import annotations

import datetime

import streamlit as st

from webui.components.preview import render_preview
from webui.i18n import t
from webui.reader.report_files import (
    ReportFile,
    discover_reports,
    load_trend_metadata,
    reports_root,
)

_SEL_KEY = "rsel"  # prefix for all selectbox session-state keys
_PREVIEW_KEY = "preview_report"
_HEIGHT_KEY = "reports_preview_height"


# ─── file browser helpers ─────────────────────────────────────────────────────


def _sel_key(rtype: str, group: str) -> str:
    return f"{_SEL_KEY}_{rtype}_{group}"


def _make_on_change(key: str, by_display: dict[str, ReportFile]):
    """Return an on_change callback that updates the preview target."""

    def _cb():
        chosen = st.session_state.get(key)
        if chosen in by_display:
            st.session_state[_PREVIEW_KEY] = by_display[chosen]

    return _cb


def _render_group_selectbox(rtype: str, group: str, reports: list[ReportFile]) -> None:
    """Render one selectbox for a source/slug group; preview updates on change."""
    by_display = {r.display: r for r in reports}
    labels = [r.display for r in reports]
    key = _sel_key(rtype, group)

    # Auto-select a preview on first render so the right pane is never empty.
    if _PREVIEW_KEY not in st.session_state and reports:
        st.session_state[_PREVIEW_KEY] = reports[0]

    st.selectbox(
        f"**{group}** ({len(labels)})",
        labels,
        key=key,
        on_change=_make_on_change(key, by_display),
    )


def _render_category_col(rtype: str, reports: list[ReportFile], header: str) -> None:
    """Render one category column (daily / trend / keyword_trend)."""
    count = len(reports)
    st.markdown(
        f"**{header}**<br>"
        f"<span style='color:#888;font-size:0.82em'>{count} {t('reports_count_unit')}</span>",
        unsafe_allow_html=True,
    )

    if not reports:
        st.caption(t("reports_empty_type"))
        return

    if rtype == "keyword_trend":
        _render_group_selectbox(rtype, "keyword_trend", reports)
    else:
        # Group by source / keyword slug
        groups = sorted({r.source for r in reports})
        for grp in groups:
            grp_reports = [r for r in reports if r.source == grp]
            _render_group_selectbox(rtype, grp, grp_reports)


# ─── preview ──────────────────────────────────────────────────────────────────


def _render_preview(report: ReportFile) -> None:
    """Render the selected report using the shared preview component."""
    stat = report.path.stat()
    size_kb = stat.st_size / 1024
    mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    type_cn = {
        "daily": t("rtype_daily"),
        "trend": t("rtype_trend"),
        "keyword_trend": t("rtype_keyword_trend"),
    }.get(report.report_type, report.report_type)

    meta = load_trend_metadata(report.path) if report.report_type == "trend" else None

    try:
        html = report.path.read_text(encoding="utf-8")
    except Exception as e:
        st.error(f"{t('reports_load_error')}: {e}")
        return

    render_preview(
        html=html,
        caption=(
            f"**{type_cn}** · `{report.source}` · `{report.path.name}` · "
            f"{size_kb:.1f} KB · {t('reports_mtime')}: {mtime}"
        ),
        file_name=report.path.name,
        height_key=_HEIGHT_KEY,
        meta=meta,
        theme=True,
        download=True,
    )


# ─── main render ──────────────────────────────────────────────────────────────


def render(_env_values: dict, _config_values: dict) -> None:
    """Render the Reports Viewer tab."""

    st.markdown(
        f'<p class="section-title">{t("reports_title")}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="hint-text">{t("reports_hint")}</p>',
        unsafe_allow_html=True,
    )

    col_refresh, _ = st.columns([1, 5])
    with col_refresh:
        if st.button(t("reports_refresh"), use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith(_SEL_KEY) or k in (_PREVIEW_KEY, _HEIGHT_KEY):
                    del st.session_state[k]
            st.rerun()

    st.divider()

    all_reports = discover_reports()
    total = sum(len(v) for v in all_reports.values())

    if total == 0:
        st.info(t("reports_empty"))
        st.caption(f"📂 {t('reports_dir_label')}: `{reports_root()}`")
        return

    # ── File browser (left) + live preview (right) ────────────────────────
    browser, preview = st.columns([2, 3], gap="large")

    with browser:
        _render_category_col("daily", all_reports["daily"], f"📅 {t('rtype_daily')}")
        _render_category_col("trend", all_reports["trend"], f"🔬 {t('rtype_trend')}")
        _render_category_col(
            "keyword_trend", all_reports["keyword_trend"], f"📈 {t('rtype_keyword_trend')}"
        )

    # ── Preview (stays visible next to the browser) ────────────────────────
    with preview:
        report: ReportFile | None = st.session_state.get(_PREVIEW_KEY)
        if report is None:
            st.info(t("reports_empty_type"))
        else:
            st.markdown(
                f'<p class="section-title">{t("reports_preview_title")}</p>',
                unsafe_allow_html=True,
            )
            _render_preview(report)
