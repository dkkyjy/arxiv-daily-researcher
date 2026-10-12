# 每日报告机器可读清单（manifest.json）契约

> 角色：**生产方**为 `arxiv-daily-researcher`，**消费方**为 `research-assistant`
> 版本：`schema_version = "1.0"`
> 原则：只导出「统计 + 论文摘要」；评分明细 / 评分理由 / 深度分析七维仍留在 MD/HTML

---

## 1. 定位

每次每日研究运行，除 Markdown / HTML 报告外，**额外**为每个数据源生成一份
`manifest.json`，供外部系统（research-assistant）以稳定结构化格式消费，
无需再解析报告文本。

- 单向依赖：`arxiv-daily-researcher` 产出 → `research-assistant` 消费
- 同机交付：写入 `data/reports/daily_research/manifest/`
- 失败隔离：manifest 写失败只记 warning，不影响报告与通知

## 2. 路径布局

```
data/reports/daily_research/
├── markdown/{source}/{SOURCE}_Report_{ts}.md
├── html/{source}/{SOURCE}_Report_{ts}.html
└── manifest/{source}/{SOURCE}_Report_{ts}.json      # ← 本契约
```

- `{ts}` = `YYYY-MM-DD_HH-MM-SS`，与同次运行的 MD/HTML **同名同时间戳**
- `REPORTS_BY_SOURCE=false` 时省略 `{source}/` 子目录（与 MD/HTML 行为一致）

## 3. Schema

```jsonc
{
  "schema_version": "1.0",
  "generated_by": "arxiv-daily-researcher",
  "mode": "daily_research",

  "report": {
    "run_id": "2026-10-12_11-00-00",     // 同次运行多源共享
    "timestamp": "2026-10-12 11:05:00",
    "source": "arxiv",
    "source_display": "ArXiv",
    "date": "2026-10-12",
    "scan_days": 1,
    "passing_score": 20.0,
    "keywords": [ { "name": "cosmic-ray", "weight": 1.0 } ]
  },

  "stats": {
    "fetched": 52,
    "passed": 5,
    "deep_analyzed": 5,
    "pass_rate": 0.096
  },

  "tokens": {                            // token 追踪关闭时为 null
    "total": 242760,
    "prompt": 150179,
    "completion": 92581,
    "by_model": { "deepseek-v4-flash": { "prompt": 1, "completion": 1, "total": 2 } }
  },

  "papers": [
    {
      "paper_id": "2610.10695v1",
      "title": "…",
      "authors": ["Ilias Cholis", "Leo Qiyuan Hu"],
      "source": "arxiv",
      "published_date": "2026-10-07",
      "url": "https://arxiv.org/abs/2610.10695v1",
      "doi": null,
      "arxiv_id": "2610.10695",
      "score": 34.0,
      "qualified": true,
      "matched_keywords": ["gamma-ray", "cosmic-ray"],  // 配置关键词中相关度>0
      "keywords": ["Fermi Bubbles", "..."],             // 论文自身关键词(extracted)
      "has_deep_analysis": true,
      "tldr": "…",                       // 仅 qualified 论文，否则 null
      "abstract": "…"                    // 仅 qualified 论文（原文），否则 null
    }
  ],

  "outputs": {
    "markdown": "data/reports/daily_research/markdown/arxiv/ARXIV_Report_2026-10-12_11-00-00.md",
    "html": "data/reports/daily_research/html/arxiv/ARXIV_Report_2026-10-12_11-00-00.html"
  }
}
```

### 3.1 字段说明与约束

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 契约版本；破坏性变更递增 |
| `papers[].authors` | string[] | 作者列表（内部 CSV 字符串已拆分） |
| `papers[].qualified` | bool | 是否达到 `report.passing_score` |
| `papers[].matched_keywords` | string[] | 配置关键词中相关度 > 0 的项 |
| `papers[].keywords` | string[] | 论文自身提取关键词（LLM extracted） |
| `papers[].tldr` / `abstract` | string \| null | **仅 `qualified=true`** 时填充，否则 `null` |
| `papers` | array | 按 `score` 降序，与报告顺序一致 |

### 3.2 明确不含（保留在 MD/HTML）

- `keyword_scores` 逐关键词相关度明细
- `reasoning` 评分理由
- 摘要中文翻译（`abstract_cn`）
- 深度分析七维（创新点/方法/关键结果/技术栈/优点/局限/相关性）

> 消费方如需以上富文本，`research-assistant` 仍可解析 MD 报告作为补充（Q5-A）。

## 4. 兼容性策略

- **新增字段**：向后兼容，不升版本
- **删除/语义变更字段**：升 `schema_version`（`1.1`、`2.0`）
- 消费方应忽略未知字段、对 `null` 做容错

## 5. 生产方实现

| 位置 | 说明 |
| --- | --- |
| `src/report/daily/manifest.py` | `build_source_manifest()` / `write_manifest()`，纯 stdlib |
| `src/report/daily/reporter.py` | `generate_reports_by_source()` 每源写完 MD/HTML 后写 manifest |
| `src/config.py` | `ensure_directories()` 创建 `daily_research/manifest/` |

## 6. 消费方对接（research-assistant）— ✅ 已实施

在 `research-assistant` 仓库完成（363 个测试全部通过，ruff clean）：

| 文件 | 改动 |
| --- | --- |
| `monitoring/report_importer.py` | 新增 `import_manifests()`：按日期聚合多源 manifest → `{date}.jsonl` + `{date}.md`；MD 解析保留为 legacy 路径 |
| `storage/sqlite_store.py` | 新增 `add_external_review()`（顺带修复了调用方一直缺失该方法、外部评审静默丢弃的既有 bug）与 `get_paper_by_doi()`（DOI 去重） |
| `cli/arxiv.py` | `import-reports` 新增 `--format auto\|manifest\|markdown`；默认源目录改为 `…/daily_research/manifest` |

多源与日期模型：manifest 按 `report.date` 分组，同一天多源合并为一份报告（匹配其 `reports.report_date` 主键模型）；MD 软链优先选 arxiv。
