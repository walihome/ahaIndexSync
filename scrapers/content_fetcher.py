# infra/content_fetcher.py
# 正文补全，只处理需要在 process 阶段抓取正文的来源
# GitHub README 和 HackerNews 正文已在 scrape 阶段获取

import threading
import requests
import trafilatura
from .models import RawItem

# AI 官方博客和学术来源，process 阶段补全全文
FETCH_FULLTEXT_TAGS = {"official_ai", "ai_research"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_trafilatura_lock = threading.Lock()


def _fetch_webpage(url: str) -> str:
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
    """
    process 阶段补全正文。
    - repo：scrape 阶段已抓 README，直接返回
    - HackerNews：scrape 阶段已并发抓正文，直接返回
    - official_ai / ai_research：此处抓全文
    - 其他：直接返回已有内容
    """
    # 已在 scrape 阶段获取
    if item.content_type in ("repo", "tweet"):
        return item.body_text or ""

    if item.source_name == "HackerNews":
        return item.body_text or ""

    # AI 官方博客 / 学术来源：抓全文
    if item.extra.get("source_tag") in FETCH_FULLTEXT_TAGS:
        content = _fetch_webpage(item.original_url)
        if content:
            print(f"  📄 正文: {item.title[:40]}")
            return content
        return item.body_text or ""

    return item.body_text or ""
