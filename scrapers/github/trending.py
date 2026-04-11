# scrapers/github/trending.py

import os
import requests
from bs4 import BeautifulSoup
from infra.models import BaseScraper, RawItem
from .search import (
    _fetch_readme_raw, _clean_readme, _extract_readme_images,
    _fetch_languages, _star_history_url,
)

GITHUB_TOKEN_ENV = "GH_MODELS_TOKEN"


class GitHubTrendingScraper(BaseScraper):
    source_name = "GitHub Trending"
    source_type = "REPO"
    content_type = "repo"

    def fetch(self) -> list[RawItem]:
        token = os.getenv(GITHUB_TOKEN_ENV, "")
        try:
            res = requests.get(
                "https://github.com/trending",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            items = []
            for rank, article in enumerate(soup.find_all("article", class_="Box-row"), start=1):
                title_tag = article.find("h2", class_="h3")
                if not title_tag:
                    continue
                full_name = "".join(title_tag.text.split())
                repo_url = f"https://github.com{title_tag.find('a')['href']}"

                desc_tag = article.find("p", class_="col-9")
                description = desc_tag.text.strip() if desc_tag else ""

                stars = 0
                meta = article.find("div", class_="f6 color-fg-muted mt-2")
                if meta:
                    s_link = meta.find("a", href=lambda x: x and x.endswith("/stargazers"))
                    if s_link:
                        try:
                            stars = int(s_link.text.strip().replace(",", ""))
                        except Exception:
                            pass

                parts = full_name.split("/")
                owner, repo = (parts[0], parts[1]) if len(parts) == 2 else ("", full_name)

                # 获取 README 原文 → 提取图片 → 清洗文本
                readme_raw = _fetch_readme_raw(owner, repo, token) if owner else ""
                readme_images = _extract_readme_images(readme_raw, owner, repo) if readme_raw else []
                readme_clean = _clean_readme(readme_raw) if readme_raw else ""

                star_history = _star_history_url(owner, repo) if owner else ""

                lang_prefix = _fetch_languages(owner, repo, token) if owner else ""
                body_text = lang_prefix + readme_clean if readme_clean else description

                items.append(RawItem(
                    title=full_name,
                    original_url=repo_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author=owner,
                    body_text=body_text,
                    raw_metrics={"stars": stars, "rank": rank},
                    extra={
                        "description": description,
                        "readme_images": readme_images,
                        "star_history_url": star_history,
                    },
                ))

            print(f"  抓取到 {len(items)} 条")
            return items
        except Exception as e:
            print(f"⚠️ GitHub Trending 失败: {e}")
            return []
