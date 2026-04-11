# ahaIndexSync

数据采集 → AI 加工 → 写入 Supabase。仅负责数据入库，不涉及静态文件生成、OSS 同步或 CDN 刷新（这些由 ahaIndex2 负责）。

## 项目目录结构

```
.
├── scrape.py                      # 抓取入口，只负责 fetch → upsert raw_items
├── process.py                     # 处理入口，只负责 raw→processed AI加工
├── rank.py                        # 排序入口，dedup + AI 打分 → display_items
├── generate_archives.py           # 归档入口，display_items → daily/weekly/monthly archives
│
├── config/
│   └── tracked_keywords.py        # 全局关键词配置，所有 scraper 共享
│
├── infra/
│   ├── models.py                  # RawItem 数据模型定义
│   ├── db.py                      # 纯数据库读写，不含业务逻辑
│   ├── llm.py                     # AI 处理逻辑
│   ├── content_fetcher.py         # 正文抓取/补全
│   ├── display_metrics.py         # 前端展示字段组装
│   └── time_utils.py              # 时间窗口工具
│
└── scrapers/
    ├── registry.py                # 自动发现所有 scraper
    ├── github/
    │   ├── trending.py
    │   └── search.py
    ├── news/
    │   └── hackernews.py
    ├── social/
    │   └── twitter.py
    ├── rss/
    │   ├── rss_scraper.py
    │   └── rss_config.py
    └── ai_blogs/
        ├── anthropic.py
        ├── cohere.py
        ├── mistral.py
        └── stability_ai.py
```

## 核心原则

- `scrape.py` 只写 raw_items，不做任何 AI 处理
- `process.py` 只读 raw_items diff，加工写 processed_items
- `rank.py` 打分排序写 display_items
- `generate_archives.py` 聚合归档数据写 Supabase
- `scrapers/` 里的每个文件只依赖 `infra.models`，不依赖 db/llm
- 新增数据源：在对应目录新建文件，继承 BaseScraper，实现 fetch()，完毕
- 新增关注方向：在 config/tracked_keywords.py 加一行关键词
