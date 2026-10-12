# 日报输出可视化 — 设计方案与实施计划 v2

> 范围：**仅** `data/reports/daily_research/`（每日研究报告）
> 形态：**沿用现有 Streamlit 面板** + **直接嵌入 HTML** + **单报告详情浏览**
> 皮肤：**移植 ac-site-template 的动森主题 CSS**（非复用 Astro 组件）
> 参考：`~/storage/github/ac-site-template/src/styles/global.css`、`~/storage/github/animal-island-ui/DESIGN_PROMPT.md`

---

## 1. 需求确认

| 项 | 决定 |
| --- | --- |
| UI 框架 | 现有 Streamlit 面板（`src/webui/config_panel.py`），新增只读 Tab |
| 报告呈现 | **直接嵌入现成 HTML**（`components.html`），不重新渲染内容 |
| 交互深度 | **单报告详情浏览**：选报告 → 看该报告全文 |
| 视觉风格 | 复刻 `ac-site-template` 的动森主题（CSS token 移植，非组件复用） |

---

## 2. 关于「能否用 ac-site-template 的 UI 组件」

### 结论：组件不可直接用，**样式可完整复用**

| 方案 | 可行性 | 说明 |
| --- | --- | --- |
| 复用 `.astro` 组件 | ❌ | Astro 构建时编译 + Tailwind JIT purge，Streamlit 无法渲染 |
| 复用 `animal-island-ui`（React 组件库） | ❌ | 需要 React 运行时；除非自建 Streamlit 自定义组件（重） |
| **移植其 CSS 设计 token / 组件类** | ✅ **采用** | `global.css` 是纯 CSS，零构建依赖 |
| 引其编译产物 `dist/_astro/*.css` | ⚠️ 不采用 | JIT purge 后类名不全、体积 90KB~1.1MB |

### 可复用的动森设计 token（来自 `global.css`）

```css
:root {
  --ac-primary:#2abaaa; --ac-primary-light:#6dd5c8; --ac-primary-dark:#1f9489;
  --ac-cream:#f7f3e7; --ac-sand:#ddd6c0; --ac-wood:#c4a46c;
  --ac-text:#877358; --ac-text-light:#a69580;
  --ac-green:#8bc34a; --ac-pink:#f48fb1; --ac-yellow:#fff176; --ac-orange:#ffb74d;
  --ac-surface:#ffffff; --ac-border:#ddd6c0;
  --ac-shadow:0 2px 8px rgba(135,115,88,.12);
  --ac-shadow-hover:0 4px 16px rgba(135,115,88,.2);
  --ac-radius-sm:8px; --ac-radius-md:14px; --ac-radius-lg:20px; --ac-radius-xl:28px;
  --ac-font:"Nunito Variable","HarmonyOS Sans SC",sans-serif;
}
.btn-ac {                     /* 动森 3D 按压按钮 */
  background:var(--ac-primary); border:3px solid var(--ac-primary-dark);
  border-radius:var(--ac-radius-md); box-shadow:0 4px 0 var(--ac-primary-dark);
}
[data-theme="night"] { /* 夜间主题变量覆盖 */ }
```

---

## 3. 皮肤注入方案（直接嵌入 HTML 的前提下）

日报 HTML 的样式为**外置 CSS**（`configs/templates/reports/html_report.css`，由 `reporter._get_report_css()` 注入 `<head>`），类名稳定：
`.card` / `.card.pass` / `.card.fail`、`.badge`、`.stat .num .label`、`.stats-bar`、`.tldr`、`.abstract-cn`、`.analysis-content`、`.field` / `.field-label`、`.score`、`.card-title`、`.meta`。

### 两条路线

| 路线 | 做法 | 影响面 | 建议 |
| --- | --- | --- | --- |
| **1. UI 内叠加（推荐）** | 预览时读 HTML → 在 `</head>` 前插入 `<style id="ac-theme">…</style>` → `components.html()` | 仅面板显示；生成文件/邮件/PDF 不变 | ✅ 采用 |
| 2. 全局换肤 | 直接改 `html_report.css` 的 token/组件样式 | 所有报告 + 邮件 + PDF 全变 | 备选，视是否要统一品牌 |

### 路线 1 的关键实现

```python
# src/webui/theme/ac_theme.py
def inject_ac_theme(html: str, dark: bool = False) -> str:
    css = (THEME_DIR / "ac_theme.css").read_text(encoding="utf-8")
    style = f'<style id="ac-theme">{css}</style>'
    if "</head>" in html:
        return html.replace("</head>", style + "</head>", 1)
    return style + html
```

`ac_theme.css` 内容 = **token 变量** + **对日报既有类的覆盖样式**，例如：

```css
/* 报告容器 */
body { background: var(--ac-cream); font-family: var(--ac-font);
       color: var(--ac-text); max-width: 1000px; }
h1, h2 { color: var(--ac-text-dark); }
h2 { border-bottom: 2px solid var(--ac-border); }

/* 统计栏 → 动森卡片 */
.stat { background: var(--ac-surface); border: 2px solid var(--ac-border);
        border-radius: var(--ac-radius-lg); box-shadow: var(--ac-shadow); }
.stat .num { color: var(--ac-primary); }

/* 论文卡片 */
.card { background: var(--ac-surface); border: 2px solid var(--ac-border);
        border-radius: var(--ac-radius-lg); box-shadow: var(--ac-shadow);
        border-top: 4px solid var(--ac-primary); }
.card.pass { border-top-color: var(--ac-green); }
.card.fail { border-top-color: var(--ac-pink); }
.badge { border-radius: var(--ac-radius-full); }
.tldr { background: #e6f9f6; border-left-color: var(--ac-primary); }
/* …其余类按需覆盖… */
```

> 同时用同一套 token 更新 `src/webui/styles.py`（侧边栏/标题/Tab），保证面板外壳与报告内部风格一致。

---

## 4. 页面设计（单报告详情浏览）

```
ArXiv Daily Researcher
└── [ Tab ] …现有 7 个…   │  📄 日报浏览（新增，只读）
```

**📄 日报浏览 Tab 布局：**

```
┌ 筛选行 ───────────────────────────────────────────────┐
│  数据源: [ALL ▾]   日期/报告: [2026-10-09 11:09:25 ▾] │
└──────────────────────────────────────────────────────┘
┌ 报告概览卡（动森卡片）────────────────────────────────┐
│  ARXIV · 2026-10-09   生成 11:09:25                   │
│  [抓取 52] [及格 5] [深度分析 5] [及格率 9.6%] [Token] │
└──────────────────────────────────────────────────────┘
┌ 报告全文（components.html，已注入 ac_theme.css）──────┐
│   <嵌入原始 HTML，高度可调，滚动>                      │
└──────────────────────────────────────────────────────┘
```

- 报告列表直接扫描 `data/reports/daily_research/html/{source}/*.html`（复用现有 `tabs/reports.py` 的发现与日期格式化逻辑），默认按 mtime 倒序。
- 概览卡数据：可**解析同名 Markdown**（已验证 537 份 0.39s 可解析）取统计/Token；或从 HTML 静态提取。推荐解析 Markdown，轻量且准确。
- 底部保留「下载 HTML / 打开原始文件」链接。

> 本次**不做**跨报告论文检索和趋势图（用户已明确只要单报告浏览）；架构上预留数据层，后续可加。

---

## 5. 文件结构（改动集中）

```
src/webui/
├── theme/                       # 新增
│   ├── ac_theme.css             # 动森 token + 日报类覆盖（注入用）
│   ├── ac_theme.py              # inject_ac_theme() / font_face_css()
│   └── fonts/                   # 自托管 Nunito 拉丁圆体 woff2（SIL OFL）
├── reader/                      # 新增（避开 .gitignore/.dockerignore 的 data/）
│   └── daily_reports.py         # 新增：扫描报告 + 解析 Markdown 取概览统计
├── tabs/
│   ├── reports.py               # 现有报告查看（三类报告）
│   └── daily_view.py            # 新增：日报浏览 Tab
└── config_panel.py              # +1 Tab 注册（现为 8 Tab）
```

Docker：`Dockerfile.webui` 已 `COPY src/webui/`，新增文件自动包含；CSS 无需新增 pip 依赖。字体如需离线自托管，`COPY src/webui/theme/fonts/` 并在 `ac_theme.css` 用 `@font-face`。

---

## 6. 实施计划

> **进度：Phase 0 ✅ / Phase 1 ✅ / Phase 2 ✅**

### Phase 0 — 皮肤移植 ✅
- [x] `theme/ac_theme.css`：移植动森 token + 覆盖日报既有类
- [x] `theme/ac_theme.py`：`inject_ac_theme(html)`（base64 内联 Nunito + CSS 注入，幂等）
- **已验证**：计算样式确认 body `#f7f3e7`、主色 `#2abaaa`、圆角 20px、Nunito 加载成功；注入 +59KB / 0.3ms

### Phase 1 — 单报告浏览 Tab ✅
- [x] `reader/daily_reports.py`：报告发现 + Markdown 概览解析（541 份 / 291ms）
- [x] `tabs/daily_view.py`：数据源筛选、报告选择、概览卡片、下载、嵌入已换肤 HTML
- [x] `i18n.py` 文案（中英）+ `config_panel.py` 注册为第 8 个 Tab
- **已验证**：AppTest 无异常；浏览器端到端确认 iframe 内 `#ac-theme` 生效

### Phase 2 — 面板外壳统一 + 打磨 ✅
- [x] `styles.py` 套用同一套动森 token（侧边栏/标题/Tab/按钮/输入/Metric/Expander）
- [x] 拉丁/数字字体内联（`font_face_css()` 共享），中文系统回退，离线可用
- [x] README 增补「日报浏览」Tab、项目树、动森主题说明
- [x] 新增 `reader/` 包避开 `.gitignore`/`.dockerignore` 的 `data/` 冲突
- **已验证**：浏览器计算样式确认 app `#f7f3e7`、侧边栏 `#ece6d4`、选中 Tab `#2abaaa`、主按钮 3D 阴影；日报 iframe `#ac-theme` 生效

> Phase 0+1+2 全部完成，合计约 **2 人日**。

---

## 7. 风险与对策

| 风险 | 对策 |
| --- | --- |
| 日报 CSS 类名变更导致覆盖失效 | 覆盖层只改视觉属性，不改结构；类名缺失时自动降级为原样式 |
| 动森字体离线不可用 | 自托管 woff2 + `@font-face`；缺字体时回退系统圆体 |
| 报告 HTML 体积大（~290KB）嵌入卡顿 | 仅嵌入单份、懒加载、`st.cache_data` 缓存 |
| 修改生成 HTML 影响产物 | 采用路线 1，只在 UI 端注入，产物零改动 |
| 与现有 `tabs/reports.py` 功能重叠 | 复用其发现逻辑；HTML 预览统一走换肤注入 |

---

## 8. 待确认

1. 皮肤注入采用**路线 1（UI 内叠加，不改产物）**可以吗？
2. 只做**明色主题**，还是同时做夜间（`data-theme="night"`）？
3. 「日报浏览」作为**新增独立 Tab**，还是直接改造现有「报告查看」Tab？（建议新增，避免影响其他两类报告）
4. 字体接受**自托管 woff2**（体积约几百 KB）吗？

---

## 9. 审核整改（`/grilling` 结论）

用户回复「按推荐执行」，据此完成以下整改：

| # | 问题 | 整改 |
| --- | --- | --- |
| 1 | 报告查看预览未动森化 | 统一走 `components/preview.py`，**所有预览都换肤** |
| 2 | 两 Tab 代码重复 | 抽出 `reader/report_files.py`（通用发现）+ `components/preview.py`（共享预览） |
| 3 | 「选下拉 + 点按钮」两步 | **选中即预览**，去掉「▶ 预览」按钮 |
| 4 | 无下载入口 | 共享预览统一提供「下载 HTML」 |
| 5 | 预览在三个高列下方、点击无感 | 报告查看改为**左侧列表 + 右侧预览**并排 |

**未做（本轮）**：跨报告论文检索、趋势图、list 分页、夜主题、新标签打开（`components.html` 的 srcdoc iframe 无法可靠跳转顶层页）。
