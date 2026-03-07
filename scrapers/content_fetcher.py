# scrapers/content_fetcher.py
#
# 按来源类型分策略抓取正文内容
# - official_ai / ai_research：抓文章正文
# - repo：抓 GitHub README
# - HackerNews：抓原文链接正文
# - 其他：跳过，保持现有 body_text

import os
import requests
import trafilatura
from .base import RawItem

GITHUB_TOKEN = os.getenv("GH_MODELS_TOKEN")

# 需要抓全文的 source_tag
FETCH_FULLTEXT_TAGS = {"official_ai", "ai_research"}

# 不值得抓正文的域名（反爬或内容价值低）
SKIP_DOMAINS = {
    "twitter.com", "x.com",
    "medium.com",          # 登录墙
    "zhihu.com",           # 反爬
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
    for domain in SKIP_DOMAINS:
        if domain in url:
            return True
    return False


def _fetch_webpage(url: str, max_chars: int = 2000) -> str:
    """抓网页正文，用 trafilatura 提取干净文本"""
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
    """通过 GitHub API 抓 README，比抓网页更稳定"""
    # url 格式: https://github.com/owner/repo
    try:
        parts = url.rstrip("/").split("/")
        if len(parts) < 5:
            return ""
        owner, repo = parts[-2], parts[-1]

        headers = {"Accept": "application/vnd.github.raw"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"

        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""

        # raw 格式直接返回 markdown 文本
        return resp.text[:max_chars]
    except Exception:
        return ""


def enrich_body_text(item: RawItem) -> str:
    """
    根据来源策略补充正文内容
    返回补充后的 body_text，原有内容已够用则直接返回
    """
    # 已有足够内容，不重复抓
    if item.body_text and len(item.body_text) >= 200:
        return item.body_text

    source_tag = item.extra.get("source_tag", "")
    url = item.original_url

    if _should_skip(url):
        return item.body_text or ""

    # GitHub repo：抓 README
    if item.content_type == "repo" and "github.com" in url:
        readme = _fetch_github_readme(url)
        if readme:
            print(f"  📄 README 已抓取: {item.title[:40]}")
            return readme
        return item.body_text or ""

    # AI 官方博客 / 学术来源：抓文章正文
    if source_tag in FETCH_FULLTEXT_TAGS:
        content = _fetch_webpage(url)
        if content:
            print(f"  📄 正文已抓取: {item.title[:40]}")
            return content
        return item.body_text or ""

    # HackerNews：原文链接抓正文（HN 本身没内容）
    if item.source_name == "HackerNews" and "news.ycombinator.com" not in url:
        content = _fetch_webpage(url)
        if content:
            print(f"  📄 HN 原文已抓取: {item.title[:40]}")
            return content
        return item.body_text or ""

    return item.body_text or ""
