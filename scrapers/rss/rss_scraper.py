# scrapers/rss/rss_scraper.py

import re
import feedparser
from datetime import datetime, timezone, timedelta
from ..base import BaseScraper, RawItem
from .rss_feeds_config import RSS_FEEDS, FETCH_WINDOW_HOURS


def _parse_date(entry) -> datetime | None:
    """从 feedparser entry 里提取发布时间"""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _build_raw_item(entry, feed_cfg: dict) -> RawItem | None:
    """把单条 RSS entry 转成 RawItem"""
    title = (getattr(entry, "title", "") or "").strip()
    url = (getattr(entry, "link", "") or "").strip()
    if not title or not url:
        return None

    body_text = (
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
        or ""
    ).strip()
    body_text = re.sub(r"<[^>]+>", "", body_text).strip()

    author = (getattr(entry, "author", "") or "").strip()
    published_at = _parse_date(entry)

    return RawItem(
        title=title,
        original_url=url,
        source_name=feed_cfg["name"],
        source_type="ARTICLE",
        content_type="article",
        author=author,
        body_text=body_text[:1000],
        raw_metrics={},
        extra={
            "source_tag": feed_cfg["source_tag"],
            "feed_url": feed_cfg["url"],
        },
        published_at=published_at,
    )


class RSSFeedScraper(BaseScraper):
    """
    通用 RSS 抓取器，所有配置来自 rss_feeds_config.py
    流程：先按时间窗口过滤，再按 max_items 限量
    """

    def fetch(self) -> list[RawItem]:
        raise NotImplementedError("请直接调用 fetch_all()")

    def fetch_all(self) -> list[tuple[RawItem, bool]]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FETCH_WINDOW_HOURS)
        results = []

        for feed_cfg in RSS_FEEDS:
            name = feed_cfg["name"]
            url = feed_cfg["url"]
            max_items = feed_cfg.get("max_items")
            skip_ai_filter = feed_cfg.get("skip_ai_filter", False)

            try:
                parsed = feedparser.parse(url)

                if parsed.bozo and not parsed.entries:
                    print(f"  ⚠️ [{name}] RSS 解析失败: {parsed.bozo_exception}")
                    continue

                items = []
                skipped_old = 0

                for entry in parsed.entries:
                    item = _build_raw_item(entry, feed_cfg)
                    if not item:
                        continue

                    # ① 先过滤时间窗口
                    # 无时间字段的直接放行，宁可多抓不漏
                    if item.published_at and item.published_at < cutoff:
                        skipped_old += 1
                        continue

                    items.append(item)

                    # ② 时间过滤后再限量
                    if max_items is not None and len(items) >= max_items:
                        break

                print(
                    f"  [{name}] 保留 {len(items)} 条"
                    + (f"，跳过 {skipped_old} 条过期" if skipped_old else "")
                )
                results.extend([(item, skip_ai_filter) for item in items])

            except Exception as e:
                print(f"  ❌ [{name}] 抓取失败: {e}")

        return results
