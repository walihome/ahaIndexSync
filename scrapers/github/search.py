# scrapers/github/search.py

import os
import requests
from datetime import datetime, timedelta
from infra.models import BaseScraper, RawItem


class GitHubSearchScraper(BaseScraper):
    source_name = "GitHub Search"
    source_type = "REPO"
    content_type = "repo"

    def fetch(self) -> list[RawItem]:
        token = os.getenv("GH_MODELS_TOKEN")
        if not token:
            print("⚠️ GH_MODELS_TOKEN 未设置")
            return []

        headers = {"Authorization": f"token {token}"}

        # 昨天 0 点（本地时间）
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        # 过去一周
        last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        queries = [
            # 宽松：过去一周内，star > 200
            (f"created:>={last_week} stars:>100 topic:ai",           "一周内 AI topic"),
            (f"created:>={last_week} stars:>100 topic:llm",          "一周内 LLM topic"),
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
                    items.append(RawItem(
                        title=r["full_name"],
                        original_url=url,
                        source_name=self.source_name,
                        source_type=self.source_type,
                        content_type=self.content_type,
                        author=r["owner"]["login"],
                        author_url=f"https://github.com/{r['owner']['login']}",
                        body_text=r.get("description") or "",
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