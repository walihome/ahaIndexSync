# scrapers/ai_blogs/mistral.py

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from infra.models import BaseScraper, RawItem


class MistralBlogScraper(BaseScraper):
    source_name = "Mistral AI Blog"
    source_type = "BLOG"
    content_type = "article"

    BASE_URL = "https://mistral.ai"
    NEWS_URL = "https://mistral.ai/news"

    def fetch(self) -> list[RawItem]:
        try:
            res = requests.get(self.NEWS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            items = []
            seen = set()

            for card in soup.select("a[href*='/news/']"):
                href = card.get("href", "")
                if not href or href in ("/news", "/news/"):
                    continue
                if href in seen:
                    continue
                seen.add(href)

                full_url = href if href.startswith("http") else self.BASE_URL + href
                title_tag = card.select_one("h2, h3, h4")
                title = title_tag.get_text(strip=True) if title_tag else card.get_text(strip=True)
                if not title:
                    continue

                published_at = None
                time_tag = card.select_one("time")
                if time_tag:
                    dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
                    try:
                        published_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    except Exception:
                        pass

                desc_tag = card.select_one("p")
                items.append(RawItem(
                    title=title,
                    original_url=full_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author="Mistral AI",
                    author_url=self.BASE_URL,
                    body_text=desc_tag.get_text(strip=True) if desc_tag else "",
                    raw_metrics={},
                    extra={"source_tag": "official_ai"},
                    published_at=published_at,
                ))

            print(f"  抓取到 {len(items)} 条")
            return items
        except Exception as e:
            print(f"⚠️ {self.source_name} 抓取失败: {e}")
            return []