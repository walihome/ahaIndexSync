# scrapers/twitter_nitter.py

import re
import requests
import feedparser
from datetime import datetime, timezone, timedelta
from infra.models import BaseScraper, RawItem
from scrapers.registry import register

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}


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
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@register("twitter_nitter")
class TwitterNitterEngine(BaseScraper):
    def fetch(self) -> list[RawItem]:
        twitter_user = self.config.get("twitter_user", "")
        if not twitter_user:
            return []

        instances = self.config.get("nitter_instances", ["https://nitter.poast.org"])
        aggregate = self.config.get("aggregate", True)
        fetch_window = self.config.get("fetch_window_hours", 25)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=fetch_window)

        parsed = None
        for instance in instances:
            url = f"{instance}/{twitter_user}/rss"
            try:
                resp = requests.get(url, timeout=10, headers=HEADERS)
                if resp.status_code != 200:
                    continue
                parsed = feedparser.parse(resp.text)
                if parsed.entries:
                    break
            except Exception:
                continue

        if not parsed or not parsed.entries:
            print(f"  ❌ 所有 Nitter 实例均不可用 (@{twitter_user})")
            return []

        if aggregate:
            return self._aggregate(parsed, twitter_user, cutoff)
        else:
            return self._individual(parsed, twitter_user, cutoff)

    def _aggregate(self, parsed, twitter_user: str, cutoff: datetime) -> list[RawItem]:
        tweets = []
        for entry in parsed.entries:
            title = (getattr(entry, "title", "") or "").strip()
            if title.startswith("RT by @"):
                continue
            pub = _parse_date(entry)
            if pub is None or pub < cutoff:
                continue
            url = (getattr(entry, "link", "") or "").strip()
            text = _clean_text(getattr(entry, "summary", "") or title)
            tweets.append({"url": url, "text": text, "published_at": pub})

        if not tweets:
            print(f"  [{self.name}] 无近期原创推文，跳过")
            return []

        tweets.sort(key=lambda x: x["published_at"] or datetime.min.replace(tzinfo=timezone.utc))
        lines = [f"[{t['published_at'].strftime('%m-%d %H:%M')}] {t['text']}" for t in tweets]
        latest = tweets[-1]

        print(f"  [{self.name}] 聚合 {len(tweets)} 条原创推文")
        return [RawItem(
            title=f"@{twitter_user} 近期推文",
            original_url=latest["url"],
            source_name=self.name,
            source_type=self.config.get("source_type", "TWEET"),
            content_type="tweet_digest",
            author=twitter_user,
            author_url=f"https://x.com/{twitter_user}",
            body_text="\n\n".join(lines),
            raw_metrics={"tweet_count": len(tweets)},
            extra={"source_tag": self.config.get("source_tag", "social"), "account": twitter_user, "tweet_urls": [t["url"] for t in tweets]},
            published_at=latest["published_at"],
        )]

    def _individual(self, parsed, twitter_user: str, cutoff: datetime) -> list[RawItem]:
        items = []
        for entry in parsed.entries:
            title = (getattr(entry, "title", "") or "").strip()
            if title.startswith("RT by @"):
                continue
            entry_url = (getattr(entry, "link", "") or "").strip()
            if not title or not entry_url:
                continue
            pub = _parse_date(entry)
            if pub is not None and pub < cutoff:
                break
            body_text = _clean_text(getattr(entry, "summary", "") or "")
            items.append(RawItem(
                title=title, original_url=entry_url,
                source_name=self.name, source_type="TWEET", content_type="tweet",
                author=twitter_user, body_text=body_text[:1000],
                raw_metrics={}, extra={"source_tag": self.config.get("source_tag", "social")},
                published_at=pub,
            ))
        print(f"  [{self.name}] {len(items)} 条")
        return items
