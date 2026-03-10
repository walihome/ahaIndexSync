# scrapers/ai_blogs/openai.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from infra.models import BaseScraper, RawItem


class OpenAIBlogScraper(BaseScraper):
    source_name = "OpenAI Blog"
    source_type = "BLOG"
    content_type = "article"

    BASE_URL = "https://openai.com"
    NEWS_URL = "https://openai.com/news"

    def fetch(self) -> list[RawItem]:
        try:
            res = requests.get(
                self.NEWS_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            items = []
            seen = set()

            for post in soup.select("article"):
                title_tag = post.find(["h2", "h3"])
                link_tag = post.find("a", href=True)
                if not title_tag or not link_tag:
                    continue

                href = link_tag["href"]
                full_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"
                if full_url in seen:
                    continue
                seen.add(full_url)

                desc_tag = post.find("p")

                published_at = None
                time_tag = post.find("time")
                if time_tag:
                    dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
                    try:
                        published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                items.append(RawItem(
                    title=title_tag.text.strip(),
                    original_url=full_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author="OpenAI",
                    author_url=self.BASE_URL,
                    body_text=desc_tag.text.strip() if desc_tag else "",
                    raw_metrics={},
                    extra={"source_tag": "official_ai"},
                    published_at=published_at,
                ))

            print(f"  抓取到 {len(items)} 条")
            return items

        except Exception as e:
            print(f"⚠️ {self.source_name} 抓取失败: {e}")
            return []