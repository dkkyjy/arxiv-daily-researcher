#!/usr/bin/env python
"""
OMX Team Worker 入口 — 包装 arxiv-daily-researcher 的各个运行模式。

用法:
  # 完整每日研究（原始单进程）
  python scripts/omx_worker.py daily

  # 独立 Worker 阶段（Pipeline拆分模式）
  python scripts/omx_worker.py worker-fetch          # 阶段1-4: 抓取+评分
  python scripts/omx_worker.py worker-analyze        # 阶段5: 深度分析
  python scripts/omx_worker.py worker-report         # 阶段6-8: 报告+通知

  # 趋势研究
  python scripts/omx_worker.py trend --keywords "quantum error correction"

  # 查看运行状态
  python scripts/omx_worker.py status

此脚本专为 OMX team 设计，每个 worker 可以运行不同的阶段。
支持流水线模式（依赖 data/worker_output/{date}/ 的中间文件共享）。
"""

import sys
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

# 将 src 目录加入路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import settings
from utils.logger import setup_logger, setup_run_log
from utils.run_lock import run_lock

logger = setup_logger("OMXWorker")


def run_daily():
    """运行完整的每日研究 pipeline（原始单进程模式）"""
    logger.info("=" * 80)
    logger.info(f"[OMX Worker] 启动每日研究模式 | PID={os.getpid()}")
    logger.info("=" * 80)

    from modes.daily_research import DailyResearchPipeline

    with run_lock("daily_research"):
        pipeline = DailyResearchPipeline()
        result = pipeline.run()

    success = result.success if hasattr(result, "success") else True
    logger.info(f"[OMX Worker] 每日研究完成 | success={success}")
    return 0 if success else 1


def run_worker_fetch(dry_run=False):
    """阶段1-4: 抓取+评分"""
    logger.info(f">>> [Worker-Fetch] 开始: 配置加载 → 关键词 → 抓取 → 评分{' [DRY RUN]' if dry_run else ''}")
    from worker_fetch import run_fetch
    return run_fetch(dry_run=dry_run)


def run_worker_analyze():
    """阶段5: 深度分析"""
    logger.info(">>> [Worker-Analyze] 开始: 深度分析及格论文")
    from worker_analyze import run_analyze
    return run_analyze()


def run_worker_report():
    """阶段6-8: 报告+通知"""
    logger.info(">>> [Worker-Report] 开始: 生成报告 → 关键词趋势 → 通知")
    from worker_report import run_report
    return run_report()


def run_trend(args):
    """运行趋势研究模式"""
    keywords = args.keywords
    if not keywords:
        logger.error("趋势研究必须指定 --keywords")
        return 1

    log_file = setup_run_log("trend_research")
    logger.info(f"[OMX Worker] 启动趋势研究 | keywords={keywords}")

    from datetime import date, timedelta
    from modes.trend_research import TrendResearchPipeline

    date_to = date.today()
    if args.date_to:
        date_to = date.fromisoformat(args.date_to)

    date_from = date_to - timedelta(days=settings.RESEARCH_DEFAULT_DATE_RANGE_DAYS)
    if args.date_from:
        date_from = date.fromisoformat(args.date_from)

    sort_order = args.sort_order or settings.RESEARCH_SORT_ORDER
    max_results = args.max_results if args.max_results is not None else settings.RESEARCH_MAX_RESULTS

    with run_lock("trend_research", keywords=keywords, date_from=date_from, date_to=date_to):
        TrendResearchPipeline(
            settings=settings,
            keywords=keywords,
            date_from=date_from,
            date_to=date_to,
            sort_order=sort_order,
            max_results=max_results,
            categories=args.categories,
        ).run()

    logger.info(f"[OMX Worker] 趋势研究完成")
    return 0


def run_status():
    """查看当前系统状态"""
    status = {
        "project": "arxiv-daily-researcher",
        "version": "3.0",
        "pid": os.getpid(),
        "timestamp": datetime.now().isoformat(),
        "data_dir": str(settings.DATA_DIR),
        "reports_dir": str(settings.REPORTS_DIR),
        "enabled_sources": settings.ENABLED_SOURCES,
        "keywords_count": len(settings.PRIMARY_KEYWORDS),
        "search_days": settings.SEARCH_DAYS,
        "notifications_enabled": settings.ENABLE_NOTIFICATIONS,
        "token_tracking": settings.TOKEN_TRACKING_ENABLED,
        "worker_scripts": {
            "fetch": str(PROJECT_ROOT / "scripts" / "worker_fetch.py"),
            "analyze": str(PROJECT_ROOT / "scripts" / "worker_analyze.py"),
            "report": str(PROJECT_ROOT / "scripts" / "worker_report.py"),
        },
    }
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description="OMX Team Worker — ArXiv Daily Researcher")
    parser.add_argument(
        "mode",
        nargs="?",
        default="daily",
        choices=["daily", "trend", "status",
                 "worker-fetch", "worker-analyze", "worker-report"],
        help="运行模式: daily(默认), trend, status, worker-fetch, worker-analyze, worker-report",
    )

    # trend / worker-fetch 共享参数
    parser.add_argument("--keywords", nargs="+", help="趋势研究关键词")
    parser.add_argument("--date-from", type=str, help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", type=str, help="截至日期 YYYY-MM-DD")
    parser.add_argument("--sort-order", choices=["ascending", "descending"], help="排序方向")
    parser.add_argument("--max-results", type=int, help="最大论文数")
    parser.add_argument("--categories", nargs="+", help="限制分类")
    parser.add_argument("--dry-run", action="store_true", help="仅验证配置和关键词，不调用外部API（worker-fetch模式）")

    args = parser.parse_args()

    settings.ensure_directories()

    if args.mode == "daily":
        return run_daily()
    elif args.mode == "trend":
        return run_trend(args)
    elif args.mode == "status":
        return run_status()
    elif args.mode == "worker-fetch":
        return run_worker_fetch(dry_run=args.dry_run)
    elif args.mode == "worker-analyze":
        return run_worker_analyze()
    elif args.mode == "worker-report":
        return run_worker_report()
    else:
        print(f"未知模式: {args.mode}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
