# enrichers/content_quality.py
"""
Content Quality Enricher — 纯规则，零 API 调用。

基于正文长度、信息密度、完整性等维度给 0-1 分。
enrichment_level = 1 (L1)
"""

from __future__ import annotations

import re

from enrichers.base import BaseEnricher, EnrichmentResult
from enrichers.registry import register


def _length_score(text: str) -> float:
    n = len(text)
    if n < 100:
        return 0.2
    if n < 500:
        return 0.5
    if n < 2000:
        return 0.8
    return 1.0


def _info_density(text: str) -> float:
    """URLs、代码块、数字占比 → 信息密度。"""
    if not text:
        return 0.0
    total = len(text)
    urls = len(re.findall(r'https?://\S+', text))
    code_blocks = len(re.findall(r'```', text)) // 2
    numbers = len(re.findall(r'\b\d[\d,.]*\b', text))
    # 每个信号给固定分，cap 在 1.0
    score = min(1.0, (urls * 0.1 + code_blocks * 0.15 + numbers * 0.02))
    return round(score, 2)


def _language_ratio(text: str) -> float:
    """纯中文或纯英文 → 1.0，混合 → 0.7。"""
    if not text:
        return 0.0
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    total = cjk + latin
    if total == 0:
        return 0.5
    dominant = max(cjk, latin) / total
    return 1.0 if dominant > 0.85 else 0.7


@register("content_quality")
class ContentQualityEnricher(BaseEnricher):
    enrichment_type = "content_quality"

    def applies_to(self, item: dict) -> bool:
        return True

    def run(self, item: dict) -> EnrichmentResult | None:
        body = item.get("body_text") or ""
        extra = item.get("extra") or {}
        if isinstance(extra, str):
            import json
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}

        length = _length_score(body)
        density = _info_density(body)
        language = _language_ratio(body)

        has_readme = 1.0 if (extra.get("readme_images") or len(body) > 500) else 0.0
        has_images = 1.0 if extra.get("readme_images") else 0.0

        overall = round(length * 0.4 + density * 0.2 + language * 0.15 + has_readme * 0.15 + has_images * 0.1, 2)

        data = {
            "length_score": length,
            "info_density": density,
            "language_ratio": language,
            "has_readme": has_readme,
            "has_images": has_images,
            "overall_score": overall,
            "body_length": len(body),
        }

        return EnrichmentResult(
            enrichment_type=self.enrichment_type,
            enricher_name=self.name,
            data=data,
            subject_candidates=[],
        )
