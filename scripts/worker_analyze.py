#!/usr/bin/env python
"""
Worker-Analyze: 对及格论文进行深度分析（阶段5）。
输入: data/worker_output/{date}/scored_papers.json
输出: data/worker_output/{date}/deep_analyses.json

可独立运行，支持并行分析。
"""

import sys
import logging
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from config import settings
from utils.logger import setup_logger
from agents import AnalysisAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

logger = setup_logger("WorkerAnalyze")


def run_analyze():
    """阶段5: 深度分析及格论文"""
    print("\n" + "=" * 80)
    print("📊 Worker-Analyze: 论文深度分析")
    print("=" * 80 + "\n")
    
    from worker_shared import load_worker_input, save_worker_output, deserialize_paper_from_json, serialize_paper_for_json
    
    # 加载上游数据
    scored_data = load_worker_input("scored_papers")
    if not scored_data or not scored_data.get("papers_by_source"):
        logger.error("未找到评分数据！请先运行 Worker-Fetch")
        return 1
    
    serialized_papers = scored_data["papers_by_source"]
    total_count = scored_data.get("total_count", 0)
    logger.info(f"加载 {total_count} 篇论文的评分数据")
    
    # 筛选及格论文 + 仅对可下载PDF的数据源做深度分析
    analysis_agent = AnalysisAgent()
    analyses_by_source = {}
    
    for source, papers in serialized_papers.items():
        # 反序列化
        scored_papers = [deserialize_paper_from_json(p) for p in papers]
        
        # 筛选及格论文
        qualified = [p for p in scored_papers if p["score_response"].is_qualified]
        logger.info(f"[{source}] {len(qualified)}/{len(scored_papers)} 篇及格")
        
        if not qualified:
            analyses_by_source[source] = []
            continue
        
        # 深度分析
        analyses = []
        with ThreadPoolExecutor(max_workers=settings.WORKER_THREADS) as executor:
            futures = {}
            for paper_info in qualified:
                paper_meta = paper_info.get("paper_metadata")
                if paper_meta:
                    pdf_url = getattr(paper_meta, "get_best_pdf_url", lambda: "")()
                else:
                    pdf_url = paper_info.get("pdf_url", "")
                
                future = executor.submit(
                    _deep_analyze, paper_info, pdf_url, analysis_agent
                )
                futures[future] = paper_info["title"]
            
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"  分析 [{source}]"):
                try:
                    result = future.result()
                    if result:
                        analyses.append(result)
                        logger.info(f"  ✓ 完成: {result['title'][:60]}...")
                except Exception as e:
                    logger.error(f"深度分析失败: {e}")
        
        analyses_by_source[source] = analyses
        logger.info(f"[{source}] 深度分析完成: {len(analyses)} 篇")
    
    # 保存
    save_worker_output("deep_analyses", {
        "analyses_by_source": analyses_by_source,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })
    
    logger.info("=" * 80)
    logger.info("✅ Worker-Analyze 完成!")
    print("\n✅ Worker-Analyze: 论文深度分析完成\n")
    return 0


def _deep_analyze(paper_info, pdf_url, analysis_agent):
    """单篇深度分析（线程安全）"""
    analysis = analysis_agent.deep_analyze(
        title=paper_info["title"],
        pdf_url=pdf_url,
        abstract=paper_info["abstract"],
        fallback_to_abstract=True,
    )
    if analysis:
        return {
            "paper_id": paper_info["paper_id"],
            "title": paper_info["title"],
            "analysis": analysis,
        }
    return None


if __name__ == "__main__":
    sys.exit(run_analyze())
