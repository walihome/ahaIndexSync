# enrichers/_utils.py
"""enricher 共享的小工具：URL 解析、GitHub slug 构造等。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_GITHUB_REPO_RE = re.compile(
    r"https?://(?:www\.)?github\.com/([A-Za-z0-9][\w.-]*)/([A-Za-z0-9][\w.-]*)",
    re.IGNORECASE,
)

# GitHub 保留路径，这些不是 user/repo
_GITHUB_RESERVED = {
    "orgs", "settings", "marketplace", "pricing", "features", "explore",
    "topics", "trending", "collections", "events", "notifications",
    "about", "sponsors", "enterprise", "customer-stories", "team", "security",
    "login", "join", "new", "issues", "pulls", "codespaces",
}


def _clean_repo(repo: str) -> str:
    """清理 repo 名末尾的 .git / 斜线。注意必须用 removesuffix 而不是 rstrip！
    rstrip(".git") 会把末尾任意属于 {'.','g','i','t'} 的字符全部吃掉，
    导致 claude-context → claude-contex 这种诡异 bug。"""
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return repo


def parse_github_repo(url: str) -> tuple[str, str] | None:
    """从 URL 解析 (owner, repo)，非 GitHub 或无效返回 None。"""
    if not url:
        return None
    m = _GITHUB_REPO_RE.match(url.strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if owner.lower() in _GITHUB_RESERVED:
        return None
    repo = _clean_repo(repo)
    if not repo or repo.startswith("."):
        return None
    return owner, repo


def github_slug(owner: str, repo: str) -> str:
    return f"github:{owner}/{repo}"


def extract_github_repos_from_text(text: str, limit: int = 20) -> list[tuple[str, str]]:
    """从任意文本中抽取所有 github.com/owner/repo 形式的 URL。"""
    if not text:
        return []
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for m in _GITHUB_REPO_RE.finditer(text):
        owner, repo = m.group(1), m.group(2)
        if owner.lower() in _GITHUB_RESERVED:
            continue
        repo = _clean_repo(repo)
        if not repo:
            continue
        key = (owner, repo)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
        if len(out) >= limit:
            break
    return out


def primary_github_repo_for_item(item: dict) -> tuple[str, str] | None:
    """若 item 本身就是 GitHub repo，返回其 (owner, repo)。"""
    if item.get("content_type") != "repo":
        url = item.get("original_url", "")
        parsed = parse_github_repo(url)
        if not parsed:
            return None
        return parsed

    extra = item.get("extra") or {}
    if isinstance(extra, dict):
        full = extra.get("repo_full_name") or extra.get("full_name")
        if full and "/" in full:
            owner, repo = full.split("/", 1)
            return owner, repo

    return parse_github_repo(item.get("original_url", ""))
