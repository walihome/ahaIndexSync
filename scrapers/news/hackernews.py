# scrapers/news/hackernews.py

import requests
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem

HN_API = "https://hacker-news.firebaseio.com/v0"
NEW_STORIES_URL = f"{HN_API}/newstories.json"
ITEM_URL = f"{HN_API}/item/{{item_id}}.json"
HN_ITEM_PAGE = "https://news.ycombinator.com/item?id={item_id}"

NEW_N = 500
MIN_SCORE = 50
FETCH_WORKERS = 5  # 并发抓取正文的线程数

# 抓不到正文的域名，跳过
SKIP_DOMAINS = {
    "twitter.com", "x.com",
    "medium.com",
    "zhihu.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# trafilatura 多线程不安全，加锁
try:
    import trafilatura
    _trafilatura_lock = threading.Lock()
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False


def _fetch_body(url: str) -> str:
    """抓取文章正文"""
    if not HAS_TRAFILATURA:
        return ""
    if any(d in url for d in SKIP_DOMAINS):
        return ""
    if "news.ycombinator.com" in url:
        return ""
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            return ""
        with _trafilatura_lock:
            content = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
        return content or ""
    except Exception:
        return ""


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
                    break
                if result:
                    items.append(result)

        except Exception as e:
            print(f"⚠️ HN New Stories 失败: {e}")

        # 并发抓取正文
        if items:
            print(f"  📄 并发抓取 {len(items)} 篇正文（workers={FETCH_WORKERS}）...")
            self._enrich_items(items)

        print(f"  共抓取 {len(items)} 条（score >= {MIN_SCORE}，过去36小时）")
        return items

    def _enrich_items(self, items: list[RawItem]):
        """并发为每条 item 抓取正文"""
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_body, item.original_url): item
                for item in items
            }
            for future in as_completed(futures):
                item = futures[future]
                try:
                    body = future.result()
                    if body:
                        item.body_text = body
                except Exception:
                    pass

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
                body_text="",  # 后续由 _enrich_items 并发填充
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
