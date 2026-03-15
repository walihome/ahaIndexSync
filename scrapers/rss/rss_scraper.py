# scrapers/rss/rss_scraper.py

import re
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem
from .rss_config import RSS_FEEDS, FETCH_WINDOW_HOURS, NITTER_INSTANCES

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Nitter 实例健康状态缓存（运行期间有效）
# 记录已知不可用的实例，避免重复尝试
_nitter_blacklist: set[str] = set()


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


def _fetch_feed(url: str, timeout: int = 15) -> feedparser.FeedParserDict | None:
    """用 requests 先拿 HTTP 响应，再交给 feedparser 解析。
    好处：能拿到 status code，超时可控，header 可定制。
    """
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} for {url}")
            return None
        return feedparser.parse(resp.text)
    except requests.Timeout:
        print(f"    超时: {url}")
        return None
    except Exception as e:
        print(f"    请求失败: {url} -> {e}")
        return None


def _fetch_nitter_feed(twitter_user: str) -> feedparser.FeedParserDict | None:
    """依次尝试多个 Nitter 实例，返回第一个成功的结果。"""
    for instance in NITTER_INSTANCES:
        if instance in _nitter_blacklist:
            continue

        url = f"{instance}/{twitter_user}/rss"
        try:
            resp = requests.get(url, timeout=10, headers=HEADERS)

            if resp.status_code == 429:
                print(f"    ⚠️ {instance} 被限流(429)，切换下一个实例")
                _nitter_blacklist.add(instance)
                continue

            if resp.status_code != 200:
                print(f"    ⚠️ {instance} 返回 HTTP {resp.status_code}，切换下一个实例")
                _nitter_blacklist.add(instance)
                continue

            parsed = feedparser.parse(resp.text)
            if parsed.entries:
                return parsed

            # 有响应但没内容，可能实例有问题
            print(f"    ⚠️ {instance} 返回空 feed，切换下一个实例")
            continue

        except requests.Timeout:
            print(f"    ⚠️ {instance} 超时，切换下一个实例")
            _nitter_blacklist.add(instance)
            continue
        except Exception as e:
            print(f"    ⚠️ {instance} 失败: {e}，切换下一个实例")
            _nitter_blacklist.add(instance)
            continue

    print(f"    ❌ 所有 Nitter 实例均不可用 (@{twitter_user})")
    return None


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
            "feed_url": feed_cfg.get("url", ""),
        },
        published_at=_parse_date(entry),
    )


def _build_aggregate_item(feed_cfg: dict, tweets: list[dict]) -> RawItem | None:
    """把一个账号的多条原创推文聚合成一条 RawItem"""
    if not tweets:
        return None

    # 从 source_name 提取账号名，如 "Twitter @ylecun" → "ylecun"
    account = feed_cfg.get("twitter_user") or feed_cfg["name"].replace("Twitter @", "").strip()

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
        content_type="tweet_digest",
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
            twitter_user = feed_cfg.get("twitter_user")

            try:
                # ── 获取 feed ──────────────────────────────────
                if twitter_user:
                    # Nitter RSS：自动 fallback 多个实例
                    parsed = _fetch_nitter_feed(twitter_user)
                elif feed_cfg.get("url"):
                    # 普通 RSS：用 requests 预检
                    parsed = _fetch_feed(feed_cfg["url"])
                else:
                    print(f"  ⚠️ [{name}] 无 url 也无 twitter_user，跳过")
                    continue

                if parsed is None:
                    continue

                if parsed.bozo and not parsed.entries:
                    print(f"  ⚠️ [{name}] RSS 解析失败: {parsed.bozo_exception}")
                    continue

                if is_aggregate:
                    # ── 聚合模式：收集原创推文，合并成一条 ──
                    tweets = []
                    for entry in parsed.entries:
                        title = (getattr(entry, "title", "") or "").strip()

                        # 过滤转推
                        if _is_retweet(title):
                            continue

                        pub = _parse_date(entry)
                        # 无日期跳过，过期跳过（用 continue 而非 break，防止乱序）
                        if pub is None:
                            continue
                        if pub < cutoff:
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
                    # ── 普通模式：逐条处理 ──
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

        # 打印 Nitter 实例健康状况
        if _nitter_blacklist:
            print(f"  ℹ️ 本次运行中不可用的 Nitter 实例: {', '.join(_nitter_blacklist)}")

        return results