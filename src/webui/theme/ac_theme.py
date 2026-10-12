"""Animal Crossing theme overlay for embedded Daily Research reports.

The daily HTML reports ship their own stylesheet
(``configs/templates/reports/html_report.css``).  This module does *not*
modify those files; instead it injects an AC-themed override right before
``</head>`` at preview time, so only the Streamlit panel is re-skinned.

Usage::

    from webui.theme.ac_theme import inject_ac_theme
    components.html(inject_ac_theme(html), height=1000, scrolling=True)
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_THEME_DIR = Path(__file__).resolve().parent
_CSS_PATH = _THEME_DIR / "ac_theme.css"
_FONT_PATH = _THEME_DIR / "fonts" / "nunito-latin-wght-normal.woff2"

_STYLE_ID = 'id="ac-theme"'


@lru_cache(maxsize=1)
def _font_face() -> str:
    """Build an inline @font-face for the Latin/numbers rounded font.

    The report is rendered inside a ``components.html`` iframe (srcdoc), so a
    relative font URL would not resolve; we embed the woff2 as base64 instead.
    The CJK glyphs intentionally fall back to the viewer's system rounded
    fonts (see ``--ac-font`` in ac_theme.css).
    """
    if not _FONT_PATH.exists():
        return ""
    encoded = base64.b64encode(_FONT_PATH.read_bytes()).decode("ascii")
    return (
        "@font-face{"
        "font-family:'AC Latin';"
        "font-style:normal;"
        "font-display:swap;"
        "font-weight:200 1000;"
        f"src:url(data:font/woff2;base64,{encoded}) format('woff2-variations');"
        "}"
    )


@lru_cache(maxsize=1)
def font_face_css() -> str:
    """Public accessor for the inline ``@font-face`` rule (cached).

    Used both by the iframe overlay and by the Streamlit panel shell
    (``webui.styles``) so Latin/numbers share the same rounded font.
    """
    return _font_face()


@lru_cache(maxsize=1)
def _theme_css() -> str:
    """Return the full overlay CSS (font face + theme rules), cached."""
    css = _CSS_PATH.read_text(encoding="utf-8") if _CSS_PATH.exists() else ""
    return _font_face() + css


def inject_ac_theme(html: str) -> str:
    """Insert the AC theme ``<style>`` into a report HTML document.

    Idempotent: if the style is already present the input is returned as-is.
    Falls back to prepending the style when there is no ``</head>``.
    """
    if _STYLE_ID in html:
        return html

    style = f'<style {_STYLE_ID}>{_theme_css()}</style>'

    marker = "</head>"
    if marker in html:
        return html.replace(marker, style + marker, 1)
    return style + html
