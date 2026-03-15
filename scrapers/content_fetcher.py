# infra/content_fetcher.py
# 正文补全，只处理需要在 process 阶段抓取正文的来源
# GitHub README 已在 scrape 阶段获取，不在此处处理

import threading
import requests
import trafilatura
from .models import RawItem

FETCH_FULLTEXT_TAGS = {"official_ai", "ai_research"}

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

# trafilatura 底层 lxml 在多线程下不安全，加锁保护
_trafilatura_lock = threading.Lock()


def _should_skip(url: str) -> bool:
    return any(domain in url for domain in SKIP_DOMAINS)


def _fetch_webpage(url: str) -> str:
    """抓取网页正文，不截断"""
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return ""
        with _trafilatura_lock:
            content = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
        return content or ""
    except Exception:
        return ""


def enrich_body_text(item: RawItem) -> str:
    """补充正文内容"""
    if _should_skip(item.original_url):
        return item.body_text or ""

    # GitHub repo：已在 scrape 阶段获取 README，直接返回
    if item.content_type == "repo":
        return item.body_text or ""

    # AI 官方博客 / 学术来源：抓全文
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
