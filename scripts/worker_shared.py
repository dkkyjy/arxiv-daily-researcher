import json
from pathlib import Path

WORKER_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "worker_output"

def serialize_paper_for_json(paper_dict: dict) -> dict:
    """
    将评分后的单篇论文dict转换为可JSON序列化的格式。
    原始对象中的 PaperMetadata (paper_metadata) 和 ScoreResponse (score_response) 需要特别处理。
    """
    paper_meta = paper_dict.get("paper_metadata")
    score_resp = paper_dict.get("score_response")
    
    serialized = {
        "paper_id": paper_dict.get("paper_id"),
        "title": paper_dict.get("title"),
        "authors": paper_dict.get("authors"),
        "abstract": paper_dict.get("abstract"),
        "abstract_cn": paper_dict.get("abstract_cn", ""),
        "url": paper_dict.get("url"),
        "pdf_url": paper_dict.get("pdf_url"),
        "published": paper_dict.get("published"),
        "source": paper_dict.get("source", ""),
    }
    
    # 序列化 score_response
    if score_resp:
        serialized["score_response"] = {
            "total_score": getattr(score_resp, "total_score", 0),
            "relevance_score": getattr(score_resp, "relevance_score", 0),
            "novelty_score": getattr(score_resp, "novelty_score", 0),
            "methodology_score": getattr(score_resp, "methodology_score", 0),
            "impact_score": getattr(score_resp, "impact_score", 0),
            "is_qualified": getattr(score_resp, "is_qualified", False),
            "tldr": getattr(score_resp, "tldr", ""),
            "relevance_reasoning": getattr(score_resp, "relevance_reasoning", ""),
            "extracted_keywords": getattr(score_resp, "extracted_keywords", []),
        }
    
    # 序列化 paper_metadata
    if paper_meta:
        serialized["paper_metadata"] = {
            "paper_id": getattr(paper_meta, "paper_id", ""),
            "title": getattr(paper_meta, "title", ""),
            "authors": getattr(paper_meta, "authors", []),
            "abstract": getattr(paper_meta, "abstract", ""),
            "url": getattr(paper_meta, "url", ""),
            "pdf_url": getattr(paper_meta, "pdf_url", ""),
            "published_date": getattr(paper_meta, "published_date", None),
            "source": getattr(paper_meta, "source", ""),
            "categories": getattr(paper_meta, "categories", []),
        }
        # 日期转字符串
        if serialized["paper_metadata"].get("published_date"):
            serialized["paper_metadata"]["published_date"] = str(serialized["paper_metadata"]["published_date"])
    
    return serialized


def deserialize_paper_from_json(data: dict):
    """
    从JSON恢复评分论文数据结构。
    返回一个类似原始评分结果的dict，但 paper_metadata 和 score_response 为dict而非对象。
    对于需要直接访问 score_response.is_qualified 等属性的代码，此函数返回模拟对象。
    """
    class ScoreResponseProxy:
        def __init__(self, d):
            for k, v in d.items():
                object.__setattr__(self, k, v)
        def __repr__(self):
            return f"<ScoreResponseProxy total_score={self.total_score}>"
    
    class PaperMetaProxy:
        def __init__(self, d):
            for k, v in d.items():
                object.__setattr__(self, k, v)
        def get_authors_string(self):
            authors = getattr(self, "authors", [])
            if isinstance(authors, list):
                return ", ".join(authors)
            return str(authors)
        def get_best_pdf_url(self):
            return getattr(self, "pdf_url", "") or getattr(self, "url", "")
        def __repr__(self):
            return f"<PaperMetaProxy paper_id={self.paper_id}>"
    
    result = dict(data)
    if "score_response" in data and isinstance(data["score_response"], dict):
        result["score_response"] = ScoreResponseProxy(data["score_response"])
    if "paper_metadata" in data and isinstance(data["paper_metadata"], dict):
        result["paper_metadata"] = PaperMetaProxy(data["paper_metadata"])
    return result


def save_worker_output(phase: str, data: dict, subdir: str = None):
    """
    保存Worker中间输出到 data/worker_output/{date}/{phase}.json
    """
    from datetime import date
    today = date.today().isoformat()
    output_dir = WORKER_DATA_DIR / today
    if subdir:
        output_dir = output_dir / subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = output_dir / f"{phase}.json"
    
    class CustomEncoder(json.JSONEncoder):
        def default(self, obj):
            return str(obj)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=CustomEncoder)
    
    logger.info(f"Worker输出已保存: {filepath}")
    return filepath


def load_worker_input(phase: str, run_date: str = None, subdir: str = None) -> dict:
    """
    加载Worker中间数据
    """
    from datetime import date
    if not run_date:
        run_date = date.today().isoformat()
    input_dir = WORKER_DATA_DIR / run_date
    if subdir:
        input_dir = input_dir / subdir
    filepath = input_dir / f"{phase}.json"
    
    if not filepath.exists():
        logger.error(f"Worker输入文件不存在: {filepath}")
        return {}
    
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


import logging
logger = logging.getLogger("WorkerShared")
