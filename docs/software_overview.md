# arxiv-daily-researcher: 全局工作原理

*2026-03-17T03:33:27Z by Showboat 0.6.1*
<!-- showboat-id: 79bf3f04-8691-492f-901a-89bb2941a24d -->

## 目标

本文件为 `arxiv-daily-researcher` 提供一个线性的、可重复的执行流程概览，便于快速理解入口、配置、核心模块职责和输出路径。

---

## 目录

1. [运行入口与模式](#运行入口与模式)
2. [配置体系（`.env` + `configs/config.json`）](#配置体系env--configsconfigjson)
3. [核心模块结构](#核心模块结构)
4. [典型运行流程（每日研究模式）](#典型运行流程每日研究模式)
5. [典型运行流程（趋势研究模式）](#典型运行流程趋势研究模式)
6. [输出与数据目录](#输出与数据目录)
7. [线性工作原理总览](#线性工作原理总览)

---

## 运行入口与模式

项目的唯一入口是 `main.py`，它负责：

- 读取命令行参数（`--mode`、`--keywords`、`--date-from`、`--date-to` 等）
- 根据 `--mode` 选择两种模式之一：`daily_research` 或 `trend_research`
- 用 `run_lock` 保证同一时间只有一个实例在运行（避免并发冲突）

典型启动命令：

```bash
python main.py
```

进行趋势分析：

```bash
python main.py --mode trend_research --keywords "quantum error correction"
```

`main.py` 的核心控制逻辑在 `if __name__ == "__main__":` 下面：

- `settings.ensure_directories()` 保证所有 `data/` 目录结构存在
- 如果 `settings.AUTO_UPDATE_ENABLED`，会尝试运行 `utils/updater.py` 的 `check_and_update()`
- 通过 `run_lock(...)` 拦截重复运行
- 启动 `modes.daily_research.DailyResearchPipeline` 或 `modes.trend_research.TrendResearchPipeline`

## 配置体系（`.env` + `configs/config.json`）

配置由两部分构成：

1. **环境变量**（`.env`）
   - 主要用于敏感信息（API keys、Webhook URL、邮箱密码等）
   - 由 `src/config.py` 中的 `Settings` 通过 `pydantic-settings` 读取
   - 支持嵌套配置：`CHEAP_LLM__API_KEY=...` 等

2. **JSON 配置**（`configs/config.json`）
   - 核心配置：搜索范围、关键词列表、报告输出、并发设置、通知开关等
   - 通过 `Settings.load_from_search_config()` 加载并覆盖默认值

关键配置项包括：

- `TARGET_DOMAINS` / `MAX_RESULTS` / `SEARCH_DAYS`（搜索范围）
- `ENABLED_SOURCES`（启用的数据源：`arxiv`、各期刊代码）
- `PRIMARY_KEYWORDS`（主要关键词）
- `ENABLE_NOTIFICATIONS` + 各通知通道设置
- `PDF_PARSER_MODE`（`mineru` 或 `pymupdf`）
- `ENABLE_CONCURRENCY` / `CONCURRENCY_WORKERS`

> 💡 约定：配置优先级为 `configs/config.json` > `.env` > 代码默认值。

## 核心模块结构

项目核心目录如下：

- `src/modes/`：两种主流程（`daily_research`、`trend_research`）
- `src/sources/`：论文抓取和元数据封装（ArXiv、OpenAlex、Semantic Scholar）
- `src/agents/`：LLM 逻辑（评分/分析/关键词/趋势分析）
- `src/report/`：报告渲染（Markdown/HTML）
- `src/notifications/`：通知发送（邮件、微信、钉钉、Telegram、Slack、通用Webhook）
- `src/utils/`：辅助工具（日志、运行锁、token 计数、更新检查）

核心类与职责（高层概览）：

- `modes.daily_research.DailyResearchPipeline`：每日研究全流程
- `modes.trend_research.TrendResearchPipeline`：趋势分析全流程
- `sources.SearchAgent`：整合多个数据源并统一返回 `PaperMetadata`
- `agents.KeywordAgent`：关键词准备与权重计算
- `agents.AnalysisAgent`：论文评分、翻译、深度分析
- `report.daily.Reporter` / `report.trend.reporter.TrendReporter`：生成最终报告
- `notifications.NotifierAgent`：按配置发送通知

---

## 典型运行流程（每日研究模式）

### 1. 启动与配置加载

- `main.py` 解析 `--mode`，默认进入每日研究模式
- `settings.ensure_directories()` 创建必要目录（`data/reports`、`data/downloaded_pdfs` 等）
- 设置日志（`utils/logger.py`），并开启 `token_counter`（若启用）

### 2. 准备关键词

- `KeywordAgent.get_all_keywords()` 读取：
  - `settings.PRIMARY_KEYWORDS`（主要关键词）
  - 若启用 `ENABLE_REFERENCE_EXTRACTION`，则从参考文献提取额外关键词
- 计算总权重并基于 `settings.calculate_passing_score()` 得出及格分

### 3. 抓取论文（多源）

- `SearchAgent.fetch_all_papers(days=settings.SEARCH_DAYS)`
- 默认数据源：`arxiv`
- 可选期刊：通过 `OpenAlexSource`（配置 `ENABLED_SOURCES`、`TARGET_JOURNALS`）
- 结果按数据源分组，返回 `Dict[source, List[PaperMetadata]]`

### 4. 评分（关键词相关度 + 其他信号）

- 统一使用 `AnalysisAgent.score_paper_with_keywords()` 计算得分
- 支持并发（`settings.ENABLE_CONCURRENCY`）
- 会调用 `analysis_agent.translate_abstract()` 进行摘要翻译，并在内存 `translation_cache` 中缓存
- 将每个论文标记为“已处理”（`SearchAgent.mark_as_processed()`）以避免重复抓取

### 5. 深度分析（仅对有 PDF 的及格论文）

- 仅针对 `score_response.is_qualified == True` 的论文
- 若：
  - 具备 PDF（`PaperMetadata.has_pdf_access()`）
  - 并且来源支持下载（目前仅 ArXiv）

- 调用 `AnalysisAgent.deep_analyze()`，对 PDF/摘要做深层 LLM 解析

### 6. 生成报告

- `report.daily.Reporter.generate_reports_by_source()`
- 输出路径：`data/reports/daily_research/{markdown,html}/...`（按数据源分文件）

### 7. 关键词趋势（可选）

- 如果 `KEYWORD_TRACKER_ENABLED` 且 `KEYWORD_NORMALIZATION_ENABLED`：
  - 运行 `KeywordTracker.run_daily_normalization()`
  - 根据 `KEYWORD_REPORT_FREQUENCY` 生成趋势报告

### 8. 通知

- 若 `ENABLE_NOTIFICATIONS`：构建 `RunResult` 并通过 `NotifierAgent.notify()` 发送
- 通知内容包括：Top-N 论文、统计信息和报告链接

---

## 典型运行流程（趋势研究模式）

### 1. 启动与输入校验

- `main.py --mode trend_research` 要求必须传 `--keywords` 参数
- `--date-from` / `--date-to` 影响论文检索时间窗口
- `--sort-order`（`ascending`/`descending`）控制结果时间排序
- `--max-results` 可覆盖配置中的 `RESEARCH_MAX_RESULTS`

### 2. 搜索论文（ArXiv）

- `ArxivSource.search_by_keywords(...)` 仅使用 ArXiv 源（不使用 OpenAlex）
- 结果为 `List[PaperMetadata]`

### 3. 生成 TLDR（可选）

- `TrendAgent.generate_tldr(paper)` 为每篇论文生成简短摘要
- 支持并发（`settings.ENABLE_CONCURRENCY`）
- 文档中为每篇论文生成 `tldrs[paper_id]`

### 4. 趋势分析（Skills 系统）

- `TrendAgent.analyze_trends(...)` 调用已启用的技能（`settings.RESEARCH_ENABLED_SKILLS`）
- 结果用于报告和通知

### 5. 生成报告

- `report.trend.reporter.TrendReporter.render(...)` 生成 Markdown/HTML
- 输出路径：`data/reports/trend_research/{markdown,html}`

### 6. 通知

- `NotifierAgent.notify_trend()` 发送趋势分析结果

---

## 输出与数据目录

主要的数据输出目录位于 `data/`：

- `data/reports/`：生成的 Markdown/HTML 报告
  - `daily_research/`（每日研究）
  - `trend_research/`（趋势分析）
  - `keyword_trend/`（关键词趋势图表）
- `data/downloaded_pdfs/`：从 ArXiv 下载的 PDF
- `data/history/`：抓取历史（避免重复处理），例如 `arxiv_history.json` / `openalex_history.json`
- `data/keywords/`：关键词跟踪数据库

日志文件写入 `logs/`，默认滚动保留 `settings.LOG_KEEP_DAYS` 天。

---

## 线性工作原理总览

1. `python main.py` 启动，读取 `.env` + `configs/config.json`，创建必要目录。
2. 通过 `--mode` 进入 `daily_research` 或 `trend_research`。
3. `daily_research`：准备关键词 → 抓取论文 → 评分 → 深度分析 → 报告 → 通知。
4. `trend_research`：关键词 + 时间窗口 → 抓取 ArXiv → 生成 TLDR → 趋势技能分析 → 报告 → 通知。
5. 结果输出到 `data/reports/...`，日志写入 `logs/`，抓取历史写入 `data/history/`。
6. 若启用 `ENABLE_NOTIFICATIONS`，通过邮件/企业微信/钉钉/Telegram/Slack/Webhook 发送结果。
7. 若开启 `AUTO_UPDATE_ENABLED`，程序启动时会尝试自检更新（`utils/updater.py`）。
