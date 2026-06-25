# main.py 线性工作原理

*2026-03-17T03:43:25Z by Showboat 0.6.1*
<!-- showboat-id: 74758c3a-1915-46c9-902e-ef58e3246a1a -->

## 目的

本文档逐行梳理 `main.py` 的执行流程，说明启动参数、模式选择、运行锁机制和流程分发。

---

## 运行入口

`main.py` 是项目唯一入口。它的职责是：

- 解析 CLI 参数（包括模式、关键词、时间范围等）
- 准备工作目录与日志
- 通过 `run_lock()` 保护不同模式的并发运行
- 启动相应的 `Pipeline` 执行核心流程

本文件没有定义任何自有函数逻辑，主要通过 `parse_args()` 解析参数，然后在 `__main__` 分发。

---

## CLI 参数说明

`main.py` 使用 `argparse` 定义如下参数：

- `--mode`: 运行模式（`daily_research`、`trend_research`），默认 `daily_research`
- `--keywords`: 仅在 `trend_research` 模式下使用，必须提供
- `--date-from` / `--date-to`: 仅在 `trend_research` 模式下使用，控制时间区间
- `--sort-order`: `ascending`/`descending`（趋势分析时控制时间排序）
- `--max-results`: 趋势分析时的结果上限，可覆盖配置值
- `--categories`: 趋势分析时可选的 ArXiv 分类过滤

### 关键行为

- `--mode trend_research` 需要 `--keywords`，否则程序会退出并返回码 `1`
- `--date-to` 默认为当天（`date.today()`），`--date-from` 默认为 `date_to - settings.RESEARCH_DEFAULT_DATE_RANGE_DAYS`

---

## 运行流程（核心分支）

### 1) 通用启动前置

在 `if __name__ == "__main__":` 中，它先完成：

1. `settings.ensure_directories()`：确保 `data/` 等目录存在
2. 如果 `settings.AUTO_UPDATE_ENABLED`：运行 `utils/updater.check_and_update()`（失败仅打日志，不中断）
3. 通过 `parse_args()` 获取 CLI 参数

### 2) 若 `--mode trend_research`

该分支负责：

- 设置趋势研究日志（`utils/setup_run_log("trend_research")`）
- 校验 `--keywords` 必须存在
- 计算时间区间：
  - `date_to`：`date.today()` 或 `--date-to`
  - `date_from`：`date_to - settings.RESEARCH_DEFAULT_DATE_RANGE_DAYS` 或 `--date-from`
- 决定 `sort_order` 与 `max_results`（命令行覆盖配置）

然后进入运行锁：

```python
with run_lock(
    "trend_research",
    keywords=args.keywords,
    date_from=date_from,
    date_to=date_to,
    categories=args.categories,
):
    TrendResearchPipeline(...).run()
```

`run_lock` 会为该运行生成唯一锁名称，确保同一时刻只允许一个相同参数组合的趋势分析在跑。

**主执行类：** `modes.trend_research.TrendResearchPipeline`

### 3) 否则（默认）每日研究模式

- 设置每日研究日志（`utils/setup_run_log("daily_research")`）
- 进入运行锁：

```python
with run_lock("daily_research"):
    DailyResearchPipeline().run()
```

**主执行类：** `modes.daily_research.DailyResearchPipeline`

---

## run_lock 机制要点

`run_lock` 用于避免重复/并行执行。它基于：

- 模式名称（`daily_research` 或 `trend_research`）
- 以及传入的关键参数（如关键词、日期）

在锁定期间，其他相同锁名的执行会被阻塞或报错（取决于实现细节）。

---

## 线性工作原理总览

1. 运行 `python main.py`，将 `src/` 添加到模块搜索路径（`sys.path.insert(0, ...)`）。
2. 加载全局配置 `settings`，初始化日志。
3. 读取 CLI 参数，判断执行模式。
4. 进入 `run_lock`：
   - `daily_research`：启动 `DailyResearchPipeline().run()`
   - `trend_research`：准备时间/排序/数量参数并启动 `TrendResearchPipeline(...).run()`
5. 程序退出以前，始终确保数据目录已创建且日志已写入。
