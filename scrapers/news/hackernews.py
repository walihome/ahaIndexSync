# scrapers/news/hackernews.py

import requests
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem
from config.tracked_keywords import TRACKED_KEYWORDS

HN_API = "https://hacker-news.firebaseio.com/v0"
HN_SEARCH_API = "https://hn.algolia.com/api/v1/search"
TOP_STORIES_URL = f"{HN_API}/topstories.json"
ITEM_URL = f"{HN_API}/item/{{item_id}}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={item_id}"

TOP_N = 60
MIN_SCORE = 50
SEARCH_PER_KEYWORD = 3


class HackerNewsScraper(BaseScraper):
    source_name = "HackerNews"
    source_type = "NEWS"
    content_type = "article"

    def fetch(self) -> list[RawItem]:
        seen = set()
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=36)
        cutoff_ts = int(cutoff.timestamp())

        # ── 1. Top Stories ────────────────────────────────────
        try:
            resp = requests.get(TOP_STORIES_URL, timeout=15)
            resp.raise_for_status()
            story_ids = resp.json()[:TOP_N]

            for story_id in story_ids:
                item = self._fetch_story(story_id, seen, cutoff)
                if item:
                    items.append(item)
        except Exception as e:
            print(f"⚠️ HN Top Stories 失败: {e}")

        # ── 2. 关键词搜索（Algolia API，直接在查询里加时间过滤）──
        for kw in TRACKED_KEYWORDS:
            try:
                res = requests.get(
                    HN_SEARCH_API,
                    params={
                        "query": kw,
                        "tags": "story",
                        "hitsPerPage": SEARCH_PER_KEYWORD,
                        "numericFilters": f"points>={MIN_SCORE},created_at_i>={cutoff_ts}",
                    },
                    timeout=10,
                )
                if res.status_code != 200:
                    continue
                for hit in res.json().get("hits", []):
                    story_id = int(hit["objectID"])
                    item = self._fetch_story(story_id, seen, cutoff)
                    if item:
                        items.append(item)
            except Exception as e:
                print(f"⚠️ HN 关键词搜索失败 ({kw}): {e}")

        print(f"  共抓取 {len(items)} 条（去重后）")
        return items

    def _fetch_story(self, story_id: int, seen: set, cutoff: datetime) -> RawItem | None:
        try:
            r = requests.get(ITEM_URL.format(item_id=story_id), timeout=10)
            r.raise_for_status()
            story = r.json()

            if not story or story.get("type") != "story":
                return None
            if story.get("dead") or story.get("deleted"):
                return None
            if story.get("score", 0) < MIN_SCORE:
                return None

            # 时间过滤：只保留过去 24 小时内发布的
            timestamp = story.get("time")
            if not timestamp:
                return None
            published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if published_at < cutoff:
                return None

            title = story.get("title", "").strip()
            if not title:
                return None

            url = story.get("url") or HN_ITEM_PAGE.format(item_id=story_id)
            if url in seen:
                return None
            seen.add(url)

            author = story.get("by", "")
            return RawItem(
                title=title,
                original_url=url,
                source_name=self.source_name,
                source_type=self.source_type,
                content_type=self.content_type,
                author=author,
                author_url=f"https://news.ycombinator.com/user?id={author}" if author else "",
                body_text="",
                raw_metrics={
                    "score": story.get("score", 0),
                    "comments": story.get("descendants", 0),
                    "hn_id": story_id,
                    "hn_url": HN_ITEM_PAGE.format(item_id=story_id),
                },
                published_at=published_at,
            )
        except Exception:
            return None