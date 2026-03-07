# scrapers/rss/rss_scraper.py

import feedparser
from datetime import datetime, timezone
from ..base import BaseScraper, RawItem
from .rss_feeds_config import RSS_FEEDS


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

    # 摘要：summary > description > 空
    body_text = (
        getattr(entry, "summary", "")
        or getattr(entry, "description", "")
        or ""
    ).strip()
    # 去掉 HTML 标签（简单处理）
    import re
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
        body_text=body_text[:1000],  # 截断，避免 token 爆炸
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
    每个 feed 独立控制 max_items / skip_ai_filter / source_tag
    """

    def fetch(self) -> list[RawItem]:
        # 这里返回所有 feed 的原始数据，不做 skip_ai_filter
        # skip_ai_filter 在 fetch_all() 里按 feed 单独处理
        raise NotImplementedError("请直接调用 fetch_and_save()")

    def fetch_all(self) -> list[tuple[RawItem, bool]]:
        """
        返回 (RawItem, skip_ai_filter) 的列表
        由 main.py 解包后分别调用 process_and_save
        """
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

                entries = parsed.entries
                if max_items is not None:
                    entries = entries[:max_items]

                items = []
                for entry in entries:
                    item = _build_raw_item(entry, feed_cfg)
                    if item:
                        items.append(item)

                print(f"  [{name}] 获取 {len(items)} 条 (max={max_items}, skip_filter={skip_ai_filter})")
                results.extend([(item, skip_ai_filter) for item in items])

            except Exception as e:
                print(f"  ❌ [{name}] 抓取失败: {e}")

        return results
