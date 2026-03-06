# main.py

from datetime import datetime
from scrapers.github.trending import GitHubTrendingScraper
from scrapers.github.search import GitHubSearchScraper
from scrapers.ai_blogs.openai import OpenAIBlogScraper
from scrapers.ai_blogs.anthropic import AnthropicBlogScraper
from scrapers.news.hackernews import HackerNewsScraper
from scrapers.db import process_and_save

# 注册所有抓取器
# skip_ai_filter=True 表示该来源天然 AI 相关，跳过关键词过滤
SCRAPERS = [
    (GitHubTrendingScraper(),  False),
    (GitHubSearchScraper(),    False),
    (OpenAIBlogScraper(),      True),
    (AnthropicBlogScraper(),   True),
    (HackerNewsScraper(),      False),
]

def main():
    print(f"\n🚀 每日情报抓取启动 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"📋 共 {len(SCRAPERS)} 个抓取器\n")

    total_success = 0
    for scraper, skip_filter in SCRAPERS:
        name = scraper.source_name
        print(f"{'─' * 40}")
        print(f"▶ 开始: {name}")
        try:
            items = scraper.fetch()
            print(f"  抓取到 {len(items)} 条原始数据")
            process_and_save(items, skip_ai_filter=skip_filter)
            total_success += 1
        except Exception as e:
            # 单个抓取器失败不影响其他的继续跑
            print(f"  ❌ {name} 整体失败: {e}")

    print(f"\n{'─' * 40}")
    print(f"✨ 完成 | 成功 {total_success}/{len(SCRAPERS)} 个抓取器")
    print(f"   结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

if __name__ == "__main__":
    main()
