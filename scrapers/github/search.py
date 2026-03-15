# scrapers/github/search.py

import os
import re
import requests
from datetime import datetime, timedelta
from infra.models import BaseScraper, RawItem

GITHUB_TOKEN_ENV = "GH_MODELS_TOKEN"
FETCH_WINDOW_HOURS = 25 * 24  # 时间窗口


def _get_headers(token: str) -> dict:
    return {"Authorization": f"token {token}"}


def _clean_readme(text: str) -> str:
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'^\s*\[.*?\]\(.*?\)\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _fetch_readme(owner: str, repo: str, token: str) -> str:
    try:
        headers = {"Accept": "application/vnd.github.raw"}
        if token:
            headers["Authorization"] = f"token {token}"
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


def _fetch_languages(owner: str, repo: str, token: str) -> str:
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


class GitHubSearchScraper(BaseScraper):
    source_name = "GitHub Search"
    source_type = "REPO"
    content_type = "repo"

    def fetch(self) -> list[RawItem]:
        token = os.getenv(GITHUB_TOKEN_ENV)
        if not token:
            print("⚠️ GH_MODELS_TOKEN 未设置")
            return []

        headers = _get_headers(token)
        last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        queries = [
            (f"created:>={last_week} stars:>100 topic:ai",                "一周内 AI topic"),
            (f"created:>={last_week} stars:>100 topic:llm",               "一周内 LLM topic"),
            (f"created:>={last_week} stars:>100 LLM in:name,description", "一周内 LLM 关键词"),
        ]

        seen, items = set(), []

        for q, label in queries:
            try:
                res = requests.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params={"q": q, "sort": "stars", "order": "desc", "per_page": 30},
                    timeout=15
                )
                if res.status_code == 403:
                    print(f"⚠️ GitHub API 频率限制，跳过: {label}")
                    continue
                if res.status_code != 200:
                    print(f"⚠️ GitHub Search 异常 [{res.status_code}] ({label})")
                    continue

                results = res.json().get("items", [])
                new_count = 0
                for r in results:
                    url = r["html_url"]
                    if url in seen:
                        continue
                    seen.add(url)
                    new_count += 1

                    owner = r["owner"]["login"]
                    repo = r["name"]

                    # 抓取阶段直接获取 README 和语言信息
                    lang_prefix = _fetch_languages(owner, repo, token)
                    readme = _fetch_readme(owner, repo, token)
                    body_text = lang_prefix + readme if readme else (r.get("description") or "")

                    items.append(RawItem(
                        title=r["full_name"],
                        original_url=url,
                        source_name=self.source_name,
                        source_type=self.source_type,
                        content_type=self.content_type,
                        author=owner,
                        author_url=f"https://github.com/{owner}",
                        body_text=body_text,
                        raw_metrics={
                            "stars": r["stargazers_count"],
                            "forks": r["forks_count"],
                            "watchers": r.get("watchers_count", 0),
                            "open_issues": r.get("open_issues_count", 0),
                        },
                        extra={
                            "language": r.get("language"),
                            "topics": r.get("topics", []),
                            "created_at": r.get("created_at"),
                            "search_query": label,
                        },
                        published_at=datetime.fromisoformat(
                            r["created_at"].replace("Z", "+00:00")
                        ) if r.get("created_at") else None,
                    ))

                print(f"  [{label}] 返回 {len(results)} 条，新增 {new_count} 条")

            except Exception as e:
                print(f"⚠️ GitHub Search 失败 ({label}): {e}")

        print(f"  抓取到 {len(items)} 条原始数据（去重后）")
        return items
