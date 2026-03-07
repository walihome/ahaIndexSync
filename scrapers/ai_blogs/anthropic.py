# scrapers/ai_blogs/anthropic.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from ..base import BaseScraper, RawItem


class AnthropicBlogScraper(BaseScraper):
    source_name = "Anthropic Blog"
    source_type = "BLOG"
    content_type = "article"

    BASE_URL = "https://www.anthropic.com"
    NEWS_URL = "https://www.anthropic.com/news"

    def fetch(self) -> list[RawItem]:
        try:
            res = requests.get(
                self.NEWS_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            items = []
            seen = set()

            for card in soup.select("a[href^='/news/']"):
                href = card.get("href", "")
                # 跳过列表页本身
                if not href or href in ("/news", "/news/"):
                    continue
                if href in seen:
                    continue
                seen.add(href)

                full_url = self.BASE_URL + href

                title_tag = card.select_one("h2, h3, h4")
                title = title_tag.get_text(strip=True) if title_tag else card.get_text(strip=True)
                if not title:
                    continue

                desc_tag = card.select_one("p")
                body_text = desc_tag.get_text(strip=True) if desc_tag else ""

                published_at = None
                time_tag = card.select_one("time")
                if time_tag:
                    dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
                    try:
                        published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                items.append(RawItem(
                    title=title,
                    original_url=full_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author="Anthropic",
                    author_url=self.BASE_URL,
                    body_text=body_text,
                    raw_metrics={},
                    published_at=published_at,
                ))

            return items

        except Exception as e:
            print(f"⚠️ Anthropic Blog 抓取失败: {e}")
            return []


if __name__ == "__main__":
    from scrapers.db import process_and_save
    scraper = AnthropicBlogScraper()
    items = scraper.fetch()
    process_and_save(items, skip_ai_filter=True)
