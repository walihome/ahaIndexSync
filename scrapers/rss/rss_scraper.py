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


def _clean_text(text: str) -> str:
    """去掉 HTML 标签"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_retweet(title: str) -> bool:
    return title.strip().startswith("RT by @")


def _build_raw_item(entry, feed_cfg: dict) -> RawItem | None:
    title = (getattr(entry, "title", "") or "").strip()
    url = (getattr(entry, "link", "") or "").strip()
    if not title or not url:
        return None

    body_text = _clean_text(
        getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
    )

    content_type = feed_cfg.get("content_type", "article")
    source_type = "TWEET" if content_type == "tweet" else "ARTICLE"

    return RawItem(
        title=title,
        original_url=url,
        source_name=feed_cfg["name"],
        source_type=source_type,
        content_type=content_type,
        author=(getattr(entry, "author", "") or "").strip(),
        body_text=body_text[:1000],
        raw_metrics={},
        extra={
            "source_tag": feed_cfg.get("source_tag", ""),
            "feed_url": feed_cfg["url"],
        },
        published_at=_parse_date(entry),
    )


def _build_aggregate_item(feed_cfg: dict, tweets: list[dict]) -> RawItem | None:
    """把一个账号的多条原创推文聚合成一条 RawItem"""
    if not tweets:
        return None

    # 从 source_name 提取账号名，如 "Twitter @ylecun" → "ylecun"
    account = feed_cfg["name"].replace("Twitter @", "").strip()

    # 按时间排序
    tweets.sort(key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc))

    # 每条推文格式：[时间] 内容
    lines = []
    for t in tweets:
        time_str = t["published_at"].strftime("%m-%d %H:%M") if t["published_at"] else ""
        lines.append(f"[{time_str}] {t['text']}")

    body_text = "\n\n".join(lines)

    # 用最新一条的 URL 作为 original_url
    latest = tweets[-1]

    return RawItem(
        title=f"@{account} 近期推文",
        original_url=latest["url"],
        source_name=feed_cfg["name"],
        source_type="TWEET",
        content_type="tweet_digest",   # 新类型，触发专属 AI prompt
        author=account,
        author_url=f"https://x.com/{account}",
        body_text=body_text,
        raw_metrics={"tweet_count": len(tweets)},
        extra={
            "source_tag": feed_cfg.get("source_tag", "social"),
            "account": account,
            "tweet_urls": [t["url"] for t in tweets],
        },
        published_at=latest["published_at"],
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
            is_aggregate = feed_cfg.get("aggregate", False)

            try:
                parsed = feedparser.parse(feed_cfg["url"])

                if parsed.bozo and not parsed.entries:
                    print(f"  ⚠️ [{name}] RSS 解析失败: {parsed.bozo_exception}")
                    continue

                if is_aggregate:
                    # 聚合模式：收集原创推文，合并成一条
                    tweets = []
                    for entry in parsed.entries:
                        title = (getattr(entry, "title", "") or "").strip()

                        # 过滤转推
                        if _is_retweet(title):
                            continue

                        pub = _parse_date(entry)
                        # 无日期或超出时间窗口跳过
                        if pub and pub < cutoff:
                            break
                        if pub is None:
                            continue

                        url = (getattr(entry, "link", "") or "").strip()
                        text = _clean_text(
                            getattr(entry, "summary", "") or
                            getattr(entry, "description", "") or
                            title
                        )
                        tweets.append({
                            "url": url,
                            "text": text,
                            "published_at": pub,
                        })

                    item = _build_aggregate_item(feed_cfg, tweets)
                    if item:
                        print(f"  [{name}] 聚合 {len(tweets)} 条原创推文")
                        results.append(item)
                    else:
                        print(f"  [{name}] 无近期原创推文，跳过")

                else:
                    # 普通模式：逐条处理
                    items = []
                    skipped_old = 0
                    skipped_no_date = 0

                    for entry in parsed.entries:
                        title = (getattr(entry, "title", "") or "").strip()
                        if _is_retweet(title):
                            continue

                        item = _build_raw_item(entry, feed_cfg)
                        if not item:
                            continue

                        if item.published_at is None:
                            skipped_no_date += 1
                            items.append(item)
                        elif item.published_at < cutoff:
                            skipped_old += 1
                            break
                        else:
                            items.append(item)

                        if max_items is not None and len(items) >= max_items:
                            break

                    log = f"  [{name}] {len(items)} 条"
                    if skipped_old:
                        log += "，遇到过期内容后停止"
                    if skipped_no_date:
                        log += f"，{skipped_no_date} 条无日期"
                    print(log)
                    results.extend(items)

            except Exception as e:
                print(f"  ❌ [{name}] 失败: {e}")

        return results