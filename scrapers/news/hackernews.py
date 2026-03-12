# scrapers/news/hackernews.py

import requests
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem

HN_API = "https://hacker-news.firebaseio.com/v0"
NEW_STORIES_URL = f"{HN_API}/newstories.json"
ITEM_URL = f"{HN_API}/item/{{item_id}}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={item_id}"

NEW_N = 500
MIN_SCORE = 50


class HackerNewsScraper(BaseScraper):
    source_name = "HackerNews"
    source_type = "NEWS"
    content_type = "article"

    def fetch(self) -> list[RawItem]:
        seen = set()
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=36)

        try:
            resp = requests.get(NEW_STORIES_URL, timeout=15)
            resp.raise_for_status()
            story_ids = resp.json()[:NEW_N]

            for story_id in story_ids:
                result = self._fetch_story(story_id, seen, cutoff)
                if result is False:
                    break  # 超出时间窗口，后面只会更老
                if result:
                    items.append(result)

        except Exception as e:
            print(f"⚠️ HN New Stories 失败: {e}")

        print(f"  共抓取 {len(items)} 条（score >= {MIN_SCORE}，过去36小时）")
        return items

    def _fetch_story(self, story_id: int, seen: set, cutoff: datetime):
        """
        返回值：
          RawItem — 成功
          None    — 跳过
          False   — 早于 cutoff，通知上层停止遍历
        """
        try:
            r = requests.get(ITEM_URL.format(item_id=story_id), timeout=10)
            r.raise_for_status()
            story = r.json()

            if not story or story.get("type") != "story":
                return None
            if story.get("dead") or story.get("deleted"):
                return None

            timestamp = story.get("time")
            if not timestamp:
                return None

            published_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            if published_at < cutoff:
                return False

            if story.get("score", 0) < MIN_SCORE:
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
