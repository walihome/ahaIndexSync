# ahaIndexSync

配置驱动的 AI 日报数据采集 Pipeline。从多源抓取 → AI 加工 → 精排 → 写入 Supabase。

所有配置（抓取源、prompt、排序规则、参数）均存储在 Supabase 配置表中，通过 ahaIndexAdmin 管理。

## 架构

```
main.py                             # 统一入口
├── pipeline/
│   ├── config_loader.py            # 从 Supabase 加载全部配置
│   ├── runner.py                   # Pipeline 编排器
│   └── run_tracker.py              # 执行追踪（pipeline_runs / scraper_runs）
│
├── stages/                         # Pipeline 各阶段
│   ├── scrape.py                   # 遍历 scraper_configs → 实例化引擎 → 抓取
│   ├── process.py                  # AI 处理 raw_items → processed_items
│   ├── rank.py                     # AI 打分精排 → display_items
│   └── archive.py                  # 归档 daily/weekly/monthly
│
├── scrapers/                       # 抓取引擎（纯代码，配置从 DB 注入）
│   ├── registry.py                 # scraper_type → class 映射
│   ├── github_trending.py
│   ├── github_search.py
│   ├── hackernews.py
│   ├── rss_feed.py
│   ├── twitter_twscrape.py
│   ├── twitter_nitter.py
│   ├── ai_blog.py
│   ├── community_v2ex.py
│   └── community_linuxdo.py
│
├── infra/                          # 基础设施
│   ├── db.py                       # Supabase client + CRUD
│   ├── llm.py                      # LLM 通用调用
│   ├── models.py                   # RawItem + BaseScraper
│   ├── content_fetcher.py          # 正文补全
│   ├── display_metrics.py          # 展示指标组装
│   ├── link_checker.py             # 链接可访问性检查
│   └── time_utils.py               # 时间窗口工具
│
└── sql/                            # 建表 + 种子数据
    ├── 001_config_tables.sql
    └── 002_seed_data.sql
```

## 配置表

| 表 | 用途 |
|---|---|
| `scraper_configs` | 抓取源配置（引擎类型 + 参数 JSON） |
| `prompt_templates` | 所有 Prompt 模板（含模型、温度等） |
| `rank_group_configs` | 精排分组定义 |
| `tag_slot_configs` | 特殊标签每日名额 |
| `pipeline_params` | 全局参数 KV |
| `display_metrics_configs` | 前端展示指标 |
| `content_fetch_rules` | 正文补全规则 |
| `pipeline_runs` | Pipeline 执行记录 |
| `scraper_runs` | 单个 Scraper 执行记录 |

## 执行流程

```
1. 从 Supabase 加载全部配置 → PipelineConfig 快照
2. 创建 pipeline_run 记录
3. Stage 1: Scrape（遍历 enabled scrapers）
4. Stage 2: Process（AI 加工 pending items）
5. Stage 3: Rank（AI 打分精排）
6. Stage 4: Archive（归档，仅生产模式）
7. 更新 pipeline_run 状态和统计
```

## 本地运行

```bash
pip install -r requirements.txt
export SUPABASE_URL=xxx
export SUPABASE_SERVICE_ROLE_KEY=xxx
export KIMI_API_KEY=xxx
python main.py
```

## 新增数据源

1. 在 Supabase `scraper_configs` 表中新增一行（指定已有的 scraper_type）
2. 如果需要新引擎类型：在 `scrapers/` 下新建文件，用 `@register("new_type")` 注册
