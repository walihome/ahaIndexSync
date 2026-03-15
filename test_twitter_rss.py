"""
测试 Nitter RSS 可用性
- 逐个实例 × 逐个账号测试
- 输出每个组合的 HTTP 状态、条目数、最新推文
- 最后汇总哪些实例可用
"""

import requests
import feedparser
from datetime import datetime, timezone, timedelta

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TIMEOUT = 10

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
]

TEST_ACCOUNTS = [
    "elonmusk",
    "sama",
    "karpathy",
    "OpenAI",
    "AnthropicAI",
]

CUTOFF = datetime.now(timezone.utc) - timedelta(hours=24)


def parse_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def test_feed(instance: str, user: str) -> dict:
    url = f"{instance}/{user}/rss"
    result = {"instance": instance, "user": user, "url": url}

    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        result["status"] = resp.status_code

        if resp.status_code != 200:
            result["ok"] = False
            result["error"] = f"HTTP {resp.status_code}"
            return result

        feed = feedparser.parse(resp.text)
        entries = feed.entries
        result["total_entries"] = len(entries)

        # 过滤转推，统计原创
        original = [e for e in entries if not (getattr(e, "title", "") or "").strip().startswith("RT by @")]
        result["original_entries"] = len(original)

        # 24h 内的原创
        recent = []
        for e in original:
            pub = parse_date(e)
            if pub and pub >= CUTOFF:
                recent.append((pub, e))
        result["recent_24h"] = len(recent)

        # 最新一条预览
        if recent:
            recent.sort(key=lambda x: x[0], reverse=True)
            pub, e = recent[0]
            age_min = int((datetime.now(timezone.utc) - pub).total_seconds() / 60)
            title = (getattr(e, "title", "") or "")[:80]
            result["latest"] = f"[{age_min}分钟前] {title}"

        result["ok"] = len(entries) > 0
        return result

    except requests.Timeout:
        result["ok"] = False
        result["error"] = "超时"
        return result
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)[:100]
        return result


def main():
    print("=" * 70)
    print("Nitter RSS 可用性测试")
    print(f"时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"测试账号: {', '.join(TEST_ACCOUNTS)}")
    print(f"测试实例: {len(NITTER_INSTANCES)} 个")
    print("=" * 70)

    # instance → 成功账号数
    instance_scores: dict[str, int] = {inst: 0 for inst in NITTER_INSTANCES}

    for instance in NITTER_INSTANCES:
        print(f"\n{'─' * 70}")
        print(f"▶ 实例: {instance}")
        print(f"{'─' * 70}")

        for user in TEST_ACCOUNTS:
            r = test_feed(instance, user)

            if r["ok"]:
                instance_scores[instance] += 1
                total = r.get("total_entries", 0)
                orig = r.get("original_entries", 0)
                recent = r.get("recent_24h", 0)
                latest = r.get("latest", "无")
                print(f"  ✅ @{user:20s} | 共 {total} 条, 原创 {orig}, 24h内 {recent}")
                if latest != "无":
                    print(f"     最新: {latest}")
            else:
                err = r.get("error", "未知错误")
                print(f"  ❌ @{user:20s} | {err}")

    # ── 汇总 ──
    print(f"\n{'=' * 70}")
    print("汇总")
    print(f"{'=' * 70}")

    total_accounts = len(TEST_ACCOUNTS)
    for instance in NITTER_INSTANCES:
        score = instance_scores[instance]
        pct = score / total_accounts * 100
        status = "✅" if score == total_accounts else ("⚠️" if score > 0 else "❌")
        print(f"  {status} {instance:45s} {score}/{total_accounts} ({pct:.0f}%)")

    # 推荐排序
    ranked = sorted(NITTER_INSTANCES, key=lambda x: instance_scores[x], reverse=True)
    best = ranked[0]
    best_score = instance_scores[best]

    print(f"\n推荐实例优先级:")
    for i, inst in enumerate(ranked, 1):
        print(f"  {i}. {inst} ({instance_scores[inst]}/{total_accounts})")

    if best_score == 0:
        print("\n⚠️ 所有实例均不可用，请检查 Nitter 服务状态")
        print("  参考: https://status.d420.de/")


if __name__ == "__main__":
    main()