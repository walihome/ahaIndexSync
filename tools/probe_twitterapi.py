#!/usr/bin/env python3
"""TwitterAPI.io 响应探测脚本 — 验证字段名、日期格式、分页结构。"""

import json
import sys
import httpx

API_KEY = sys.argv[1] if len(sys.argv) > 1 else ""
if not API_KEY:
    print("用法: python tools/probe_twitterapi.py <API_KEY>")
    sys.exit(1)

BASE = "https://api.twitterapi.io"
HEADERS = {"X-API-Key": API_KEY}


def probe_user_timeline(username: str):
    print(f"\n{'='*60}")
    print(f"接入点 1: 用户时间线 — @{username}")
    print(f"{'='*60}")
    resp = httpx.get(
        f"{BASE}/twitter/user/last_tweets",
        params={"userName": username},
        headers=HEADERS,
        timeout=30.0,
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    # 打印顶层 key
    print(f"顶层 keys: {list(data.keys())}")
    tweets = data.get("tweets", [])
    print(f"tweets 数量: {len(tweets)}")
    if tweets:
        print(f"\n--- 第 1 条推文完整字段 ---")
        print(json.dumps(tweets[0], indent=2, ensure_ascii=False))
        # 检查分页字段
        print(f"\n--- 分页字段 ---")
        print(f"has_next_page: {data.get('has_next_page')} (type={type(data.get('has_next_page')).__name__})")
        print(f"next_cursor:   {data.get('next_cursor')} (type={type(data.get('next_cursor')).__name__})")
    return data


def probe_advanced_search(query: str):
    print(f"\n{'='*60}")
    print(f"接入点 2: 高级搜索 — query={query!r}")
    print(f"{'='*60}")
    resp = httpx.get(
        f"{BASE}/twitter/tweet/advanced_search",
        params={"query": query, "queryType": "Latest"},
        headers=HEADERS,
        timeout=30.0,
    )
    print(f"Status: {resp.status_code}")
    data = resp.json()
    print(f"顶层 keys: {list(data.keys())}")
    tweets = data.get("tweets", [])
    print(f"tweets 数量: {len(tweets)}")
    if tweets:
        print(f"\n--- 第 1 条推文完整字段 ---")
        print(json.dumps(tweets[0], indent=2, ensure_ascii=False))
        print(f"\n--- 分页字段 ---")
        print(f"has_next_page: {data.get('has_next_page')} (type={type(data.get('has_next_page')).__name__})")
        print(f"next_cursor:   {data.get('next_cursor')} (type={type(data.get('next_cursor')).__name__})")
    return data


def verify_field_mapping(tweet: dict):
    """验证我们代码中的字段映射是否与实际响应一致。"""
    print(f"\n{'='*60}")
    print("字段映射验证")
    print(f"{'='*60}")
    checks = [
        ("id",            tweet.get("id")),
        ("url",           tweet.get("url")),
        ("text",          tweet.get("text")),
        ("createdAt",     tweet.get("createdAt")),
        ("likeCount",     tweet.get("likeCount")),
        ("retweetCount",  tweet.get("retweetCount")),
        ("replyCount",    tweet.get("replyCount")),
        ("quoteCount",    tweet.get("quoteCount")),
        ("viewCount",     tweet.get("viewCount")),
        ("isReply",       tweet.get("isReply")),
        ("lang",          tweet.get("lang")),
    ]
    author = tweet.get("author") or {}
    author_checks = [
        ("author.userName",       author.get("userName")),
        ("author.id",             author.get("id")),
        ("author.name",           author.get("name")),
        ("author.isBlueVerified", author.get("isBlueVerified")),
        ("author.followers",      author.get("followers")),
    ]
    all_ok = True
    for name, val in checks + author_checks:
        status = "✅" if val is not None else "⚠️  MISSING"
        if val is None:
            all_ok = False
        print(f"  {status} {name} = {val!r}")
    if all_ok:
        print("\n所有字段均存在，映射无误。")
    else:
        print("\n部分字段缺失，代码中已做容错处理（默认 0 / False / ''）。")


if __name__ == "__main__":
    # 1) 用户时间线
    data1 = probe_user_timeline("sama")
    if data1.get("tweets"):
        verify_field_mapping(data1["tweets"][0])

    # 2) 高级搜索
    data2 = probe_advanced_search('"AI agent" -is:retweet lang:en min_faves:100')
    if data2.get("tweets"):
        verify_field_mapping(data2["tweets"][0])

    print("\n✅ 探测完成")
