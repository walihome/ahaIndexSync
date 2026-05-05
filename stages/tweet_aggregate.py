# stages/tweet_aggregate.py
"""
Twitter 推文聚合阶段
--------------------
在 scrape 之后、fetch_content 之前运行。
将当天所有 tweet 类型的 raw_items 聚合为一条 tweet_digest。
"""

from __future__ import annotations

import hashlib
from datetime import date

from supabase import Client
from pipeline.config_loader import PipelineConfig
from infra.db import table_names, upsert_raw_item, get_supabase
from infra.models import RawItem


def _aggregate_id(snapshot_date: str) -> str:
    """确定性 ID：同一天的 digest 始终相同。"""
    return hashlib.md5(f"tweet_digest:{snapshot_date}".encode()).hexdigest()


def run_tweet_aggregate(
    sb: Client,
    config: PipelineConfig,
    table_suffix: str = "",
    snapshot_date: date | None = None,
) -> dict:
    raw_table, _, _, content_table = table_names(table_suffix)
    today = snapshot_date or date.today()
    today_str = today.isoformat()

    # 读取当天所有 tweet 类型的 raw_items
    rows = (
        sb.table(raw_table)
        .select("*")
        .eq("snapshot_date", today_str)
        .eq("content_type", "tweet")
        .execute()
        .data
        or []
    )

    if not rows:
        print("  📭 无推文，跳过聚合")
        return {"aggregated": 0}

    # 聚合指标
    total_likes = 0
    total_retweets = 0
    total_replies = 0
    total_views = 0
    tweets = []

    for r in rows:
        rm = r.get("raw_metrics") or {}
        if isinstance(rm, str):
            import json
            try:
                rm = json.loads(rm)
            except Exception:
                rm = {}

        likes = rm.get("likes", 0) or 0
        retweets = rm.get("retweets", 0) or 0
        replies = rm.get("replies", 0) or 0
        views = rm.get("views", 0) or 0

        total_likes += likes
        total_retweets += retweets
        total_replies += replies
        total_views += views

        ext = r.get("extra") or {}
        if isinstance(ext, str):
            import json
            try:
                ext = json.loads(ext)
            except Exception:
                ext = {}

        tweets.append({
            "author": r.get("author", ""),
            "display_name": ext.get("display_name", ""),
            "text": r.get("title", ""),  # title 是推文前 100 字
            "likes": likes,
            "retweets": retweets,
            "url": r.get("original_url", ""),
            "tweet_id": ext.get("tweet_id", ""),
        })

    # 按 likes 排序
    tweets.sort(key=lambda t: t["likes"], reverse=True)

    # 生成标题：取 top 3 作者
    top_authors = list(dict.fromkeys(t["author"] for t in tweets if t["author"]))[:3]
    author_str = "、".join(f"@{a}" for a in top_authors) if top_authors else "AI 圈"
    title = f"{author_str} 等 {len(tweets)} 条推文热议"

    # 构造 digest item
    digest_id = _aggregate_id(today_str)
    body_text = "\n\n".join(
        f"@{t['author']}: {t['text']}" for t in tweets
    )

    # 删除原始 tweet items
    tweet_ids = [r["id"] for r in rows]
    if tweet_ids:
        # 分批删除（Supabase 限制）
        batch_size = 100
        for i in range(0, len(tweet_ids), batch_size):
            batch = tweet_ids[i:i + batch_size]
            sb.table(raw_table).delete().in_("id", batch).execute()
        # 同时删除 items_content 中的对应记录
        for i in range(0, len(tweet_ids), batch_size):
            batch = tweet_ids[i:i + batch_size]
            sb.table(content_table).delete().in_("item_id", batch).execute()

    # 插入聚合后的 digest
    digest = RawItem(
        title=title,
        original_url=f"tweet_digest://{today_str}",
        source_name="X (Twitter)",
        source_type="TWEET",
        content_type="tweet_digest",
        author=", ".join(top_authors),
        body_text=body_text,
        raw_metrics={
            "likes": total_likes,
            "retweets": total_retweets,
            "replies": total_replies,
            "views": total_views,
            "tweet_count": len(tweets),
        },
        extra={
            "tweets": tweets,
        },
        published_at=today,
        snapshot_date=today,
    )
    upsert_raw_item(digest, raw_table)

    print(f"  🐦 聚合 {len(tweets)} 条推文 → 1 条 digest（❤️ {total_likes} 🔁 {total_retweets}）")
    return {"aggregated": len(tweets), "digest_id": digest_id}
