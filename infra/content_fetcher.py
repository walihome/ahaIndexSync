# infra/content_fetcher.py
# 正文补全，根据来源类型分策略抓取

import os
import requests
import trafilatura
from .models import RawItem

GITHUB_TOKEN = os.getenv("GH_MODELS_TOKEN")

# 需要抓全文的 source_tag
FETCH_FULLTEXT_TAGS = {"official_ai", "ai_research"}

# 反爬或内容价值低，跳过
SKIP_DOMAINS = {
    "twitter.com", "x.com",
    "medium.com",
    "zhihu.com",
    "v2ex.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _should_skip(url: str) -> bool:
    return any(domain in url for domain in SKIP_DOMAINS)


def _fetch_webpage(url: str, max_chars: int = 2000) -> str:
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            return ""
        content = trafilatura.extract(
            resp.text,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        return content[:max_chars] if content else ""
    except Exception:
        return ""


def _fetch_github_readme(url: str, max_chars: int = 2000) -> str:
    try:
        parts = url.rstrip("/").split("/")
        if len(parts) < 5:
            return ""
        owner, repo = parts[-2], parts[-1]
        headers = {"Accept": "application/vnd.github.raw"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            headers=headers,
            timeout=10,
        )
        return resp.text[:max_chars] if resp.status_code == 200 else ""
    except Exception:
        return ""


def enrich_body_text(item: RawItem) -> str:
    """补充正文内容，已有足够内容则直接返回"""
    if item.body_text and len(item.body_text) >= 200:
        return item.body_text

    if _should_skip(item.original_url):
        return item.body_text or ""

    # GitHub repo：抓 README
    if item.content_type == "repo" and "github.com" in item.original_url:
        readme = _fetch_github_readme(item.original_url)
        if readme:
            print(f"  📄 README: {item.title[:40]}")
            return readme
        return item.body_text or ""

    # AI 官方博客 / 学术来源：抓文章正文
    if item.extra.get("source_tag") in FETCH_FULLTEXT_TAGS:
        content = _fetch_webpage(item.original_url)
        if content:
            print(f"  📄 正文: {item.title[:40]}")
            return content
        return item.body_text or ""

    # HackerNews：抓原文链接正文
    if item.source_name == "HackerNews" and "news.ycombinator.com" not in item.original_url:
        content = _fetch_webpage(item.original_url)
        if content:
            print(f"  📄 HN原文: {item.title[:40]}")
            return content
        return item.body_text or ""

    return item.body_text or ""