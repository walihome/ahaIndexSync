# scrapers/social/twitter.py

import os
import asyncio
from datetime import datetime, timezone, timedelta
from twscrape import API, gather
from twscrape.logger import set_log_level
from infra.models import BaseScraper, RawItem
from config.tracked_keywords import TRACKED_KEYWORDS

WATCH_ACCOUNTS = [
    "karpathy",
    "sama",
    "anthropic",
    "openai",
    "demishassabis",
    "ylecun",
    "drjimfan",
    "svpino",
]

SEARCH_LIMIT = 20
TIMELINE_LIMIT = 5
TIMELINE_MIN_FAVES = 50
MAX_AGE_DAYS = 2

ACCOUNTS_DB = os.path.join(os.path.dirname(__file__), "../../.twscrape_accounts.db")


class TwitterScraper(BaseScraper):
    source_name = "X (Twitter)"
    source_type = "TWEET"
    content_type = "tweet"

    def fetch(self) -> list[RawItem]:
        try:
            return asyncio.run(self._fetch_all())
        except Exception as e:
            print(f"⚠️ TwitterScraper 失败: {e}")
            return []

    async def _fetch_all(self) -> list[RawItem]:
        set_log_level("INFO")  # 改成 INFO 看详细连接日志
        api = API(ACCOUNTS_DB)

        # 先检查账号状态
        stats = await api.pool.stats()
        print(f"  账号状态: {stats}")
        if stats.get('active', 0) == 0:
            print(f"  ⚠️ 无可用账号，跳过")
            return []

        seen: set[str] = set()
        items: list[RawItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

        # ── 1. 关键词搜索 ─────────────────────────────────────
        print(f"  开始关键词搜索，共 {len(TRACKED_KEYWORDS)} 个关键词")
        for kw in TRACKED_KEYWORDS:
            query = f'"{kw}" -is:retweet lang:en min_faves:100'
            try:
                print(f"  [搜索] {kw}...")
                tweets = await asyncio.wait_for(
                    gather(api.search(query, limit=SEARCH_LIMIT)),
                    timeout=30  # 单个关键词最多等 30 秒
                )
                new_count = 0
                for t in tweets:
                    item = self._to_raw_item(t, cutoff, seen)
                    if item:
                        items.append(item)
                        new_count += 1
                print(f"  [搜索] {kw} → {new_count} 条")
            except asyncio.TimeoutError:
                print(f"  [搜索] {kw} 超时，跳过")
            except Exception as e:
                print(f"  [搜索] 失败 ({kw}): {e}")

        # ── 2. 指定账号时间线 ──────────────────────────────────
        print(f"  开始账号时间线抓取，共 {len(WATCH_ACCOUNTS)} 个账号")
        for username in WATCH_ACCOUNTS:
            try:
                print(f"  [@{username}] 抓取中...")
                user = await asyncio.wait_for(
                    api.user_by_login(username),
                    timeout=15
                )
                if not user:
                    print(f"  [@{username}] 用户不存在，跳过")
                    continue
                tweets = await asyncio.wait_for(
                    gather(api.user_tweets(user.id, limit=TIMELINE_LIMIT)),
                    timeout=30
                )
                new_count = 0
                for t in tweets:
                    if t.likeCount < TIMELINE_MIN_FAVES:
                        continue
                    item = self._to_raw_item(t, cutoff, seen)
                    if item:
                        items.append(item)
                        new_count += 1
                print(f"  [@{username}] → {new_count} 条")
            except asyncio.TimeoutError:
                print(f"  [@{username}] 超时，跳过")
            except Exception as e:
                print(f"  [@{username}] 失败: {e}")

        print(f"  共抓取 {len(items)} 条（去重后）")
        return items

    def _to_raw_item(self, tweet, cutoff: datetime, seen: set) -> RawItem | None:
        url = f"https://x.com/{tweet.user.username}/status/{tweet.id}"
        if url in seen or tweet.date < cutoff:
            return None
        if tweet.retweetedTweet is not None:
            return None
        seen.add(url)

        return RawItem(
            title=tweet.rawContent[:100],
            original_url=url,
            source_name=self.source_name,
            source_type=self.source_type,
            content_type=self.content_type,
            author=tweet.user.username,
            author_url=f"https://x.com/{tweet.user.username}",
            body_text=tweet.rawContent,
            raw_metrics={
                "likes":    tweet.likeCount,
                "retweets": tweet.retweetCount,
                "replies":  tweet.replyCount,
                "views":    tweet.viewCount or 0,
            },
            extra={
                "tweet_id":     str(tweet.id),
                "display_name": tweet.user.displayname,
                "verified":     tweet.user.verified,
                "followers":    tweet.user.followersCount,
            },
            published_at=tweet.date,
        )
