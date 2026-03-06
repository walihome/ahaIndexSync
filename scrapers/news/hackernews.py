import requests
from datetime import datetime, timezone
from scrapers.base import BaseScraper, RawItem

# HackerNews 官方 Firebase API，稳定免费无需鉴权
HN_API = "https://hacker-news.firebaseio.com/v0"
TOP_STORIES_URL = f"{HN_API}/topstories.json"
ITEM_URL = f"{HN_API}/item/{{item_id}}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={item_id}"

# 每次抓取 Top N 条（太多会慢，建议 50~100）
TOP_N = 60
# 最低分数过滤，减少噪音
MIN_SCORE = 50


class HackerNewsScraper(BaseScraper):
    source_name = "HackerNews"
    source_type = "NEWS"
    content_type = "article"

    def fetch(self) -> list[RawItem]:
        items = []
        try:
            resp = requests.get(TOP_STORIES_URL, timeout=15)
            resp.raise_for_status()
            story_ids = resp.json()[:TOP_N]
        except Exception as e:
            print(f"[HackerNewsScraper] Failed to fetch top stories: {e}")
            return items

        for story_id in story_ids:
            try:
                r = requests.get(ITEM_URL.format(item_id=story_id), timeout=10)
                r.raise_for_status()
                story = r.json()

                if not story or story.get("type") != "story":
                    continue
                if story.get("dead") or story.get("deleted"):
                    continue

                score = story.get("score", 0)
                if score < MIN_SCORE:
                    continue

                title = story.get("title", "").strip()
                if not title:
                    continue

                # 外链优先，无外链则指向 HN 讨论页
                original_url = story.get("url") or HN_ITEM_PAGE.format(item_id=story_id)

                author = story.get("by", "")
                comment_count = story.get("descendants", 0)
                timestamp = story.get("time")
                published_at = (
                    datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    if timestamp else None
                )

                items.append(RawItem(
                    title=title,
                    original_url=original_url,
                    source_name=self.source_name,
                    source_type=self.source_type,
                    content_type=self.content_type,
                    author=author,
                    author_url=f"https://news.ycombinator.com/user?id={author}" if author else "",
                    body_text="",
                    raw_metrics={
                        "score": score,
                        "comments": comment_count,
                        "hn_id": story_id,
                        "hn_url": HN_ITEM_PAGE.format(item_id=story_id),
                    },
                    published_at=published_at,
                ))

            except Exception as e:
                print(f"[HackerNewsScraper] Error fetching story {story_id}: {e}")
                continue

        print(f"[HackerNewsScraper] Fetched {len(items)} items (score >= {MIN_SCORE})")
        return items
