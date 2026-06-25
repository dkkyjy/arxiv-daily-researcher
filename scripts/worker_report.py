#!/usr/bin/env python
"""
Worker-Report: 生成报告 + 关键词趋势 + 发送通知（阶段6-8）。
输入: data/worker_output/{date}/scored_papers.json + deep_analyses.json
输出: 报告 + 通知
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, date

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from config import settings
from utils.logger import setup_logger
from utils.token_counter import token_counter
from report.daily import Reporter
from notifications import NotifierAgent, RunResult

logger = setup_logger("WorkerReport")


def run_report():
    """阶段6-8: 报告生成 + 关键词趋势 + 通知"""
    print("\n" + "=" * 80)
    print("📝 Worker-Report: 报告生成与通知")
    print("=" * 80 + "\n")
    
    from worker_shared import load_worker_input, deserialize_paper_from_json
    
    # 加载评分数据
    scored_data = load_worker_input("scored_papers")
    if not scored_data or not scored_data.get("papers_by_source"):
        logger.error("未找到评分数据！请先运行 Worker-Fetch")
        return 1
    
    serialized_papers = scored_data["papers_by_source"]
    total_count = scored_data.get("total_count", 0)
    
    # 恢复 scored_papers_by_source
    scored_papers_by_source = {}
    for source, papers in serialized_papers.items():
        scored_papers_by_source[source] = [deserialize_paper_from_json(p) for p in papers]
    
    logger.info(f"加载 {total_count} 篇论文的评分数据")
    for source, papers in scored_papers_by_source.items():
        qualified = sum(1 for p in papers if p["score_response"].is_qualified)
        logger.info(f"  [{source}] {len(papers)} 篇, {qualified} 篇及格")
    
    # 加载深度分析数据
    analyses_data = load_worker_input("deep_analyses")
    if analyses_data and analyses_data.get("analyses_by_source"):
        analyses_by_source = analyses_data["analyses_by_source"]
        for source, analyses in analyses_by_source.items():
            logger.info(f"  [{source}] 深度分析: {len(analyses)} 篇")
    else:
        analyses_by_source = {}
        logger.info("未找到深度分析数据，跳过")
    
    # 加载关键词（用于报告）
    kw_data = load_worker_input("keywords")
    all_keywords = kw_data.get("all_keywords", {}) if kw_data else {}
    logger.info(f"关键词: {len(all_keywords)} 个")
    
    # === 阶段6: 生成报告 ===
    logger.info(">>> [阶段6] 生成分数据源研究报告...")
    reporter = Reporter()
    report_paths = reporter.generate_reports_by_source(
        scored_papers_by_source=scored_papers_by_source,
        analyses_by_source=analyses_by_source,
        keywords_dict=all_keywords,
        token_usage=token_counter.get_summary() if settings.TOKEN_TRACKING_ENABLED else None,
    )
    logger.info(f"报告已生成: {len(report_paths)} 个数据源")
    for source, path in report_paths.items():
        logger.info(f"  [{source}] {path}")
    
    # === 阶段7: 关键词趋势处理 ===
    if settings.KEYWORD_NORMALIZATION_ENABLED:
        logger.info(">>> [阶段7] 运行每日关键词标准化...")
        try:
            from keyword_tracker import KeywordTracker
            keyword_tracker = KeywordTracker()
            stats = keyword_tracker.run_daily_normalization()
            logger.info(f"  标准化完成: {stats}")
            
            if settings.KEYWORD_REPORT_ENABLED:
                today = date.today()
                should_generate = False
                freq = settings.KEYWORD_REPORT_FREQUENCY
                if freq == "always" or freq == "daily":
                    should_generate = True
                elif freq == "weekly":
                    should_generate = today.weekday() == 0
                elif freq == "monthly":
                    should_generate = today.day == 1
                
                if should_generate:
                    logger.info("  生成关键词趋势报告...")
                    from report.keyword_trend import KeywordTrendReporter
                    kw_reporter = KeywordTrendReporter()
                    trend_paths = kw_reporter.render(
                        top_keywords=keyword_tracker.get_top_keywords(),
                        trends=keyword_tracker.get_trends(),
                        bar_chart=keyword_tracker.generate_bar_chart(),
                        trend_chart=keyword_tracker.generate_trend_chart(),
                        today=today,
                        days=keyword_tracker.default_days,
                    )
                    logger.info(f"  趋势报告已保存")
        except Exception as e:
            logger.warning(f"关键词标准化失败: {e}")
    
    # === 构建 RunResult ===
    all_scored_flat = []
    for source, scored_papers in scored_papers_by_source.items():
        for p in scored_papers:
            all_scored_flat.append({
                "title": p["title"],
                "score": p["score_response"].total_score,
                "source": source,
                "tldr": p["score_response"].tldr,
                "url": p["url"],
            })
    all_scored_flat.sort(key=lambda x: x["score"], reverse=True)
    top_papers = all_scored_flat[:settings.NOTIFICATION_TOP_N]
    
    run_result = RunResult(
        run_timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        total_papers_fetched=total_count,
        top_papers=top_papers,
    )
    
    for source, scored_papers in scored_papers_by_source.items():
        qualified = sum(1 for p in scored_papers if p["score_response"].is_qualified)
        analyzed = len(analyses_by_source.get(source, []))
        run_result.papers_by_source[source] = len(scored_papers)
        run_result.qualified_by_source[source] = qualified
        run_result.analyzed_by_source[source] = analyzed
        run_result.total_qualified += qualified
        run_result.total_analyzed += analyzed
    
    run_result.report_paths = {s: str(p) for s, p in report_paths.items()}
    if settings.TOKEN_TRACKING_ENABLED:
        run_result.token_usage = token_counter.get_summary()
    
    # 打印统计
    print("\n📊 统计信息:")
    for source, scored_papers in scored_papers_by_source.items():
        qualified = run_result.qualified_by_source.get(source, 0)
        analyzed = run_result.analyzed_by_source.get(source, 0)
        pct = (qualified / len(scored_papers) * 100) if scored_papers else 0
        print(f"   [{source.upper()}]")
        print(f"     • 抓取: {len(scored_papers)} 篇")
        print(f"     • 及格: {qualified} 篇 ({pct:.1f}%)")
        print(f"     • 深度分析: {analyzed} 篇")
    
    print("\n📁 报告位置:")
    for source, path in report_paths.items():
        print(f"   • [{source}] {path}")
    
    # === 阶段8: 发送通知 ===
    if settings.ENABLE_NOTIFICATIONS:
        logger.info(">>> [阶段8] 发送通知...")
        try:
            notifier = NotifierAgent()
            notifier.notify(run_result)
            logger.info("通知发送完成")
        except Exception as e:
            logger.warning(f"通知发送失败: {e}")
    
    logger.info("=" * 80)
    logger.info("✅ Worker-Report 完成!")
    print("\n✅ Worker-Report: 报告生成与通知完成\n")
    return 0


if __name__ == "__main__":
    sys.exit(run_report())
