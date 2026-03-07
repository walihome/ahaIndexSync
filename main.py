# main.py

from datetime import datetime
from scrapers.github.trending import GitHubTrendingScraper
from scrapers.github.search import GitHubSearchScraper
from scrapers.news.hackernews import HackerNewsScraper
from scrapers.social.twitter import TwitterScraper
from scrapers.rss.rss_scraper import RSSFeedScraper
from scrapers.db import process_and_save

# 常规抓取器：统一 skip_ai_filter
SCRAPERS = [
    (GitHubTrendingScraper(), False),
    (GitHubSearchScraper(),   False),
    (HackerNewsScraper(),     False),
    (TwitterScraper(),        False),
]


def main():
    start_time = datetime.now()
    print(f"\n🚀 每日情报抓取启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = []  # (name, success, cost_seconds, error)

    # ── 1. 常规抓取器 ──────────────────────────────────────────
    print(f"\n📋 常规抓取器共 {len(SCRAPERS)} 个\n")
    for scraper, skip_filter in SCRAPERS:
        name = scraper.__class__.__name__
        print(f"{'─' * 40}")
        print(f"▶ {name}")
        t0 = datetime.now()
        try:
            items = scraper.fetch()
            print(f"  抓取到 {len(items)} 条原始数据")
            process_and_save(items, skip_ai_filter=skip_filter)
            cost = (datetime.now() - t0).seconds
            results.append((name, True, cost, None))
        except Exception as e:
            cost = (datetime.now() - t0).seconds
            results.append((name, False, cost, str(e)))
            print(f"  ❌ 失败: {e}")

    # ── 2. RSS 抓取器（每个 feed 独立 skip_ai_filter）─────────
    print(f"\n{'─' * 40}")
    print(f"▶ RSSFeedScraper")
    t0 = datetime.now()
    try:
        rss_scraper = RSSFeedScraper()
        rss_items = rss_scraper.fetch_all()  # [(RawItem, skip_ai_filter), ...]

        # 按 skip_ai_filter 分组
        need_filter = [item for item, skip in rss_items if not skip]
        skip_filter = [item for item, skip in rss_items if skip]

        if need_filter:
            process_and_save(need_filter, skip_ai_filter=False)
        if skip_filter:
            process_and_save(skip_filter, skip_ai_filter=True)

        cost = (datetime.now() - t0).seconds
        results.append((f"RSSFeedScraper ({len(rss_items)} 条)", True, cost, None))
    except Exception as e:
        cost = (datetime.now() - t0).seconds
        results.append(("RSSFeedScraper", False, cost, str(e)))
        print(f"  ❌ 失败: {e}")

    # ── 汇总 ──────────────────────────────────────────────────
    total_cost = (datetime.now() - start_time).seconds
    success_count = sum(1 for _, ok, _, _ in results if ok)
    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | {success_count}/{len(results)} 成功 | 总耗时 {total_cost}s")
    print(f"{'─' * 40}")
    for name, ok, cost, err in results:
        status = "✅" if ok else "❌"
        detail = f"{cost}s" if ok else f"{cost}s | {err}"
        print(f"  {status} {name:<40} {detail}")
    print(f"{'─' * 40}")
    print(f"   结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()
