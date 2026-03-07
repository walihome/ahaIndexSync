# scrapers/social/twitter.py
#
# 依赖: pip install twscrape
# 首次使用需要添加 Twitter 账号:
#   python -m twscrape add_accounts accounts.txt
#   python -m twscrape login_all
#
# accounts.txt 格式（每行一个账号）:
#   username:password:email:email_password

import os
import asyncio
from datetime import datetime, timezone, timedelta
from twscrape import API, gather
from twscrape.logger import set_log_level
from ..base import BaseScraper, RawItem


# ── 配置区 ────────────────────────────────────────────────────

# 关键词搜索：抓热点推文
# 过滤转推、限定英文、要求一定互动量
SEARCH_QUERIES = [
    "LLM OR \"large language model\" -is:retweet lang:en min_faves:100",
    "\"AI agent\" OR \"agentic AI\" -is:retweet lang:en min_faves:100",
    "\"fine-tuning\" OR \"RAG\" OR \"vector database\" -is:retweet lang:en min_faves:200",
    "\"context window\" OR \"reasoning model\" -is:retweet lang:en min_faves:100",
    "Claude OR Gemini OR GPT-5 -is:retweet lang:en min_faves:300",
]

# 指定账号时间线：高质量 AI 领域博主
WATCH_ACCOUNTS = [
    "karpathy",       # Andrej Karpathy
    "sama",           # Sam Altman
    "anthropic",      # Anthropic 官号
    "openai",         # OpenAI 官号
    "demishassabis",  # DeepMind CEO
    "ylecun",         # Yann LeCun
    "drjimfan",       # NVIDIA Jim Fan
    "scaling01",      # Scaling AI
    "rohanpaul_ai",   # AI 研究博主
    "svpino",         # Santiago ML
]

# 每个关键词最多抓多少条
SEARCH_LIMIT = 20
# 每个账号最多抓最近多少条
TIMELINE_LIMIT = 5
# 最低点赞数过滤（timeline 用，search 已在 query 里限制）
TIMELINE_MIN_FAVES = 50
# 只抓最近几天内的推文
MAX_AGE_DAYS = 2

# twscrape 账号数据库路径（持久化登录状态）
ACCOUNTS_DB = os.path.join(os.path.dirname(__file__), "../../.twscrape_accounts.db")


# ── Scraper ───────────────────────────────────────────────────

class TwitterScraper(BaseScraper):
    source_name = "X (Twitter)"
    source_type = "TWEET"
    content_type = "tweet"

    def fetch(self) -> list[RawItem]:
        try:
            return asyncio.run(self._fetch_all())
        except Exception as e:
            print(f"[TwitterScraper] 运行失败: {e}")
            return []

    async def _fetch_all(self) -> list[RawItem]:
        set_log_level("ERROR")  # 减少 twscrape 的噪音日志
        api = API(ACCOUNTS_DB)

        seen: set[str] = set()
        items: list[RawItem] = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

        # ── 1. 关键词搜索 ──────────────────────────────────────
        for query in SEARCH_QUERIES:
            try:
                tweets = await gather(api.search(query, limit=SEARCH_LIMIT))
                new_count = 0
                for t in tweets:
                    item = self._to_raw_item(t, cutoff, seen)
                    if item:
                        items.append(item)
                        new_count += 1
                print(f"  [搜索] {query[:50]}... → 新增 {new_count} 条")
            except Exception as e:
                print(f"  [搜索] 失败 ({query[:40]}...): {e}")

        # ── 2. 指定账号时间线 ──────────────────────────────────
        for username in WATCH_ACCOUNTS:
            try:
                tweets = await gather(api.user_tweets(
                    await self._get_user_id(api, username),
                    limit=TIMELINE_LIMIT
                ))
                new_count = 0
                for t in tweets:
                    if t.likeCount < TIMELINE_MIN_FAVES:
                        continue
                    item = self._to_raw_item(t, cutoff, seen)
                    if item:
                        items.append(item)
                        new_count += 1
                print(f"  [时间线] @{username} → 新增 {new_count} 条")
            except Exception as e:
                print(f"  [时间线] @{username} 失败: {e}")

        print(f"  抓取到 {len(items)} 条推文（去重后）")
        return items

    async def _get_user_id(self, api: API, username: str) -> int:
        user = await api.user_by_login(username)
        if not user:
            raise Exception(f"找不到用户: {username}")
        return user.id

    def _to_raw_item(self, tweet, cutoff: datetime, seen: set) -> RawItem | None:
        """把 twscrape Tweet 对象转成 RawItem，过滤旧推文和重复"""
        url = f"https://x.com/{tweet.user.username}/status/{tweet.id}"

        if url in seen:
            return None
        if tweet.date < cutoff:
            return None
        # 跳过纯转推（没有自己内容）
        if tweet.retweetedTweet is not None:
            return None

        seen.add(url)

        return RawItem(
            title=tweet.rawContent[:100],  # 推文前100字作为标题
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


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
    from scrapers.db import process_and_save
    scraper = TwitterScraper()
    items = scraper.fetch()
    print(f"共抓到 {len(items)} 条，开始处理...")
    process_and_save(items, skip_ai_filter=False)
