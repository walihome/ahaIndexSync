# scrapers/ai_blogs/openai.py
# 其他 AI 公司博客结构类似，换 URL 和解析逻辑即可

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from ..base import BaseScraper, RawItem

class OpenAIBlogScraper(BaseScraper):
    source_name = "OpenAI Blog"
    source_type = "BLOG"
    content_type = "article"

    def fetch(self) -> list[RawItem]:
        url = "https://openai.com/news"
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            items = []
            # 解析逻辑根据实际页面结构调整
            for post in soup.select("article"):
                title_tag = post.find(["h2", "h3"])
                link_tag = post.find("a", href=True)
                if not title_tag or not link_tag: continue
                href = link_tag["href"]
                full_url = href if href.startswith("http") else f"https://openai.com{href}"
                desc_tag = post.find("p")
                items.append(RawItem(
                    title=title_tag.text.strip(),
                    original_url=full_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    body_text=desc_tag.text.strip() if desc_tag else "",
                    raw_metrics={},
                ))
            return items
        except Exception as e:
            print(f"⚠️ OpenAI Blog 抓取失败: {e}")
            return []


if __name__ == "__main__":
    from scrapers.db import process_and_save
    scraper = OpenAIBlogScraper()
    items = scraper.fetch()
    process_and_save(items, skip_ai_filter=True)  # AI 公司博客天然相关，跳过过滤
