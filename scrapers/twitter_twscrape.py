# scrapers/twitter_twscrape.py

import os
import asyncio
from datetime import datetime, timezone, timedelta
from twscrape import API, gather
from twscrape.logger import set_log_level
from infra.models import BaseScraper, RawItem
from scrapers.registry import register

ACCOUNTS_DB = os.path.join(os.path.dirname(__file__), "../.twscrape_accounts.db")


@register("twitter_twscrape")
class TwitterTwscrapeEngine(BaseScraper):
    def fetch(self) -> list[RawItem]:
        try:
            return asyncio.run(self._fetch_all())
        except Exception as e:
            print(f"⚠️ TwitterScraper 失败: {e}")
            return []

    async def _fetch_all(self) -> list[RawItem]:
        set_log_level("INFO")
        api = API(ACCOUNTS_DB)
        stats = await api.pool.stats()
        print(f"  账号状态: {stats}")
        if stats.get('active', 0) == 0:
            print(f"  ⚠️ 无可用账号，跳过")
            return []

        max_age = self.config.get("max_age_days", 2)
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)
        seen: set[str] = set()
        items: list[RawItem] = []

        keywords = self.config.get("tracked_keywords", [])
        search_limit = self.config.get("search_limit", 20)
        print(f"  开始关键词搜索，共 {len(keywords)} 个关键词")
        for kw in keywords:
            query = f'"{kw}" -is:retweet lang:en min_faves:100'
            try:
                tweets = await asyncio.wait_for(gather(api.search(query, limit=search_limit)), timeout=30)
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

        accounts = self.config.get("watch_accounts", [])
        timeline_limit = self.config.get("timeline_limit", 5)
        min_faves = self.config.get("timeline_min_faves", 50)
        print(f"  开始账号时间线抓取，共 {len(accounts)} 个账号")
        for username in accounts:
            try:
                user = await asyncio.wait_for(api.user_by_login(username), timeout=15)
                if not user:
                    continue
                tweets = await asyncio.wait_for(gather(api.user_tweets(user.id, limit=timeline_limit)), timeout=30)
                new_count = 0
                for t in tweets:
                    if t.likeCount < min_faves:
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
            source_name=self.name,
            source_type=self.config.get("source_type", "TWEET"),
            content_type=self.config.get("content_type", "tweet"),
            author=tweet.user.username,
            author_url=f"https://x.com/{tweet.user.username}",
            body_text=tweet.rawContent,
            raw_metrics={"likes": tweet.likeCount, "retweets": tweet.retweetCount, "replies": tweet.replyCount, "views": tweet.viewCount or 0},
            extra={"tweet_id": str(tweet.id), "display_name": tweet.user.displayname, "verified": tweet.user.verified, "followers": tweet.user.followersCount},
            published_at=tweet.date,
        )
