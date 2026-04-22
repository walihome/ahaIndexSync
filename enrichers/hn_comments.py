# enrichers/hn_comments.py
"""
HN Comments Enricher
--------------------
触发条件：source_name == 'HackerNews' 且 raw_metrics.hn_id 存在

流程：
  1. Algolia HN API 一次调用 → 完整评论树（含 points）
  2. 展平评论 → 按 points 排序取 Top 20
  3. LLM 分析 → sentiment / core_debate / top_insights / alternatives / alternative_repos / valuable_links
  4. alternative_repos 中含 GitHub 链接的 → subject 候选（project 类型）
"""

from __future__ import annotations

import json
import time

import requests

from enrichers.base import BaseEnricher, EnrichmentResult, SubjectCandidate
from enrichers.registry import register
from enrichers._utils import github_slug
from infra.llm import call_llm

ALGOLIA_ITEM_URL = "https://hn.algolia.com/api/v1/items/{hn_id}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AmazingIndexBot/1.0; +https://amazingindex.com)"
    )
}


def _flatten_comments(node: dict, out: list[dict], depth: int = 0, max_depth: int = 3):
    """递归展平评论树。忽略已删除/死亡评论。"""
    if not node:
        return
    if node.get("type") == "comment":
        text = (node.get("text") or "").strip()
        if text and not node.get("dead") and not node.get("deleted"):
            out.append({
                "points": node.get("points") or 0,
                "author": node.get("author") or "",
                "text": text,
                "depth": depth,
            })
    if depth >= max_depth:
        return
    for child in node.get("children") or []:
        _flatten_comments(child, out, depth + 1, max_depth)


def _strip_html(text: str) -> str:
    import re
    text = re.sub(r"<p>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&#x27;", "'").replace("&quot;", '"').replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&")
    return text.strip()


@register("hn_comments")
class HNCommentsEnricher(BaseEnricher):
    enrichment_type = "comments"

    def applies_to(self, item: dict) -> bool:
        if item.get("source_name") != "HackerNews":
            return False
        metrics = item.get("raw_metrics") or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        return bool(metrics.get("hn_id"))

    def run(self, item: dict) -> EnrichmentResult | None:
        metrics = item.get("raw_metrics") or {}
        if isinstance(metrics, str):
            try:
                metrics = json.loads(metrics)
            except Exception:
                metrics = {}
        hn_id = metrics.get("hn_id")
        if not hn_id:
            return None

        try:
            resp = requests.get(ALGOLIA_ITEM_URL.format(hn_id=hn_id), timeout=15, headers=HEADERS)
            resp.raise_for_status()
            tree = resp.json()
        except Exception as e:
            print(f"  ⚠️ [hn_comments] Algolia 获取失败 hn_id={hn_id}: {e}")
            return None

        comments: list[dict] = []
        for child in tree.get("children") or []:
            _flatten_comments(child, comments)

        if not comments:
            return None

        comments.sort(key=lambda c: c.get("points") or 0, reverse=True)
        top = comments[:20]

        comments_text = "\n\n".join(
            f"[{c['points']}] {c['author']}: {_strip_html(c['text'])[:400]}"
            for c in top
        )

        prompt_cfg = self.config.get_prompt("enrich_hn_comments")
        if not prompt_cfg or not self.api_key:
            return EnrichmentResult(
                enrichment_type=self.enrichment_type,
                enricher_name=self.name,
                data={
                    "hn_id": hn_id,
                    "comment_count": len(comments),
                    "top_comments_raw": [
                        {"points": c["points"], "author": c["author"], "text": _strip_html(c["text"])[:300]}
                        for c in top[:5]
                    ],
                    "llm_skipped": True,
                },
                subject_candidates=[],
            )

        prompt = prompt_cfg.render(
            title=item.get("processed_title") or item.get("raw_title") or "",
            summary=item.get("summary") or "",
            comments_text=comments_text,
        )

        ai = call_llm(prompt, prompt_cfg, system_prompt="You only output JSON.", api_key=self.api_key)
        if not ai:
            return None

        alternative_repos = ai.get("alternative_repos") or []
        subject_candidates: list[SubjectCandidate] = []
        seen_slugs: set[str] = set()
        for full in alternative_repos:
            if not isinstance(full, str) or "/" not in full:
                continue
            full = full.strip().strip("/")
            parts = full.split("/")
            if len(parts) < 2:
                continue
            owner, repo = parts[0], parts[1]
            if not owner or not repo:
                continue
            slug = github_slug(owner, repo)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            subject_candidates.append(SubjectCandidate(
                slug=slug,
                type="project",
                display_name=f"{owner}/{repo}",
                description=f"HN 评论中提到的替代方案（{item.get('processed_title', '')[:30]}）",
                metadata={"repo_full_name": f"{owner}/{repo}"},
                role="mentioned",
                context="HN 评论提及",
            ))

        data = {
            "hn_id": hn_id,
            "comment_count": len(comments),
            "analyzed_top_n": len(top),
            "sentiment": ai.get("sentiment"),
            "core_debate": ai.get("core_debate"),
            "top_insights": ai.get("top_insights") or [],
            "alternatives": ai.get("alternatives") or [],
            "alternative_repos": alternative_repos,
            "valuable_links": ai.get("valuable_links") or [],
        }

        time.sleep(prompt_cfg.request_interval)

        return EnrichmentResult(
            enrichment_type=self.enrichment_type,
            enricher_name=self.name,
            data=data,
            subject_candidates=subject_candidates,
        )
