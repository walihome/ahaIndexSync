# enrichers/web_search.py
"""
Web Search Enricher
-------------------
触发条件：content_type 为 article 或 hf_papers

流程：
  1. 从标题构造搜索关键词
  2. Tavily Search API 获取相关结果（max_results=5）
  3. LLM 从结果中提取 related_articles 和 key_discussions

环境变量：TAVILY_API_KEY
"""

from __future__ import annotations

import os
import time

from enrichers.base import BaseEnricher, EnrichmentResult
from enrichers.registry import register
from infra.llm import call_llm


def _tavily_search(query: str, api_key: str, max_results: int = 5) -> list[dict]:
    """调用 Tavily Search API，返回结果列表。"""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query=query, max_results=max_results, search_depth="basic")
        return resp.get("results", [])
    except ImportError:
        # fallback: 用 httpx 直接调 API
        import httpx
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": api_key, "query": query, "max_results": max_results, "search_depth": "basic"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])


@register("web_search")
class WebSearchEnricher(BaseEnricher):
    enrichment_type = "web_context"

    def __init__(self, sb, config, api_key="", table_suffix=""):
        super().__init__(sb, config, api_key, table_suffix)
        self.tavily_key = os.getenv("TAVILY_API_KEY", "")

    def applies_to(self, item: dict) -> bool:
        ct = item.get("content_type", "")
        return ct in ("article", "hf_papers")

    def run(self, item: dict) -> EnrichmentResult | None:
        if not self.tavily_key:
            print("  ⚠️ [web_search] TAVILY_API_KEY 未设置，跳过")
            return None

        title = item.get("processed_title") or item.get("raw_title") or ""
        if not title:
            return None

        # 构造搜索 query
        extra = item.get("extra") or {}
        if isinstance(extra, str):
            import json
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}

        query = title
        arxiv_id = extra.get("arxiv_id") or extra.get("paper_id")
        if arxiv_id:
            query = f"{title} arxiv {arxiv_id}"

        # Tavily 搜索
        try:
            results = _tavily_search(query, self.tavily_key, max_results=5)
        except Exception as e:
            print(f"  ⚠️ [web_search] Tavily 搜索失败: {e}")
            return None

        if not results:
            return None

        # 格式化搜索结果供 LLM 分析
        results_text = "\n\n".join(
            f"[{i+1}] {r.get('title', '')}\nURL: {r.get('url', '')}\n{r.get('content', '')[:300]}"
            for i, r in enumerate(results)
        )

        prompt_cfg = self.config.get_prompt("enrich_web_search")
        if not prompt_cfg or not self.api_key:
            # 无 LLM：直接返回原始搜索结果
            return EnrichmentResult(
                enrichment_type=self.enrichment_type,
                enricher_name=self.name,
                data={
                    "search_query": query,
                    "related_articles": [
                        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("content") or "")[:200]}
                        for r in results[:5]
                    ],
                    "key_discussions": [],
                    "llm_skipped": True,
                },
            )

        prompt = prompt_cfg.render(
            title=title,
            source_name=item.get("source_name", ""),
            results_text=results_text,
        )

        ai = call_llm(prompt, prompt_cfg, system_prompt="You only output JSON.", api_key=self.api_key)
        if not ai:
            return None

        time.sleep(prompt_cfg.request_interval)

        return EnrichmentResult(
            enrichment_type=self.enrichment_type,
            enricher_name=self.name,
            data={
                "search_query": query,
                "related_articles": ai.get("related_articles") or [],
                "key_discussions": ai.get("key_discussions") or [],
            },
        )
