# infra/content_fetcher.py
# 正文补全：Jina Reader 为主，trafilatura 为 fallback
# 统一管理所有正文抓取逻辑（网页、GitHub README、RSS）

from __future__ import annotations

import hashlib
import os
import re
import threading
from dataclasses import dataclass

import requests
import trafilatura

_trafilatura_lock = threading.Lock()

# ── 内存缓存（同一次 pipeline run 内不重复调用） ──────────────
_jina_cache: dict[str, str] = {}
_cache_lock = threading.Lock()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


@dataclass
class FetchResult:
    content: str
    source: str  # 'jina', 'trafilatura', 'github_readme', 'rss', 'scraper', 'empty'
    quality: float  # 0-1


# ── Jina Reader ────────────────────────────────────────────────

def _fetch_jina(url: str) -> str:
    """通过 Jina Reader 获取网页正文（markdown 格式）。"""
    cache_key = hashlib.md5(url.encode()).hexdigest()
    with _cache_lock:
        if cache_key in _jina_cache:
            return _jina_cache[cache_key]

    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/markdown"}
    api_key = os.getenv("JINA_API_KEY", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        resp = requests.get(jina_url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return ""
        text = resp.text.strip()
        # Jina 返回的可能包含 URL header，去掉
        if text.startswith("Title:"):
            lines = text.split("\n", 3)
            if len(lines) >= 4:
                text = lines[3]
        with _cache_lock:
            _jina_cache[cache_key] = text
        return text
    except Exception:
        return ""


# ── trafilatura（fallback） ────────────────────────────────────

def _fetch_trafilatura(url: str) -> str:
    """trafilatura 本地解析 HTML 提取正文。"""
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


# ── GitHub README（统一入口） ──────────────────────────────────

def _clean_readme(text: str) -> str:
    """清理 README：去掉代码块、badge、图片、HTML 标签。"""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'^\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _fetch_readme_raw(owner: str, repo: str) -> str:
    """通过 GitHub API 获取 README 原始内容。"""
    token = os.getenv("GH_MODELS_TOKEN", "")
    try:
        headers = {"Accept": "application/vnd.github.raw"}
        if token:
            headers["Authorization"] = f"token {token}"
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/readme",
            headers=headers, timeout=10,
        )
        if resp.status_code != 200:
            return ""
        return resp.text
    except Exception:
        return ""


def _fetch_languages(owner: str, repo: str) -> str:
    """获取 GitHub repo 的主要语言。"""
    token = os.getenv("GH_MODELS_TOKEN", "")
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"token {token}"
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


def _fetch_github_readme(owner: str, repo: str) -> str:
    """获取 GitHub README + 语言信息，返回清理后的文本。"""
    raw = _fetch_readme_raw(owner, repo)
    if not raw:
        return ""
    lang_prefix = _fetch_languages(owner, repo)
    cleaned = _clean_readme(raw)
    return lang_prefix + cleaned


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    """从 URL 解析 GitHub owner/repo。"""
    if "github.com" not in url:
        return None
    parts = url.rstrip("/").split("/")
    if len(parts) < 5:
        return None
    return parts[-2], parts[-1]


# ── 正文质量评分 ───────────────────────────────────────────────

def _estimate_quality(text: str) -> float:
    """基于正文特征估算质量分（0-1），纯规则，不调 LLM。"""
    if not text:
        return 0.0

    length = len(text)

    # 长度分
    if length < 50:
        length_score = 0.1
    elif length < 100:
        length_score = 0.2
    elif length < 300:
        length_score = 0.4
    elif length < 500:
        length_score = 0.5
    elif length < 1000:
        length_score = 0.7
    elif length < 2000:
        length_score = 0.8
    else:
        length_score = 1.0

    # 信息密度：数字、URL、代码片段占比
    numbers = len(re.findall(r'\d+', text))
    urls = len(re.findall(r'https?://', text))
    code_blocks = len(re.findall(r'```', text))
    density = min(1.0, (numbers + urls * 2 + code_blocks * 3) / max(1, length / 50))

    # 句子完整性：有句号/换行的文本更有价值
    sentences = len(re.findall(r'[。！？.!?\n]', text))
    completeness = min(1.0, sentences / max(1, length / 100))

    return round(length_score * 0.5 + density * 0.25 + completeness * 0.25, 2)


# ── 主入口 ─────────────────────────────────────────────────────

def enrich_body_text(
    title: str,
    original_url: str,
    source_name: str,
    content_type: str,
    body_text: str,
    extra: dict,
    skip_domains: set[str] | None = None,
    fulltext_tags: set[str] | None = None,
) -> FetchResult:
    """
    正文补全主入口。

    策略：
      1. skip_domain → 直接返回现有 body_text
      2. GitHub repo → GitHub API README
      3. 其他网页 → Jina Reader → trafilatura fallback
      4. 无正文 → 返回 empty

    返回 FetchResult(content, source, quality)。
    """
    skip = skip_domains or {"twitter.com", "x.com", "medium.com", "zhihu.com", "v2ex.com"}
    tags = fulltext_tags or {"official_ai", "ai_research"}

    # 1. skip_domain
    if any(domain in original_url for domain in skip):
        return FetchResult(
            content=body_text or "",
            source="scraper",
            quality=_estimate_quality(body_text or ""),
        )

    # 2. GitHub repo → README
    if content_type == "repo" and "github.com" in original_url:
        repo = _parse_github_repo(original_url)
        if repo:
            readme = _fetch_github_readme(*repo)
            if readme:
                return FetchResult(
                    content=readme,
                    source="github_readme",
                    quality=_estimate_quality(readme),
                )
        return FetchResult(
            content=body_text or "",
            source="scraper",
            quality=_estimate_quality(body_text or ""),
        )

    # 3. 特定 tag 的文章 → 尝试抓全文
    source_tag = extra.get("source_tag", "") if isinstance(extra, dict) else ""
    if source_tag in tags:
        result = _fetch_with_fallback(original_url)
        if result.content:
            return result

    # 4. HN 外链（非 news.ycombinator.com）→ 尝试抓全文
    if source_name == "HackerNews" and "news.ycombinator.com" not in original_url:
        result = _fetch_with_fallback(original_url)
        if result.content:
            return result

    # 5. 兜底：用现有 body_text
    return FetchResult(
        content=body_text or "",
        source="scraper",
        quality=_estimate_quality(body_text or ""),
    )


def _fetch_with_fallback(url: str) -> FetchResult:
    """Jina Reader 为主，trafilatura 为 fallback。"""
    # Jina 优先
    content = _fetch_jina(url)
    if content and len(content) > 50:
        return FetchResult(
            content=content,
            source="jina",
            quality=_estimate_quality(content),
        )

    # trafilatura fallback
    content = _fetch_trafilatura(url)
    if content and len(content) > 50:
        return FetchResult(
            content=content,
            source="trafilatura",
            quality=_estimate_quality(content),
        )

    return FetchResult(content="", source="empty", quality=0.0)
