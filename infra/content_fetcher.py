# infra/content_fetcher.py
# 正文补全，根据来源类型分策略抓取

import os
import re
import threading
import requests
import trafilatura
from .models import RawItem

_trafilatura_lock = threading.Lock()

GITHUB_TOKEN = os.getenv("GH_MODELS_TOKEN")

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


def _should_skip(url: str) -> bool:
    return any(domain in url for domain in SKIP_DOMAINS)


def _clean_readme(text: str) -> str:
    """去掉代码块、徽章、安装命令等低价值内容，保留项目描述和功能说明"""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'^\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


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


def _fetch_github_readme(url: str) -> str:
    """抓取 GitHub README 全文并清理"""
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
        if resp.status_code != 200:
            return ""
        return _clean_readme(resp.text)
    except Exception:
        return ""


def _fetch_github_languages(url: str) -> str:
    """获取 GitHub repo 的语言分布，拼成一行文字"""
    try:
        parts = url.rstrip("/").split("/")
        if len(parts) < 5:
            return ""
        owner, repo = parts[-2], parts[-1]
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"token {GITHUB_TOKEN}"
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/languages",
            headers=headers, timeout=10,
        )
        if resp.status_code != 200:
            return ""
        langs = list(resp.json().keys())[:5]
        return f"主要语言：{', '.join(langs)}\n\n" if langs else ""
    except Exception:
        return ""


def enrich_body_text(item: RawItem) -> str:
    """补充正文内容，已有足够内容则直接返回"""
    if _should_skip(item.original_url):
        return item.body_text or ""

    # GitHub repo：抓完整 README + 语言信息
    if item.content_type == "repo" and "github.com" in item.original_url:
        readme = _fetch_github_readme(item.original_url)
        if readme:
            lang_prefix = _fetch_github_languages(item.original_url)
            print(f"  📄 README: {item.title[:40]}")
            return lang_prefix + readme
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
