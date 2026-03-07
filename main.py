# main.py

from datetime import datetime
from scrapers.github.trending import GitHubTrendingScraper
from scrapers.github.search import GitHubSearchScraper
from scrapers.ai_blogs.openai import OpenAIBlogScraper
from scrapers.ai_blogs.anthropic import AnthropicBlogScraper
from scrapers.news.hackernews import HackerNewsScraper
from scrapers.social.twitter import TwitterScraper
from scrapers.db import process_and_save

# 注册所有抓取器
# skip_ai_filter=True 表示该来源天然 AI 相关，跳过关键词过滤
SCRAPERS = [
    (GitHubTrendingScraper(),  False),
    (GitHubSearchScraper(),    False),
    (OpenAIBlogScraper(),      True),
    (AnthropicBlogScraper(),   True),
    (HackerNewsScraper(),      False),
    (TwitterScraper(),         False),
]


def main():
    start_time = datetime.now()
    print(f"\n🚀 每日情报抓取启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 共 {len(SCRAPERS)} 个抓取器\n")

    results = []  # (name, success, cost_seconds, error)

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

    # 汇总
    total_cost = (datetime.now() - start_time).seconds
    success_count = sum(1 for _, ok, _, _ in results if ok)
    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | {success_count}/{len(SCRAPERS)} 成功 | 总耗时 {total_cost}s")
    print(f"{'─' * 40}")
    for name, ok, cost, err in results:
        status = "✅" if ok else "❌"
        detail = f"{cost}s" if ok else f"{cost}s | {err}"
        print(f"  {status} {name:<30} {detail}")
    print(f"{'─' * 40}")
    print(f"   结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()
