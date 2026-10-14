import fitz  # pymupdf
import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, Set, List, Optional
from config import settings
from utils.llm_request_pool import call_chat_completion
from utils.llm_resilience import build_llm_client
from utils.llm_health import LLMHealthRecorder
from utils.llm_usage import record_token_usage as record_llm_token_usage
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class KeywordAgent:
    """
    关键词提取Agent。

    职责:
    - 从参考PDF中提取带权重的关键词
    - 根据重要性分配不同权重（高/中/低）
    - 使用LLM自动提取专业概念
    - 返回带权重的关键词字典
    - 缓存已提取的关键词，避免重复提取
    - 支持增量更新（只提取新PDF）
    - 智能去重相似关键词
    """

    def __init__(self, health_recorder: Optional[LLMHealthRecorder] = None):
        # 初始化低成本LLM客户端
        self.client = build_llm_client(
            settings.CHEAP_LLM.api_key, settings.CHEAP_LLM.base_url
        )

        # 缓存文件路径
        self.cache_file = settings.DATA_DIR / "keywords" / "keywords_cache.json"
        self._health_recorder = health_recorder

    def _record_llm_health(
        self, success: bool, error: Optional[BaseException] = None
    ) -> None:
        recorder = getattr(self, "_health_recorder", None)
        if recorder is not None:
            recorder("cheap", settings.CHEAP_LLM.model_name, success, error)

    def set_health_recorder(self, health_recorder: Optional[LLMHealthRecorder]) -> None:
        """Attach optional passive observability after agent construction."""
        self._health_recorder = health_recorder

    def _calculate_pdf_hash(self, pdf_path: Path) -> str:
        """
        计算PDF文件的MD5哈希值，用于检测文件是否变化。

        参数:
            pdf_path: PDF文件路径

        返回值:
            str: 文件的MD5哈希值
        """
        try:
            with open(pdf_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"计算PDF哈希失败 {pdf_path}: {e}")
            return ""

    def _load_cache(self) -> Dict:
        """
        加载关键词缓存。

        返回值:
            dict: 缓存数据，格式：
            {
                "pdf_hashes": {"filename": "hash_value"},
                "pdf_keywords": {"filename": {"keyword": weight}},
                "keywords": {"keyword": weight}  # 兼容旧版本
            }
        """
        if not self.cache_file.exists():
            return {"pdf_hashes": {}, "pdf_keywords": {}, "keywords": {}}

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 兼容旧版本缓存格式
                if "pdf_keywords" not in data:
                    data["pdf_keywords"] = {}
                return data
        except Exception as e:
            logger.warning(f"加载缓存失败: {e}，将重新提取")
            return {"pdf_hashes": {}, "pdf_keywords": {}, "keywords": {}}

    def _save_cache(self, cache_data: Dict):
        """
        保存关键词缓存。

        参数:
            cache_data: 要保存的缓存数据
        """
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            logger.info(f"关键词缓存已保存到 {self.cache_file}")
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """
        计算两个字符串的相似度（0-1之间）。

        参数:
            str1: 字符串1
            str2: 字符串2

        返回值:
            float: 相似度分数，1.0表示完全相同
        """
        # 转换为小写进行比较
        s1 = str1.lower().strip()
        s2 = str2.lower().strip()

        # 完全相同
        if s1 == s2:
            return 1.0

        # 使用SequenceMatcher计算相似度
        return SequenceMatcher(None, s1, s2).ratio()

    def _deduplicate_keywords(self, keywords_dict: Dict[str, float]) -> Dict[str, float]:
        """
        去除相似的关键词，保留权重更高的那个。

        参数:
            keywords_dict: 原始关键词字典 {关键词: 权重}

        返回值:
            Dict[str, float]: 去重后的关键词字典
        """
        if not keywords_dict:
            return {}

        threshold = settings.SIMILARITY_THRESHOLD
        keywords_list = list(keywords_dict.items())
        # 按权重降序排序，优先保留高权重关键词
        keywords_list.sort(key=lambda x: x[1], reverse=True)

        deduplicated = {}
        removed_count = 0

        for keyword, weight in keywords_list:
            # 检查是否与已保留的关键词相似
            is_duplicate = False
            for existing_keyword in deduplicated.keys():
                similarity = self._calculate_similarity(keyword, existing_keyword)
                if similarity >= threshold:
                    is_duplicate = True
                    logger.debug(
                        f"去重: '{keyword}' 与 '{existing_keyword}' 相似度 {similarity:.2f} >= {threshold}，已跳过"
                    )
                    removed_count += 1
                    break

            if not is_duplicate:
                deduplicated[keyword] = weight

        if removed_count > 0:
            logger.info(f"关键词去重: 移除了 {removed_count} 个相似关键词")

        return deduplicated

    def _extract_text_from_pdf(self, pdf_path) -> str:
        """
        从 PDF 的前两页提取文本。

        优化：仅提取前两页以减少文本处理量，
        通过快速提取摘要和引言页面的核心概念。

        参数:
            pdf_path: PDF文件的路径

        返回值:
            str: 提取的文本，失败时返回空串
        """
        try:
            with fitz.open(pdf_path) as doc:
                text = ""
                # 只提取前两页
                for i, page in enumerate(doc):
                    if i >= 2:
                        break
                    text += page.get_text()
                return text
        except Exception as e:
            logger.error(f"PDF无法读取 {pdf_path}: {e}")
            return ""

    def _extract_keywords_from_excerpt(self, excerpt: str) -> Dict[str, float]:
        """
        对单篇参考PDF的摘录调用一次 LLM，返回该篇自己的 {关键词: 权重}。

        失败时抛出异常，由调用方决定是否写入缓存（未写入则下次运行重试）。
        """
        system_prompt = f"""你是一名研究助理。基于用户提供的学术论文摘录，提取真正核心的技术概念和术语。

研究背景:
{settings.RESEARCH_CONTEXT if settings.RESEARCH_CONTEXT else "通用学术研究"}

请按重要性分为三个层级提取关键词：
1. 高重要性关键词（最多{settings.REFERENCE_COUNT_HIGH}个）：核心技术、主要算法、关键问题
2. 中重要性关键词（最多{settings.REFERENCE_COUNT_MEDIUM}个）：相关技术、辅助方法、应用领域
3. 低重要性关键词（最多{settings.REFERENCE_COUNT_LOW}个）：周边概念、通用术语、背景知识

**重要原则**：
- 只提取真正核心和重要的关键词，不要为了凑数而提取不重要的内容
- 如果论文在某个层级没有足够核心的内容，宁可少提取或不提取
- 每个层级的关键词数量可以少于最大数量，甚至可以为空
- 关键词质量比数量更重要

要求：
- 关键词应为专业术语或短语
- 关键词应具体且有辨识度，能够代表论文的核心贡献
- 避免过于宽泛的词汇（如"机器学习"、"人工智能"、"优化"等）
- 优先使用英文术语
- 避免提取相似或重复的关键词
- 关键词之间应有明显区别
- 只提取与研究背景高度相关的核心概念

输出格式: 仅输出JSON对象，包含三个数组。如果某个层级没有足够核心的关键词，数组可以为空或包含较少元素。
示例:
{{
  "high_importance": ["quantum error correction", "topological qubits"],
  "medium_importance": ["decoherence"],
  "low_importance": []
}}
"""
        prompt = f"""论文摘录:
{excerpt}"""

        response = call_chat_completion(
            self.client,
            model=settings.CHEAP_LLM.model_name,
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        usage = getattr(response, "usage", None)
        if settings.TOKEN_TRACKING_ENABLED and usage:
            record_llm_token_usage(
                settings.CHEAP_LLM.model_name,
                usage,
                len(system_prompt + prompt) // 4,
            )
        content = response.choices[0].message.content

        # 处理可能的非标准JSON输出包装（去除 markdown 代码块）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        data = json.loads(content)

        def _clean(values, limit):
            return [
                kw
                for kw in list(values)[:limit]
                if isinstance(kw, str) and kw.strip()
            ]

        high = _clean(data.get("high_importance", []), settings.REFERENCE_COUNT_HIGH)
        medium = _clean(data.get("medium_importance", []), settings.REFERENCE_COUNT_MEDIUM)
        low = _clean(data.get("low_importance", []), settings.REFERENCE_COUNT_LOW)

        keywords: Dict[str, float] = {}
        step = float(getattr(settings, "REFERENCE_WEIGHT_STEP", 0.0) or 0.0)
        if step > 0:
            # 按 高→中→低 顺序给每个关键词递减权重（如 1.0/0.9/0.8…），
            # 而不是每档同值；下限为低档权重。
            start = float(settings.REFERENCE_WEIGHT_HIGH)
            floor = float(settings.REFERENCE_WEIGHT_LOW)
            for index, kw in enumerate(high + medium + low):
                keywords[kw] = round(max(floor, start - index * step), 4)
        else:
            for kw in high:
                keywords[kw] = settings.REFERENCE_WEIGHT_HIGH
            for kw in medium:
                keywords[kw] = settings.REFERENCE_WEIGHT_MEDIUM
            for kw in low:
                keywords[kw] = settings.REFERENCE_WEIGHT_LOW
        return keywords

    def generate_weighted_keywords(self) -> Dict[str, float]:
        """
        从参考PDF中提取带权重的关键词字典（支持缓存、增量更新和PDF删除检测）。

        流程:
        1. 加载缓存，检查哪些PDF是新增的、修改的或删除的
        2. 删除已删除PDF对应的关键词
        3. 只对新增PDF使用LLM提取关键词
        4. 合并所有现存PDF的关键词并去重
        5. 根据重要性分配不同权重
        6. 保存缓存供下次使用

        返回值:
            Dict[str, float]: 关键词-权重字典，例如 {"quantum computing": 0.8, "qubit": 0.5}

        降级策略:
            - 如果未启用reference提取，则返回空字典
            - 如果没有找到参考PDF，则返回空字典
            - 如果LLM调用失败，则返回缓存的关键词
        """
        # 检查是否启用reference关键词提取
        if not settings.ENABLE_REFERENCE_EXTRACTION:
            logger.info("Reference关键词提取未启用，跳过。")
            return {}

        pdf_files = list(settings.REF_PDF_DIR.glob("*.pdf"))

        if not pdf_files:
            logger.warning("未找到参考PDF。无法提取reference关键词。")
            return {}

        logger.info(f"发现 {len(pdf_files)} 个参考PDF。正在检查缓存...")

        # 加载缓存
        cache = self._load_cache()
        cached_hashes = cache.get("pdf_hashes", {})
        cached_pdf_keywords = cache.get("pdf_keywords", {})

        # 当前PDF文件名集合
        current_pdf_names = {pdf.name for pdf in pdf_files}
        cached_pdf_names = set(cached_hashes.keys())

        # 检测删除的PDF
        deleted_pdfs = cached_pdf_names - current_pdf_names
        if deleted_pdfs:
            logger.info(f"检测到 {len(deleted_pdfs)} 个PDF已被删除:")
            for pdf_name in deleted_pdfs:
                removed_keywords = cached_pdf_keywords.get(pdf_name, {})
                logger.info(f"  - {pdf_name} (包含 {len(removed_keywords)} 个关键词)")
                # 从缓存中删除
                cached_hashes.pop(pdf_name, None)
                cached_pdf_keywords.pop(pdf_name, None)

        # 检测新增或修改的PDF
        new_pdfs = []
        current_hashes = {}

        for pdf in pdf_files:
            pdf_hash = self._calculate_pdf_hash(pdf)
            current_hashes[pdf.name] = pdf_hash

            # 如果PDF不在缓存中，或哈希值变化了，则视为新PDF
            if pdf.name not in cached_hashes or cached_hashes[pdf.name] != pdf_hash:
                new_pdfs.append(pdf)

        # 如果没有新增PDF且没有删除PDF，直接返回缓存
        if not new_pdfs and not deleted_pdfs:
            logger.info("所有PDF均已缓存，无需重新处理。")
            # 从所有PDF的关键词合并生成最终关键词
            merged_keywords = {}
            for pdf_name in current_pdf_names:
                pdf_keywords = cached_pdf_keywords.get(pdf_name, {})
                for kw, weight in pdf_keywords.items():
                    if kw in merged_keywords:
                        merged_keywords[kw] = max(merged_keywords[kw], weight)
                    else:
                        merged_keywords[kw] = weight
            # 与新增路径保持一致：缓存路径同样去重。
            merged_keywords = self._deduplicate_keywords(merged_keywords)
            logger.info(f"去重后关键词总数: {len(merged_keywords)} 个")
            return merged_keywords

        if deleted_pdfs:
            logger.info(f"由于PDF删除，需要重新生成关键词集合")

        if new_pdfs:
            logger.info(f"检测到 {len(new_pdfs)} 个新增/修改的PDF，需要提取关键词")

            # 最多分析 5 个新 PDF 以节省时间和成本，其余留待后续运行。
            # 逐篇提取：每篇各自一次 LLM 调用，得到属于该篇的关键词。
            attempted = new_pdfs[:5]
            for pdf in attempted:
                excerpt = self._extract_text_from_pdf(pdf)[:2000]
                if not excerpt.strip():
                    logger.warning(f"  {pdf.name} 未提取到文本，跳过（下次重试）")
                    continue
                logger.info(f"  提取文本: {pdf.name}")
                try:
                    pdf_keywords = self._extract_keywords_from_excerpt(excerpt)
                except Exception as e:
                    self._record_llm_health(False, e)
                    logger.error(f"从 {pdf.name} 提取关键词失败（下次重试）: {e}")
                    continue
                # 只为真正提取成功的 PDF 写入缓存，失败的留给下次重试。
                cached_pdf_keywords[pdf.name] = pdf_keywords
                self._record_llm_health(True)
                logger.info(f"  从 {pdf.name} 提取了 {len(pdf_keywords)} 个关键词")

            processed = sum(1 for pdf in attempted if pdf.name in cached_pdf_keywords)
            remaining = len(new_pdfs) - processed
            if remaining > 0:
                logger.info(f"  本次处理 {processed} 个，仍有 {remaining} 个留待后续运行")

        # 从所有现存PDF的关键词合并生成最终关键词
        merged_keywords = {}
        for pdf_name in current_pdf_names:
            pdf_keywords = cached_pdf_keywords.get(pdf_name, {})
            for kw, weight in pdf_keywords.items():
                # 如果关键词已存在，保留更高的权重
                if kw in merged_keywords:
                    merged_keywords[kw] = max(merged_keywords[kw], weight)
                else:
                    merged_keywords[kw] = weight

        logger.info(f"合并后关键词总数: {len(merged_keywords)} 个")

        # 去除相似关键词
        deduplicated_keywords = self._deduplicate_keywords(merged_keywords)
        logger.info(f"去重后关键词总数: {len(deduplicated_keywords)} 个")

        # 保存缓存
        cache_data = {
            # 只为真正提取过关键词的 PDF 记录哈希：单次最多分析 5 个新 PDF，
            # 未处理的 PDF 绝不能写入哈希，否则下次会被误判为“已处理”而永久跳过。
            "pdf_hashes": {
                name: digest
                for name, digest in current_hashes.items()
                if name in cached_pdf_keywords
            },
            "pdf_keywords": cached_pdf_keywords,
            "keywords": deduplicated_keywords,  # 保留用于向后兼容
        }
        self._save_cache(cache_data)

        return deduplicated_keywords

    def _trim_reference_keywords(
        self, keywords: Dict[str, float]
    ) -> Dict[str, float]:
        """Apply the configured weight floor and top-N cap to reference keywords.

        Trimming happens at merge time only; the per-PDF cache keeps every
        extracted term, so relaxing the limits later restores the terms
        without another LLM call.
        """
        if not keywords:
            return keywords
        min_weight = float(
            getattr(settings, "REFERENCE_KEYWORD_MIN_WEIGHT", 0.0) or 0.0
        )
        max_count = int(getattr(settings, "REFERENCE_KEYWORD_MAX_COUNT", 0) or 0)
        trimmed = keywords
        if min_weight > 0:
            trimmed = {
                kw: weight for kw, weight in trimmed.items() if weight >= min_weight
            }
        if max_count > 0 and len(trimmed) > max_count:
            trimmed = dict(
                sorted(trimmed.items(), key=lambda item: (-item[1], item[0]))[:max_count]
            )
        if len(trimmed) != len(keywords):
            logger.info(
                "参考关键词裁剪: %d -> %d（权重阈值 %.2f，数量上限 %d）",
                len(keywords),
                len(trimmed),
                min_weight,
                max_count,
            )
        return trimmed

    def get_all_keywords(self) -> Dict[str, float]:
        """
        获取所有关键词（主要关键词 + reference关键词）的合并字典。

        返回值:
            Dict[str, float]: 合并后的关键词-权重字典
        """
        # 从配置获取主要关键词
        all_keywords = settings.get_merged_keywords()

        # 关闭时连缓存读取/合并都不进行。这样旧的关键词缓存仍可在以后
        # 重新启用时复用，但不会影响当前这次研究的评分或排序。
        if settings.ENABLE_REFERENCE_EXTRACTION:
            reference_keywords = self.generate_weighted_keywords()
        else:
            reference_keywords = {}
            logger.info("Reference关键词提取已关闭；仅使用主要关键词。")

        reference_keywords = self._trim_reference_keywords(reference_keywords)

        # 合并（主要关键词优先，不会被覆盖）
        negative_keys = set()
        if settings.normalized_score_strategy() == "weighted_keyword_with_penalties_v1":
            negative_keys = {
                keyword.casefold() for keyword in settings.NEGATIVE_KEYWORDS
            }
        for kw, weight in reference_keywords.items():
            # A reference PDF can yield a configured penalty term.  Do not
            # score the same term as both positive and negative evidence.
            if kw.casefold() not in negative_keys and kw not in all_keywords:
                all_keywords[kw] = weight

        logger.info(f"关键词总数: {len(all_keywords)} 个")
        logger.info(f"总权重: {sum(all_keywords.values()):.2f}")

        return all_keywords
