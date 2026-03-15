"""
测试 Twitter RSS 服务在当前环境（本地/CI）里的可用性
运行方式：python test_twitter_rss.py
"""

import requests
import feedparser
from datetime import datetime, timezone, timedelta

TEST_ACCOUNT = "karpathy"   # 用一个账号快速验证
CUTOFF_HOURS = 72

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)

# 所有候选服务，按优先级排列
SERVICES = [
    ("nitter.net",              f"https://nitter.net/{TEST_ACCOUNT}/rss"),
    ("nitter.privacydev.net",   f"https://nitter.privacydev.net/{TEST_ACCOUNT}/rss"),
    ("nitter.poast.org",        f"https://nitter.poast.org/{TEST_ACCOUNT}/rss"),
    ("nitter.cz",               f"https://nitter.cz/{TEST_ACCOUNT}/rss"),
    ("nitter.1d4.us",           f"https://nitter.1d4.us/{TEST_ACCOUNT}/rss"),
    ("rsshub.app",              f"https://rsshub.app/twitter/user/{TEST_ACCOUNT}"),
    ("rsshub.rssforever.com",   f"https://rsshub.rssforever.com/twitter/user/{TEST_ACCOUNT}"),
]

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

print(f"🔍 测试 Twitter RSS 服务（账号: @{TEST_ACCOUNT}，时间窗口: {CUTOFF_HOURS}h）\n")

best_service = None

for name, url in SERVICES:
    try:
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code != 200:
            print(f"  ❌ {name}: HTTP {resp.status_code}")
            continue

        feed = feedparser.parse(resp.text)
        entries = feed.entries

        if not entries:
            print(f"  ⚠️  {name}: 无条目")
            continue

        # 统计近 72 小时内的内容
        recent = [
            e for e in entries
            if hasattr(e, "published_parsed") and e.published_parsed
            and datetime(*e.published_parsed[:6], tzinfo=timezone.utc) > cutoff
        ]

        latest_time = ""
        if entries[0].get("published_parsed"):
            latest_time = datetime(*entries[0].published_parsed[:6], tzinfo=timezone.utc).strftime("%m-%d %H:%M")

        print(f"  ✅ {name}: 共 {len(entries)} 条，{CUTOFF_HOURS}h 内 {len(recent)} 条，最新 {latest_time}")

        if recent:
            print(f"     示例: {entries[0].title[:60]}")

        if best_service is None and len(recent) > 0:
            best_service = (name, url.replace(f"/{TEST_ACCOUNT}/rss", "").replace(f"/twitter/user/{TEST_ACCOUNT}", ""))

    except Exception as e:
        print(f"  ❌ {name}: {e}")

print(f"\n{'═' * 50}")
if best_service:
    service_name, base_url = best_service
    print(f"🏆 推荐使用: {service_name}")
    print(f"\n以下是所有监控账号的 RSS 地址（复制到 rss_config.py）：\n")
    for account in WATCH_ACCOUNTS:
        if "rsshub" in service_name:
            rss_url = f"{base_url}/twitter/user/{account}"
        else:
            rss_url = f"{base_url}/{account}/rss"
        print(f'    {{"name": "Twitter @{account}", "url": "{rss_url}", "max_items": 3, "source_tag": "social", "content_type": "tweet"}},')
else:
    print("❌ 所有服务均不可用，建议使用本地 twscrape 方案")
