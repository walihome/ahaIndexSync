# enrichers/github_ecosystem.py
"""
GitHub Ecosystem Enricher
-------------------------
触发条件：content_type == 'repo' 且 URL 能解析出 GitHub repo

流程：
  1. 读取 item.extra 中已有的 repo 信息（topics/stars/readme 摘要）
     如缺失则调用 GET /repos/:owner/:repo 补全
  2. 用 topics 构造 GitHub Search API 查询，拿 Top N 同赛道 repo
  3. LLM 分析 → competitors / ecosystem_position / maturity / unique_value
  4. competitors 列表中每个 repo → subject 候选（project 类型，全部自动创建）

环境变量：GH_MODELS_TOKEN（与 github_search scraper 共用）
"""

from __future__ import annotations

import json
import os
import time

import requests

from enrichers.base import BaseEnricher, EnrichmentResult, SubjectCandidate
from enrichers.registry import register
from enrichers._utils import github_slug, primary_github_repo_for_item, parse_github_repo
from infra.llm import call_llm

GITHUB_API = "https://api.github.com"


def _gh_headers() -> dict:
    token = os.getenv("GH_MODELS_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AmazingIndex-Enricher/1.0",
    }
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


@register("github_ecosystem")
class GithubEcosystemEnricher(BaseEnricher):
    enrichment_type = "ecosystem"

    def applies_to(self, item: dict) -> bool:
        if item.get("content_type") != "repo":
            return False
        return primary_github_repo_for_item(item) is not None

    def run(self, item: dict) -> EnrichmentResult | None:
        if not os.getenv("GH_MODELS_TOKEN"):
            raise RuntimeError("GH_MODELS_TOKEN 未配置，github_ecosystem 无法运行")

        repo_tuple = primary_github_repo_for_item(item)
        if not repo_tuple:
            return None
        owner, repo = repo_tuple
        full_name = f"{owner}/{repo}"

        repo_info = self._resolve_repo_info(item, owner, repo)
        if not repo_info:
            return None

        topics = repo_info.get("topics") or []
        candidates = self._search_similar(topics, full_name)

        readme_excerpt = (repo_info.get("readme_excerpt") or "")[:800]
        if not readme_excerpt:
            readme_excerpt = (item.get("summary") or "")[:500]

        candidates_text = "\n".join(
            f"- {c['full_name']} (⭐{c['stargazers_count']}) — {(c.get('description') or '')[:120]}"
            for c in candidates
        ) or "（未搜索到相关 repo）"

        prompt_cfg = self.config.get_prompt("enrich_github_ecosystem")
        if not prompt_cfg or not self.api_key:
            return EnrichmentResult(
                enrichment_type=self.enrichment_type,
                enricher_name=self.name,
                data={
                    "repo_full_name": full_name,
                    "topics": topics,
                    "stars": repo_info.get("stargazers_count"),
                    "candidates_raw": [{"name": c["full_name"], "stars": c["stargazers_count"]} for c in candidates],
                    "llm_skipped": True,
                },
                subject_candidates=[],
            )

        prompt = prompt_cfg.render(
            repo_full_name=full_name,
            stars=str(repo_info.get("stargazers_count") or 0),
            topics=", ".join(topics) if topics else "（无）",
            description=repo_info.get("description") or "",
            readme_excerpt=readme_excerpt,
            candidates_text=candidates_text,
        )

        ai = call_llm(prompt, prompt_cfg, system_prompt="You only output JSON.", api_key=self.api_key)
        if not ai:
            return None

        competitors = ai.get("competitors") or []
        subject_candidates: list[SubjectCandidate] = []
        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            name = (comp.get("name") or "").strip().strip("/")
            if not name or "/" not in name:
                continue
            parts = name.split("/")
            c_owner, c_repo = parts[0], parts[1]
            if not c_owner or not c_repo:
                continue
            slug = github_slug(c_owner, c_repo)
            subject_candidates.append(SubjectCandidate(
                slug=slug,
                type="project",
                display_name=f"{c_owner}/{c_repo}",
                description=comp.get("comparison") or f"{full_name} 的竞品",
                metadata={
                    "repo_full_name": f"{c_owner}/{c_repo}",
                    "stars": comp.get("stars"),
                },
                role="mentioned",
                context=f"{full_name} 的生态竞品",
            ))

        data = {
            "repo_full_name": full_name,
            "stars": repo_info.get("stargazers_count"),
            "topics": topics,
            "competitors": competitors,
            "ecosystem_position": ai.get("ecosystem_position"),
            "maturity": ai.get("maturity"),
            "unique_value": ai.get("unique_value"),
        }

        time.sleep(prompt_cfg.request_interval)

        return EnrichmentResult(
            enrichment_type=self.enrichment_type,
            enricher_name=self.name,
            data=data,
            subject_candidates=subject_candidates,
        )

    def _resolve_repo_info(self, item: dict, owner: str, repo: str) -> dict | None:
        extra = item.get("extra") or {}
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except Exception:
                extra = {}

        info: dict = {}
        if isinstance(extra, dict):
            info["topics"] = extra.get("topics") or []
            info["stargazers_count"] = extra.get("stars") or extra.get("stargazers_count")
            info["description"] = extra.get("description")
            info["readme_excerpt"] = extra.get("readme_excerpt") or extra.get("readme")

        if info.get("topics") and info.get("stargazers_count") is not None:
            return info

        try:
            resp = requests.get(
                f"{GITHUB_API}/repos/{owner}/{repo}",
                headers=_gh_headers(),
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"  ⚠️ [gh_ecosystem] 获取 repo 元信息失败 {owner}/{repo} HTTP {resp.status_code}")
                return info if info.get("topics") or info.get("stargazers_count") is not None else None
            data = resp.json()
            info["topics"] = info.get("topics") or data.get("topics") or []
            info["stargazers_count"] = info.get("stargazers_count") or data.get("stargazers_count")
            info["description"] = info.get("description") or data.get("description")
            return info
        except Exception as e:
            print(f"  ⚠️ [gh_ecosystem] repo 元信息异常 {owner}/{repo}: {e}")
            return info if info else None

    def _search_similar(self, topics: list[str], exclude_full_name: str) -> list[dict]:
        if not topics:
            return []
        top_topics = topics[:3]
        query_parts = [f"topic:{t}" for t in top_topics]
        query = " ".join(query_parts)
        try:
            resp = requests.get(
                f"{GITHUB_API}/search/repositories",
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                headers=_gh_headers(),
                timeout=20,
            )
            if resp.status_code != 200:
                print(f"  ⚠️ [gh_ecosystem] search 失败 HTTP {resp.status_code}")
                return []
            items = resp.json().get("items") or []
            return [
                {
                    "full_name": it.get("full_name"),
                    "stargazers_count": it.get("stargazers_count") or 0,
                    "description": it.get("description") or "",
                    "html_url": it.get("html_url"),
                }
                for it in items
                if it.get("full_name") and it["full_name"].lower() != exclude_full_name.lower()
            ][:8]
        except Exception as e:
            print(f"  ⚠️ [gh_ecosystem] search 异常: {e}")
            return []
