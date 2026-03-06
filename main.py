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
```

---

## 未来加新抓取器只需两步

1. 新建 `scrapers/xxx/yyy.py` 实现 `fetch()`
2. 在 `main.py` 的 `SCRAPERS` 列表加一行

Actions 的 workflow 文件**完全不用动**，入口永远是 `python main.py`。

---

## 目录结构最终全貌
```
.
├── main.py
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily.yml          # 你现有的 Actions，不用改
└── scrapers/
    ├── __init__.py
    ├── base.py                # RawItem 数据类 + BaseScraper 基类
    ├── db.py                  # 所有写库 + AI 加工逻辑
    ├── github/
    │   ├── __init__.py
    │   ├── trending.py
    │   └── search.py
    ├── ai_blogs/
    │   ├── __init__.py
    │   ├── openai.py
    │   └── anthropic.py
    ├── news/
    │   ├── __init__.py
    │   └── hackernews.py
    └── social/
        ├── __init__.py
        └── twitter.py
