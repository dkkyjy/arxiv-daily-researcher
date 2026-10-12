"""Animal Crossing theme for the Streamlit config panel shell.

The design tokens mirror ``src/webui/theme/ac_theme.css`` (ported from the
ac-site-template).  Light ("day") theme only.  The Latin/numbers font is
inlined via the shared ``font_face_css`` helper so the panel and the embedded
reports look identical offline.
"""

from webui.theme.ac_theme import font_face_css

CUSTOM_CSS = f"""
<style>
{font_face_css()}

/* ==================== Design tokens ==================== */
:root {{
    --ac-primary: #2abaaa;
    --ac-primary-light: #6dd5c8;
    --ac-primary-dark: #1f9489;
    --ac-cream: #f7f3e7;
    --ac-cream-dark: #ece6d4;
    --ac-sand: #ddd6c0;
    --ac-wood: #c4a46c;
    --ac-wood-dark: #a8894e;
    --ac-text: #877358;
    --ac-text-light: #a69580;
    --ac-text-dark: #6b5c48;
    --ac-green: #8bc34a;
    --ac-pink: #f48fb1;
    --ac-surface: #ffffff;
    --ac-border: #ddd6c0;
    --ac-shadow: 0 2px 8px rgba(135, 115, 88, 0.12);
    --ac-shadow-hover: 0 4px 16px rgba(135, 115, 88, 0.2);
    --ac-radius-sm: 10px;
    --ac-radius-md: 14px;
    --ac-radius-lg: 20px;
    --ac-radius-full: 9999px;
    --ac-font: "AC Latin", "Nunito Variable", "M PLUS Rounded 1c",
        "LXGW WenKai Screen", "HarmonyOS Sans SC", "PingFang SC",
        "Hiragino Maru Gothic ProN", "Microsoft YaHei", "Noto Sans CJK SC",
        sans-serif;
}}

/* ==================== Global ==================== */
html, body, [class*="st-"], [data-testid="stAppViewContainer"] {{
    font-family: var(--ac-font);
    color: var(--ac-text);
}}

.stApp {{
    background-color: var(--ac-cream);
    background-image: none;
}}

[data-testid="stHeader"] {{
    background-color: transparent;
}}

.block-container {{
    padding-top: 3rem;
    padding-bottom: 2.5rem;
}}

/* ==================== Header ==================== */
.main-header {{
    font-size: 1.9rem;
    font-weight: 800;
    color: var(--ac-text-dark);
    margin-top: 0.25rem;
    margin-bottom: 0.5rem;
    line-height: 1.4;
    padding: 4px 0;
}}
.sub-header {{
    color: var(--ac-text-light);
    font-size: 0.95rem;
    margin-bottom: 1.5rem;
}}

/* ==================== Tabs ==================== */
.stTabs [data-baseweb="tab-list"] {{
    gap: 6px;
    background-color: var(--ac-cream-dark);
    border-radius: var(--ac-radius-full);
    padding: 5px;
}}
.stTabs [data-baseweb="tab"] {{
    border-radius: var(--ac-radius-full);
    padding: 8px 18px;
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--ac-text);
}}
.stTabs [data-baseweb="tab"]:hover {{
    background-color: rgba(255, 255, 255, 0.55);
}}
.stTabs [aria-selected="true"] {{
    background-color: var(--ac-primary) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 0 var(--ac-primary-dark);
}}
.stTabs [data-baseweb="tab-highlight"],
.stTabs [data-baseweb="tab-border"] {{
    display: none;
}}

/* ==================== Sidebar ==================== */
[data-testid="stSidebar"] {{
    background: var(--ac-cream-dark);
    border-right: 2px solid var(--ac-border);
}}
[data-testid="stSidebar"] [data-testid="stMarkdown"] p,
[data-testid="stSidebar"] [data-testid="stMarkdown"] li,
[data-testid="stSidebar"] [data-testid="stMarkdown"] span {{
    color: var(--ac-text) !important;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    color: var(--ac-text-dark) !important;
}}
[data-testid="stSidebar"] hr {{
    border-color: var(--ac-sand);
    margin: 1rem 0;
}}

/* ==================== Buttons ==================== */
.stButton > button,
.stDownloadButton > button,
button[kind="secondary"] {{
    border-radius: var(--ac-radius-md);
    border: 2px solid var(--ac-border);
    background-color: var(--ac-surface);
    color: var(--ac-text-dark);
    font-weight: 600;
    transition: all 0.12s ease;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
button[kind="secondary"]:hover {{
    border-color: var(--ac-primary-light);
    color: var(--ac-primary-dark);
    background-color: var(--ac-surface);
}}
/* Primary — AC 3D press-down button */
.stButton > button[kind="primary"],
button[kind="primary"] {{
    background-color: var(--ac-primary);
    color: #ffffff;
    border: 3px solid var(--ac-primary-dark);
    border-radius: var(--ac-radius-md);
    box-shadow: 0 4px 0 var(--ac-primary-dark);
}}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {{
    background-color: var(--ac-primary-light);
    color: #ffffff;
    transform: translateY(-1px);
    box-shadow: 0 5px 0 var(--ac-primary-dark);
}}
.stButton > button[kind="primary"]:active,
button[kind="primary"]:active {{
    transform: translateY(3px);
    box-shadow: 0 1px 0 var(--ac-primary-dark);
}}

/* ==================== Inputs / Selects ==================== */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea textarea,
.stSelectbox > div > div,
[data-baseweb="select"] > div {{
    border-radius: var(--ac-radius-md) !important;
    border-color: var(--ac-border) !important;
    background-color: var(--ac-surface) !important;
}}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea textarea:focus {{
    border-color: var(--ac-primary) !important;
    box-shadow: 0 0 0 2px rgba(42, 186, 170, 0.25) !important;
}}

/* ==================== Metric cards ==================== */
[data-testid="stMetric"] {{
    background-color: var(--ac-surface);
    border: 2px solid var(--ac-border);
    border-radius: var(--ac-radius-lg);
    padding: 14px 18px;
    box-shadow: var(--ac-shadow);
}}
[data-testid="stMetricLabel"] {{
    color: var(--ac-text-light) !important;
    font-weight: 600;
}}
[data-testid="stMetricValue"] {{
    color: var(--ac-primary-dark) !important;
    font-weight: 800;
}}

/* ==================== Card / Expander ==================== */
[data-testid="stExpander"] {{
    background-color: var(--ac-surface);
    border: 2px solid var(--ac-border);
    border-radius: var(--ac-radius-md);
    margin-bottom: 0.8rem;
    overflow: hidden;
}}
[data-testid="stExpander"] summary {{
    font-weight: 700;
    font-size: 0.95rem;
    color: var(--ac-text-dark);
    background-color: var(--ac-cream);
}}
[data-testid="stExpander"] summary:hover {{
    color: var(--ac-primary-dark);
}}

/* ==================== Alerts ==================== */
[data-testid="stAlert"] {{
    border-radius: var(--ac-radius-md);
    border: 2px solid var(--ac-border);
}}

/* ==================== Status boxes ==================== */
.config-status {{
    padding: 8px 12px;
    border-radius: var(--ac-radius-sm);
    margin: 8px 0;
    font-size: 0.85rem;
}}
.status-saved {{
    background-color: #eaf6d8;
    border: 1px solid var(--ac-green);
    color: #3e6416;
}}
.status-unsaved {{
    background-color: #fff8e1;
    border: 1px solid #ffe08a;
    color: #856404;
}}

/* ==================== Section headers ==================== */
.section-title {{
    font-size: 1.15rem;
    font-weight: 800;
    color: var(--ac-text-dark);
    margin-top: 1rem;
    margin-bottom: 0.5rem;
    padding-bottom: 0.3rem;
    border-bottom: 3px solid var(--ac-primary);
    display: inline-block;
    border-radius: 2px;
}}

/* ==================== Info hint ==================== */
.hint-text {{
    color: var(--ac-text-light);
    font-size: 0.82rem;
    margin-top: -0.5rem;
    margin-bottom: 0.8rem;
}}

/* ==================== Divider ==================== */
hr {{
    border-color: var(--ac-border);
}}
</style>
"""
