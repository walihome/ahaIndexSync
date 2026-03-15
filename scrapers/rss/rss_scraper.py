# scrapers/rss/rss_scraper.py

import re
import feedparser
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem
from .rss_config import RSS_FEEDS, FETCH_WINDOW_HOURS


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _build_raw_item(entry, feed_cfg: dict) -> RawItem | None:
    title = (getattr(entry, "title", "") or "").strip()
    url = (getattr(entry, "link", "") or "").strip()
    if not title or not url:
        return None

    body_text = (
        getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    ).strip()
    body_text = re.sub(r"<[^>]+>", "", body_text).strip()

    return RawItem(
        title=title,
        original_url=url,
        source_name=feed_cfg["name"],
        source_type="ARTICLE",
        content_type="article",
        author=(getattr(entry, "author", "") or "").strip(),
        body_text=body_text[:1000],
        raw_metrics={},
        extra={
            "source_tag": feed_cfg["source_tag"],
            "feed_url": feed_cfg["url"],
        },
        published_at=_parse_date(entry),
    )


class RSSFeedScraper(BaseScraper):
    source_name = "RSS"
    source_type = "ARTICLE"
    content_type = "article"

    def fetch(self) -> list[RawItem]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_WINDOW_HOURS)
        results = []

        for feed_cfg in RSS_FEEDS:
            name = feed_cfg["name"]
            max_items = feed_cfg.get("max_items")

            try:
                parsed = feedparser.parse(feed_cfg["url"])

                if parsed.bozo and not parsed.entries:
                    print(f"  ⚠️ [{name}] RSS 解析失败: {parsed.bozo_exception}")
                    continue

                items = []
                skipped_old = 0
                skipped_no_date = 0

                for entry in parsed.entries:
                    item = _build_raw_item(entry, feed_cfg)
                    if not item:
                        continue

                    if item.published_at is None:
                        # 解析不到时间：保留但计数，不做时间过滤
                        skipped_no_date += 1
                        items.append(item)
                    elif item.published_at < cutoff:
                        skipped_old += 1
                        # RSS 是倒序的，遇到过期直接停止遍历
                        break
                    else:
                        items.append(item)

                    if max_items is not None and len(items) >= max_items:
                        break

                log = f"  [{name}] {len(items)} 条"
                if skipped_old:
                    log += f"，遇到过期内容后停止"
                if skipped_no_date:
                    log += f"，{skipped_no_date} 条无日期"
                print(log)
                results.extend(items)

            except Exception as e:
                print(f"  ❌ [{name}] 失败: {e}")

        return results