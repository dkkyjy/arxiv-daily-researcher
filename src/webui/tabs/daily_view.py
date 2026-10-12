"""Daily Report viewer tab.

Read-only browser for ``data/reports/daily_research/``: pick a source + report,
see an at-a-glance overview, and read the full report with the Animal Crossing
theme applied by the shared preview component.
"""

from __future__ import annotations

import datetime

import streamlit as st

from webui.components.preview import render_preview
from webui.i18n import t
from webui.reader.daily_reports import (
    DailyReport,
    available_sources,
    list_daily_reports,
    load_html,
)

_SOURCE_KEY = "daily_source"
_REPORT_KEY = "daily_report"
_HEIGHT_KEY = "daily_height"


@st.cache_data(ttl=30, show_spinner=False)
def _cached_reports() -> list[DailyReport]:
    return list_daily_reports()


def _label(report: DailyReport) -> str:
    return f"{report.source} · {report.label}"


def _render_overview(report: DailyReport) -> None:
    """At-a-glance metric cards parsed from the report's Markdown."""
    cols = st.columns(5)
    cols[0].metric(t("daily_fetched"), report.fetched if report.fetched is not None else "—")
    cols[1].metric(t("daily_passed"), report.passed if report.passed is not None else "—")
    cols[2].metric(
        t("daily_deep"),
        report.deep_analyzed if report.deep_analyzed is not None else "—",
    )
    cols[3].metric(
        t("daily_pass_rate"),
        f"{report.pass_rate:.1f}%" if report.pass_rate is not None else "—",
    )
    cols[4].metric(
        t("daily_tokens"),
        f"{report.tokens['total']:,}" if report.tokens else "—",
    )

    bits = [
        f"**{report.source}**",
        t("daily_generated") + f": {report.generated_at or report.timestamp}",
    ]
    if report.passing_score is not None:
        bits.append(t("daily_passing") + f": {report.passing_score:.1f}")
    if report.keywords:
        names = ", ".join(k["name"] for k in report.keywords)
        bits.append(t("daily_keywords") + f" ({len(report.keywords)}): {names}")
    st.caption(" · ".join(bits))


def render(_env_values: dict, _config_values: dict) -> None:
    """Render the Daily Report viewer tab."""
    st.markdown(f'<p class="section-title">{t("daily_title")}</p>', unsafe_allow_html=True)
    st.markdown(f'<p class="hint-text">{t("daily_hint")}</p>', unsafe_allow_html=True)

    c_refresh, _ = st.columns([1, 5])
    with c_refresh:
        if st.button(t("daily_refresh"), use_container_width=True, key="daily_refresh_btn"):
            _cached_reports.clear()
            st.cache_data.clear()
            for k in (_SOURCE_KEY, _REPORT_KEY, _HEIGHT_KEY):
                st.session_state.pop(k, None)
            st.rerun()

    st.divider()

    reports = _cached_reports()
    if not reports:
        st.info(t("daily_empty"))
        return

    sources = available_sources(reports)

    sel = st.columns([1, 2])
    with sel[0]:
        source = st.selectbox(
            t("daily_source"),
            [t("daily_all_sources"), *sources],
            key=_SOURCE_KEY,
        )
    filtered = (
        reports
        if source == t("daily_all_sources")
        else [r for r in reports if r.source == source]
    )

    labels = [_label(r) for r in filtered]
    by_label = dict(zip(labels, filtered))

    with sel[1]:
        if st.session_state.get(_REPORT_KEY) not in labels:
            st.session_state[_REPORT_KEY] = labels[0]
        chosen = st.selectbox(t("daily_report"), labels, key=_REPORT_KEY)

    report = by_label.get(chosen)
    if report is None:
        st.info(t("daily_empty"))
        return

    st.divider()
    _render_overview(report)

    html = load_html(report)
    if html is None:
        st.warning(t("daily_no_html"))
        return

    path = report.html_path
    size_kb = path.stat().st_size / 1024 if path else 0
    mtime = (
        datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        if path
        else "—"
    )

    st.markdown("")
    render_preview(
        html=html,
        caption=(
            f"`{path.name if path else report.stem}` · {size_kb:.1f} KB · "
            f"{t('reports_mtime')}: {mtime}"
        ),
        file_name=path.name if path else f"{report.stem}.html",
        height_key=_HEIGHT_KEY,
        theme=True,
        download=True,
    )
