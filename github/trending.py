# scrapers/github/trending.py

import requests
from bs4 import BeautifulSoup
from ..base import BaseScraper, RawItem

class GitHubTrendingScraper(BaseScraper):
    source_name = "GitHub"
    source_type = "REPO"
    content_type = "repo"

    def fetch(self) -> list[RawItem]:
        url = "https://github.com/trending"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(url, headers=headers, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            items = []
            for rank, article in enumerate(soup.find_all("article", class_="Box-row"), start=1):
                title_tag = article.find("h2", class_="h3")
                full_name = "".join(title_tag.text.split()) if title_tag else ""
                repo_url = f"https://github.com{title_tag.find('a')['href']}" if title_tag else ""
                desc_tag = article.find("p", class_="col-9")
                description = desc_tag.text.strip() if desc_tag else ""
                stars = 0
                meta = article.find("div", class_="f6 color-fg-muted mt-2")
                if meta:
                    s_link = meta.find("a", href=lambda x: x and x.endswith("/stargazers"))
                    if s_link:
                        try: stars = int(s_link.text.strip().replace(",", ""))
                        except: pass
                items.append(RawItem(
                    title=full_name,
                    original_url=repo_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author=full_name.split("/")[0] if "/" in full_name else "",
                    body_text=description,
                    raw_metrics={"stars": stars, "rank": rank, "source": "trending"},
                ))
            return items
        except Exception as e:
            print(f"⚠️ GitHub Trending 抓取失败: {e}")
            return []


if __name__ == "__main__":
    from scrapers.db import process_and_save
    scraper = GitHubTrendingScraper()
    items = scraper.fetch()
    process_and_save(items)
