"""Shared HTML report preview component.

Used by both the "报告查看" and "日报浏览" tabs so the info bar, download,
height control and Animal-Crossing-themed iframe behave identically.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from webui.i18n import t
from webui.theme.ac_theme import inject_ac_theme

_HEIGHTS = [600, 800, 1000, 1200, 1500, 2000]


def render_preview(
    *,
    html: str,
    caption: str,
    file_name: str,
    height_key: str,
    meta: dict | None = None,
    theme: bool = True,
    download: bool = True,
    heights: list[int] | None = None,
) -> None:
    """Render a report preview: info bar, metadata, controls and iframe.

    Args:
        html: raw report HTML.
        caption: markdown caption shown above the controls.
        file_name: suggested download file name.
        height_key: unique session-state key for the height slider.
        meta: optional trend metadata (``keyword``/``date_from``/``date_to``/
            ``total_papers``) rendered in a collapsible expander.
        theme: inject the Animal Crossing theme before embedding.
        download: show the "download HTML" button.
    """
    heights = heights or _HEIGHTS

    st.caption(caption)

    if meta:
        with st.expander(t("reports_meta_expander"), expanded=False):
            cols = st.columns(3)
            if "keyword" in meta:
                cols[0].metric(t("meta_keyword"), meta["keyword"])
            if "date_from" in meta and "date_to" in meta:
                cols[1].metric(
                    t("meta_date_range"), f"{meta['date_from']} → {meta['date_to']}"
                )
            if "total_papers" in meta:
                cols[2].metric(t("meta_papers"), meta["total_papers"])

    ctrl = st.columns([1, 3])
    with ctrl[0]:
        if download:
            st.download_button(
                t("report_download"),
                data=html.encode("utf-8"),
                file_name=file_name,
                mime="text/html",
                use_container_width=True,
                key=f"dl_{height_key}",
            )
    with ctrl[1]:
        if st.session_state.get(height_key) not in heights:
            st.session_state[height_key] = 1000
        height = st.select_slider(t("reports_height"), options=heights, key=height_key)

    try:
        content = inject_ac_theme(html) if theme else html
        components.html(content, height=height, scrolling=True)
    except Exception as e:  # pragma: no cover - render guard
        st.error(f"{t('reports_load_error')}: {e}")
