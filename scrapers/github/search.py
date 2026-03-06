# scrapers/github/search.py

import os
import requests
from datetime import datetime, timedelta
from ..base import BaseScraper, RawItem

class GitHubSearchScraper(BaseScraper):
    source_name = "GitHub"
    source_type = "REPO"
    content_type = "repo"

    def fetch(self) -> list[RawItem]:
        token = os.getenv("GH_MODELS_TOKEN")
        if not token: return []
        headers = {"Authorization": f"token {token}"}
        last_week = (datetime.now() - timedelta(days=7)).date()
        last_month = (datetime.now() - timedelta(days=30)).date()
        queries = [
            f"topic:ai created:>{last_week} stars:>100",
            f"created:>{last_month} stars:>1000 LLM",
            f"topic:llm pushed:>{last_week} forks:>50",
        ]
        seen, items = set(), []
        for q in queries:
            try:
                res = requests.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params={"q": q, "sort": "stars", "order": "desc"},
                    timeout=15
                )
                if res.status_code != 200: continue
                for r in res.json().get("items", []):
                    if r["html_url"] in seen: continue
                    seen.add(r["html_url"])
                    items.append(RawItem(
                        title=r["full_name"],
                        original_url=r["html_url"],
                        source_name=self.source_name,
                        source_type=self.source_type,
                        content_type=self.content_type,
                        author=r["owner"]["login"],
                        body_text=r["description"] or "",
                        raw_metrics={"stars": r["stargazers_count"], "forks": r["forks_count"], "source": "search_api"},
                        extra={"language": r.get("language"), "topics": r.get("topics", [])},
                    ))
            except Exception as e:
                print(f"⚠️ GitHub Search 失败 ({q}): {e}")
        return items


if __name__ == "__main__":
    from scrapers.db import process_and_save
    scraper = GitHubSearchScraper()
    items = scraper.fetch()
    process_and_save(items)
