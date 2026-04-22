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
│   ├── coarse_filter.py            # 粗排：去重 + aha 阈值 + 死链
│   ├── enrich.py                   # 第二层内容增厚（并发 + 超时 + 容错）
│   ├── subject.py                  # Subject 资产（upsert + mention 登记）
│   ├── rank.py                     # AI 打分精排 → display_items
│   └── archive.py                  # 归档 daily/weekly/monthly
│
├── enrichers/                      # 内容增厚引擎（插件式，通过 registry 注册）
│   ├── registry.py                 # enricher_name → class 映射（也决定执行顺序）
│   ├── base.py                     # BaseEnricher / EnrichmentResult / SubjectCandidate
│   ├── cross_reference.py          # 纯 DB：历史轨迹 + 同日交叉引用
│   ├── hn_comments.py              # Algolia 评论树 → LLM 社区情绪/替代方案
│   ├── github_ecosystem.py         # topics 搜索 → LLM 竞品/成熟度
│   └── _utils.py                   # URL 解析、GitHub slug 构造
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
    ├── 002_seed_data.sql
    ├── 003_enrich_and_subject_tables.sql        # 生产：Enrich + Subject 4 张新表
    ├── 003_enrich_and_subject_tables_test.sql   # 测试：同结构 + _test 后缀
    └── 004_enrich_seed.sql                       # Enrich 的 prompts + params（全局共享）
```

测试方式：`TABLE_SUFFIX=_test python main.py --suffix _test`，Scrape/Process/Coarse/Enrich/Rank 的所有读写都会落到 `_test` 表，与生产完全隔离。

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
| `item_enrichments` | 第二层增厚数据（社区反馈 / 竞品 / 历史） |
| `subjects` | 被追踪的事物（project/product/org/person/concept） |
| `subject_mentions` | item 与 subject 的多对多关联 |
| `subject_aliases` | 人工 slug 合并通道 |

## 执行流程

```
1. 从 Supabase 加载全部配置 → PipelineConfig 快照
2. 创建 pipeline_run 记录
3. Stage 1: Scrape（遍历 enabled scrapers）
4. Stage 2: Process（AI 加工 pending items）
5. Stage 3a: Coarse Filter（去重 + aha 阈值 + 死链）
6. Stage 3b: Enrich（第二层增厚：cross_ref / hn_comments / gh_ecosystem）
   - 单 enricher 独立容错 + 整体超时兜底，不可能阻塞主管道
   - 同时产出 subject 候选（V1 仅自动创建 github:owner/repo）
7. Stage 4: Rank（读取 enrichment + subject 历史，AI 打分精排）
8. Stage 5: Archive（归档，仅生产模式）
9. 更新 pipeline_run 状态和统计
```

### Enrich 相关参数（`pipeline_params`）

| key | 默认 | 说明 |
|---|---|---|
| `enrich_enabled` | `true` | 一键关闭 Enrich 阶段 |
| `enrich_timeout` | `3600` | Enrich 总体超时秒数 |
| `enrich_max_workers` | `5` | item 级并发线程数 |
| `coarse_filter_min_aha` | `0.25` | 粗排 aha_index 下限 |

## 本地运行

```bash
pip install -r requirements.txt
export SUPABASE_URL=xxx
export SUPABASE_SERVICE_ROLE_KEY=xxx
export KIMI_API_KEY=xxx
export GH_MODELS_TOKEN=xxx          # 供 github_search / github_ecosystem 使用
python main.py
```

## 新增数据源

1. 在 Supabase `scraper_configs` 表中新增一行（指定已有的 scraper_type）
2. 如果需要新引擎类型：在 `scrapers/` 下新建文件，用 `@register("new_type")` 注册
