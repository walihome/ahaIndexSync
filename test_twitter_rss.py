"""
测试 Twitter RSS 服务在当前环境（本地/CI）里的可用性
运行方式：python test_twitter_rss.py
"""

import requests
import feedparser
from datetime import datetime, timezone, timedelta

CUTOFF_HOURS = 72
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)

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

BASE_URL = "https://nitter.net"

print(f"🔍 测试 nitter.net 各账号情况（时间窗口: {CUTOFF_HOURS}h）\n")

total_recent = 0
active_accounts = []

for account in WATCH_ACCOUNTS:
    url = f"{BASE_URL}/{account}/rss"
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  ❌ @{account}: HTTP {resp.status_code}")
            continue

        feed = feedparser.parse(resp.text)
        entries = feed.entries

        if not entries:
            print(f"  ⚠️  @{account}: 无条目")
            continue

        recent = [
            e for e in entries
            if hasattr(e, "published_parsed") and e.published_parsed
            and datetime(*e.published_parsed[:6], tzinfo=timezone.utc) > cutoff
        ]

        latest_time = ""
        if entries[0].get("published_parsed"):
            latest_time = datetime(*entries[0].published_parsed[:6], tzinfo=timezone.utc).strftime("%m-%d %H:%M")

        status = "✅" if recent else "😴"
        print(f"  {status} @{account}: 共 {len(entries)} 条，{CUTOFF_HOURS}h 内 {len(recent)} 条，最新 {latest_time}")
        if recent:
            print(f"     → {recent[0].title[:70]}")
            active_accounts.append(account)
            total_recent += len(recent)

    except Exception as e:
        print(f"  ❌ @{account}: {e}")

print(f"\n{'═' * 50}")
print(f"📊 汇总：{len(active_accounts)}/{len(WATCH_ACCOUNTS)} 个账号有近 {CUTOFF_HOURS}h 内容，共 {total_recent} 条")
if active_accounts:
    print(f"   活跃账号: {', '.join('@' + a for a in active_accounts)}")
