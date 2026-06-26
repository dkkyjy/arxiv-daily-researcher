#!/usr/bin/env python
"""
Worker-Fetch: 配置加载 + 关键词准备 + 论文抓取 + 评分。
输出: data/worker_output/{date}/scored_papers.json

独立可运行，无依赖其他Worker。
"""

import sys
import os
import logging
import argparse
from pathlib import Path

# 添加src到path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from config import settings
from utils.logger import setup_logger
from agents import KeywordAgent, AnalysisAgent
from sources import SearchAgent
from datetime import datetime

# 复用原始pipeline中的评分函数
from modes.daily_research import _score_single_paper

logger = setup_logger("WorkerFetch")


def run_fetch(dry_run=False, days=7):
    """阶段1-4: 配置加载 → 关键词 → 抓取 → 评分，输出中间数据

    Args:
        dry_run: 仅加载配置和关键词，不调用外部API（抓取+评分）
        days: 搜索最近N天的论文
    """
    print("\n" + "=" * 80)
    print(f"{'🔍 [DRY RUN] ' if dry_run else ''}Worker-Fetch: 论文抓取与评分")
    print("=" * 80 + "\n")
    
    # === 阶段1: 配置加载 ===
    logger.info(">>> [阶段1] 加载配置...")
    logger.info(f"启用的数据源: {settings.ENABLED_SOURCES}")
    
    # === 阶段2: 关键词准备 ===
    logger.info(">>> [阶段2] 准备关键词...")
    from worker_shared import save_worker_output
    keyword_agent = KeywordAgent()
    all_keywords = keyword_agent.get_all_keywords()
    
    if not all_keywords:
        logger.error("未找到任何关键词！")
        return 1
    
    logger.info(f"关键词总数: {len(all_keywords)} 个")
    total_weight = sum(all_keywords.values())
    passing_score = settings.calculate_passing_score(total_weight)
    logger.info(f"动态及格分: {passing_score:.1f}")
    
    # 保存关键词供下游使用
    save_worker_output("keywords", {
        "all_keywords": all_keywords,
        "primary_count": len(settings.PRIMARY_KEYWORDS),
        "total_weight": total_weight,
        "passing_score": passing_score,
        "timestamp": datetime.now().isoformat(),
    })
    
    if dry_run:
        logger.info(">>> [DRY RUN] 跳过抓取和评分阶段")
        print("\n✅ Worker-Fetch (DRY RUN): 配置与关键词验证通过\n")
        return 0
    
    # === 阶段3: 抓取论文 ===
    logger.info(">>> [阶段3] 从多个数据源抓取论文...")
    search_agent = SearchAgent(
        history_dir=settings.HISTORY_DIR,
        enabled_sources=settings.ENABLED_SOURCES,
        arxiv_domains=settings.TARGET_DOMAINS,
        journals=settings.TARGET_JOURNALS,
        max_results=settings.MAX_RESULTS,
        max_results_per_source=settings.MAX_RESULTS_PER_SOURCE,
    )
    
    papers_by_source = search_agent.fetch_all_papers(days=days)
    total_papers_count = sum(len(p) for p in papers_by_source.values())
    logger.info(f"抓取完成: 共 {total_papers_count} 篇论文")
    
    if total_papers_count == 0:
        logger.warning("没有新论文，跳过后续处理")
        save_worker_output("scored_papers", {"papers_by_source": {}, "total_count": 0})
        return 0
    
    for source, papers in papers_by_source.items():
        logger.info(f"  [{source}] 抓取 {len(papers)} 篇")
    
    # === 阶段4: 评分 ===
    logger.info(">>> [阶段4] 对论文进行加权评分...")
    analysis_agent = AnalysisAgent()
    
    import hashlib
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm
    
    translation_cache = {}
    cache_lock = threading.Lock()
    
    scored_papers_by_source = {}
    for source, papers in papers_by_source.items():
        scored_papers = []
        llm_semaphore = threading.Semaphore(min(settings.CONCURRENCY_WORKERS, 3))
        with ThreadPoolExecutor(max_workers=settings.CONCURRENCY_WORKERS) as executor:
            def _submit_with_semaphore(paper):
                llm_semaphore.acquire()
                def _release(*args, **kwargs):
                    llm_semaphore.release()
                fut = executor.submit(
                    _score_single_paper,
                    paper, source, analysis_agent, all_keywords,
                    translation_cache, cache_lock, None, search_agent,
                )
                fut.add_done_callback(_release)
                return fut
            futures = {
                _submit_with_semaphore(paper): paper
                for paper in papers
            }
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"  评分 [{source}]"):
                try:
                    result = future.result()
                    if result:
                        result["source"] = source
                        scored_papers.append(result)
                except Exception as e:
                    logger.error(f"评分失败: {e}")
        scored_papers_by_source[source] = scored_papers
        qualified = sum(1 for p in scored_papers if p["score_response"].is_qualified)
        logger.info(f"  [{source}] 评分完成: {qualified}/{len(scored_papers)} 篇及格")
    
    # === 序列化保存中间数据 ===
    from worker_shared import serialize_paper_for_json
    
    serialized = {}
    for source, papers in scored_papers_by_source.items():
        serialized[source] = [serialize_paper_for_json(p) for p in papers]
    
    save_worker_output("scored_papers", {
        "papers_by_source": serialized,
        "total_count": total_papers_count,
        "timestamp": datetime.now().isoformat(),
    })
    
    logger.info("=" * 80)
    logger.info("✅ Worker-Fetch 完成!")
    print("\n✅ Worker-Fetch: 论文抓取与评分完成\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Worker-Fetch: 论文抓取与评分")
    parser.add_argument("--dry-run", action="store_true", help="仅验证配置和关键词，不调用外部API")
    parser.add_argument("--days", type=int, default=7, help="搜索最近N天的论文")
    args = parser.parse_args()
    sys.exit(run_fetch(dry_run=args.dry_run, days=args.days))
