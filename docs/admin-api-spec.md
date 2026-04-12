# ahaIndexAdmin 后端修改说明

> 基于 ahaIndexSync 配置驱动架构重构，ahaIndexAdmin 需要提供以下 7 张配置表 + 2 张监控表的 CRUD 管理界面。

---

## 一、Supabase 表总览

| 表名 | 类型 | 说明 | Admin 操作 |
|---|---|---|---|
| `scraper_configs` | 配置 | 抓取源配置 | 完整 CRUD |
| `prompt_templates` | 配置 | Prompt 模板 | 完整 CRUD |
| `rank_group_configs` | 配置 | 精排分组 | 完整 CRUD |
| `tag_slot_configs` | 配置 | 特殊标签名额 | 完整 CRUD |
| `pipeline_params` | 配置 | 全局参数 KV | 完整 CRUD |
| `display_metrics_configs` | 配置 | 展示指标配置 | 完整 CRUD |
| `content_fetch_rules` | 配置 | 正文补全规则 | 完整 CRUD |
| `pipeline_runs` | 监控(只读) | Pipeline 执行记录 | 列表 + 详情 |
| `scraper_runs` | 监控(只读) | Scraper 执行记录 | 列表（按 pipeline_run 筛选） |

---

## 二、各表字段定义 & 表单设计

### 1. scraper_configs — 抓取源配置

这是最核心的表。每行代表"一个抓取引擎 + 一套参数"。同一个引擎类型可以有多行配置。

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | 主键 | 隐藏 |
| `scraper_type` | TEXT | ✅ | 引擎类型（选择框） | Select |
| `name` | TEXT | ✅ | 显示名称，会写入 raw_items.source_name | Input |
| `enabled` | BOOLEAN | ✅ | 是否启用 | Switch |
| `priority` | INT | ✅ | 执行优先级（越小越先执行） | NumberInput |
| `config` | JSONB | ✅ | 引擎专属参数 | JSON Editor |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读显示 |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读显示 |

#### scraper_type 枚举值

| 值 | 说明 | config JSON schema |
|---|---|---|
| `github_trending` | GitHub Trending 页面 | `{ source_type, content_type, timeout }` |
| `github_search` | GitHub Search API | `{ source_type, content_type, queries: [{q, label}], per_page, fetch_window_days, badge_patterns, max_readme_images }` |
| `hackernews` | HackerNews | `{ source_type, content_type, new_n, min_score, cutoff_hours, fetch_workers, skip_domains }` |
| `rss` | RSS Feed（通用） | `{ source_type, content_type, url, max_items, source_tag, fetch_window_hours }` |
| `twitter_twscrape` | Twitter (twscrape) | `{ source_type, content_type, watch_accounts, tracked_keywords, search_limit, timeline_limit, timeline_min_faves, max_age_days }` |
| `twitter_nitter` | Twitter (Nitter RSS) | `{ source_type, content_type, twitter_user, source_tag, aggregate, nitter_instances, fetch_window_hours }` |
| `ai_blog` | AI 公司博客 HTML | `{ source_type, content_type, base_url, news_url, link_selector, author, source_tag, fetch_window_hours }` |
| `community_v2ex` | V2EX 热议 | `{ source_type, content_type, top_n, max_replies_to_fetch, max_replies_to_keep, source_tag }` |
| `community_linuxdo` | LINUX DO 热议 | `{ source_type, content_type, top_n, max_replies_to_fetch, source_tag }` |

#### 各引擎 config 字段详细说明

**通用字段（所有引擎都有）：**
- `source_type`: 来源类型标识，写入 raw_items.source_type。可选值 `"REPO"` / `"BLOG"` / `"NEWS"` / `"TWEET"` / `"ARTICLE"`
- `content_type`: 内容类型标识，写入 raw_items.content_type。可选值 `"repo"` / `"article"` / `"tweet"` / `"tweet_digest"` / `"v2ex_hot"` / `"linuxdo_hot"` / `"news"`

**`rss` 引擎特有字段：**
- `url` (string, 必填): RSS Feed URL
- `max_items` (int, 可选): 每次最多抓取条数，null 表示不限
- `source_tag` (string): 来源标签，影响 AI 处理阶段的行为。可选值 `"official_ai"` / `"ai_research"` / `"tech_media"` / `"consumer_tech"` / `"dev_community"` / `"engineering"` / `"social"`
- `fetch_window_hours` (int): 时间窗口（小时），只抓取该时间段内的内容

**`github_search` 引擎特有字段：**
- `queries` (array): 搜索查询列表，每项 `{q: "查询字符串", label: "说明"}`。查询字符串中 `{last_week}` 会被替换为 7 天前的日期
- `per_page` (int): 每个查询的结果数
- `fetch_window_days` (int): 搜索时间窗口（天）
- `badge_patterns` (string[]): 要过滤的 badge/噪音图片域名
- `max_readme_images` (int): 每个 repo 最多提取的 README 图片数

**`hackernews` 引擎特有字段：**
- `new_n` (int): 读取最近多少条 new stories
- `min_score` (int): 最低分数门槛
- `cutoff_hours` (int): 时间截止（小时）
- `fetch_workers` (int): 并发抓正文的线程数
- `skip_domains` (string[]): 跳过正文抓取的域名

**`twitter_twscrape` 引擎特有字段：**
- `watch_accounts` (string[]): 监控的 Twitter 用户名列表
- `tracked_keywords` (string[]): 搜索关键词列表
- `search_limit` (int): 每个关键词的搜索结果数
- `timeline_limit` (int): 每个账号的时间线抓取条数
- `timeline_min_faves` (int): 时间线推文最低点赞数
- `max_age_days` (int): 最大时间范围（天）

**`twitter_nitter` 引擎特有字段：**
- `twitter_user` (string, 必填): Twitter 用户名
- `aggregate` (boolean): true = 聚合多条推文为一条摘要，false = 逐条处理
- `nitter_instances` (string[]): Nitter 实例 URL 列表（按顺序尝试）
- `fetch_window_hours` (int): 时间窗口（小时）

**`ai_blog` 引擎特有字段：**
- `base_url` (string): 网站根域名，如 `"https://www.anthropic.com"`
- `news_url` (string): 博客列表页 URL
- `link_selector` (string): CSS 选择器，用于从列表页提取文章链接
- `author` (string): 作者名
- `fetch_window_hours` (int): 时间窗口（小时），0 表示不做时间过滤

**`community_v2ex` 引擎特有字段：**
- `top_n` (int): 对前 N 条帖子补抓点击数
- `max_replies_to_fetch` (int): 通过 API 获取的评论条数上限
- `max_replies_to_keep` (int): 最终保留的精选评论数

**`community_linuxdo` 引擎特有字段：**
- `top_n` (int): 补抓评论的帖子数
- `max_replies_to_fetch` (int): 获取的评论条数上限

#### 列表页展示建议

| 列 | 说明 |
|---|---|
| name | 显示名 |
| scraper_type | 引擎类型（用 Tag/Badge） |
| enabled | 开关 |
| priority | 优先级 |
| updated_at | 最近更新 |

---

### 2. prompt_templates — Prompt 模板

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | 主键 | 隐藏 |
| `name` | TEXT | ✅ | 唯一标识名 | Input（不可重复） |
| `stage` | TEXT | ✅ | 所属阶段 | Select: `process` / `rank` / `archive` |
| `template` | TEXT | ✅ | Prompt 文本，支持 `{variable}` 占位符 | Textarea / Code Editor（大文本） |
| `model` | TEXT | ✅ | LLM 模型名 | Input，默认 `kimi-k2.5` |
| `model_base_url` | TEXT | ✅ | API Base URL | Input，默认 `https://api.moonshot.cn/v1` |
| `temperature` | FLOAT | ✅ | 温度参数 | NumberInput (0-2)，默认 0.3 |
| `max_retries` | INT | ✅ | 最大重试次数 | NumberInput，默认 3 |
| `request_interval` | FLOAT | ✅ | 请求间隔秒数 | NumberInput，默认 0.5 |
| `enabled` | BOOLEAN | ✅ | 是否启用 | Switch |
| `version` | INT | ✅ | 版本号 | NumberInput，默认 1 |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读 |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### 已有的 name 值（种子数据）

| name | stage | 用途 |
|---|---|---|
| `process_system` | process | AI 处理的 system prompt |
| `process_main` | process | AI 处理的主 prompt（含所有编辑指令） |
| `rank_system` | rank | 精排 AI 的 system prompt |
| `rank_idea` | rank | 优先关注的内容方向（注入到打分 prompt） |
| `rank_scoring` | rank | 完整评分体系（注入到打分 prompt） |
| `rank_candidate` | rank | 打分请求的模板，含 `{group}`, `{count}`, `{idea_guide}`, `{scoring_guide}`, `{candidate_text}` 占位符 |
| `archive_monthly_summary` | archive | 月度摘要生成 prompt，含 `{year}`, `{month}`, `{avg_score}`, `{top_stories}` 占位符 |

#### 模板占位符说明

Pipeline 在运行时用 `template.replace("{variable}", value)` 进行替换。

**process_main 可用占位符：**
- `{source_name}` — 来源名
- `{source_tag}` — 来源标签
- `{title}` — 标题
- `{body_text}` — 正文（截取前 800 字）
- `{raw_metrics}` — 原始指标 JSON

**rank_candidate 可用占位符：**
- `{group}` — 当前分组名
- `{count}` — 候选数量
- `{idea_guide}` — rank_idea 模板内容
- `{scoring_guide}` — rank_scoring 模板内容
- `{candidate_text}` — 候选内容文本

**archive_monthly_summary 可用占位符：**
- `{year}` — 年
- `{month}` — 月
- `{avg_score}` — 月均 Aha Score
- `{top_stories}` — Top Story 列表文本

#### 编辑建议

template 字段内容可能很长（如 rank_scoring 有 3000+ 字符），建议用 **Markdown 预览** 或 **Code Editor**（带行号）展示。

---

### 3. rank_group_configs — 精排分组

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | | 隐藏 |
| `group_name` | TEXT | ✅ | 分组名称，如 "官方动态" | Input |
| `source_names` | TEXT[] | ✅ | 匹配的 source_name 列表 | TagInput / MultiSelect |
| `limit` | INT | ✅ | 该组最多选几条 | NumberInput |
| `must_include` | BOOLEAN | ✅ | 是否必须展示 | Switch |
| `sort_order` | INT | ✅ | 排列顺序（越小越靠前） | NumberInput |
| `enabled` | BOOLEAN | ✅ | 是否启用 | Switch |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读 |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### source_names 取值说明

`source_names` 数组中的值必须与 `scraper_configs.name` 匹配。Pipeline 在精排阶段按 source_name 匹配 processed_items 到分组。

**建议**：Admin 端可以提供一个下拉框，从 `scraper_configs` 中拉取所有 `name` 值作为候选项。

#### 列表页展示建议

支持拖拽排序（按 sort_order），或者在表格中直接编辑 sort_order。

---

### 4. tag_slot_configs — 特殊标签名额

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | | 隐藏 |
| `tag_name` | TEXT | ✅ | 标签名（UNIQUE） | Input |
| `max_slots` | INT | ✅ | 每日上限条数 | NumberInput |
| `min_score` | FLOAT | ✅ | 保底替换的最低 AI 分数 | NumberInput |
| `enabled` | BOOLEAN | ✅ | 是否启用 | Switch |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读 |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### 已有标签

| tag_name | 含义 | 当前 max_slots |
|---|---|---|
| `gossip` | AI 圈八卦 | 1 |
| `deal` | 优惠福利 | 1 |
| `macro` | 跨界大事件 | 2 |
| `incident` | 宕机/故障 | 1 |
| `lifestyle` | 好物推荐 | 1 |

---

### 5. pipeline_params — 全局参数 KV

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `key` | TEXT | ✅ | 参数名（主键） | Input |
| `value` | JSONB | ✅ | 参数值 | Input / NumberInput |
| `description` | TEXT | | 说明 | Input |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### 已有参数

| key | value | description |
|---|---|---|
| `scraper_timeout` | `120` | 每个 scraper 的超时秒数 |
| `process_max_workers` | `3` | AI 处理并发线程数 |
| `link_check_max_workers` | `10` | 链接检查并发线程数 |
| `fetch_window_hours` | `24` | raw_items 时间窗口（小时） |

注意 value 是 JSONB，但当前都是简单数字。

---

### 6. display_metrics_configs — 展示指标配置

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | | 隐藏 |
| `content_type` | TEXT | ✅ | 内容类型（UNIQUE） | Input |
| `metrics` | JSONB | ✅ | 指标配置数组 | JSON Editor |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读 |
| `updated_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### metrics JSON 结构

```json
[
  { "label": "⭐ Stars", "key": "stars", "format": "number" },
  { "label": "📅 创建", "key": "created_at", "format": "days_ago" }
]
```

- `label`: 前端展示文字
- `key`: 从 raw_metrics 或 extra 中取值的字段名
- `format`: 格式化方式，可选 `number`（千分位）/ `days_ago`（距今天数）/ `date`（日期）/ `text`（原样）

#### 已有配置

| content_type | metrics |
|---|---|
| `repo` | Stars (number), 创建 (days_ago) |
| `article` | 发布 (date) |
| `tweet` | 点赞/转发/回复 (number) |
| `news` | 热度/评论 (number) |

---

### 7. content_fetch_rules — 正文补全规则

#### 字段

| 字段 | 类型 | 必填 | 说明 | 表单控件 |
|---|---|---|---|---|
| `id` | UUID | 自动 | | 隐藏 |
| `rule_type` | TEXT | ✅ | 规则类型 | Select: `skip_domain` / `fetch_fulltext_tag` |
| `value` | TEXT | ✅ | 值 | Input |
| `enabled` | BOOLEAN | ✅ | 是否启用 | Switch |
| `created_at` | TIMESTAMPTZ | 自动 | | 只读 |

#### rule_type 说明

- `skip_domain`: Pipeline 在补全正文时跳过该域名（如 `twitter.com`）
- `fetch_fulltext_tag`: Pipeline 对带有该 source_tag 的内容主动抓取全文（如 `official_ai`）

---

### 8. pipeline_runs — Pipeline 执行记录（只读）

#### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `run_type` | TEXT | `daily` / `test` / `manual` |
| `status` | TEXT | `running` / `success` / `failed` |
| `table_suffix` | TEXT | 表后缀，空为生产 |
| `started_at` | TIMESTAMPTZ | 开始时间 |
| `finished_at` | TIMESTAMPTZ | 结束时间（running 时为 null） |
| `config_snapshot` | JSONB | 执行时的配置快照 |
| `stats` | JSONB | 统计数据 `{ scraped, processed, ranked, archived, errors }` |
| `error` | TEXT | 失败时的错误信息 |

#### 列表页展示建议

- 按 `started_at DESC` 排序
- status 用颜色 Tag：running=蓝色, success=绿色, failed=红色
- 耗时 = `finished_at - started_at`
- 点击展开查看 `config_snapshot` 和 `stats`

---

### 9. scraper_runs — Scraper 执行记录（只读）

#### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 主键 |
| `pipeline_run_id` | UUID | FK → pipeline_runs |
| `scraper_config_id` | UUID | FK → scraper_configs |
| `scraper_type` | TEXT | 引擎类型 |
| `scraper_name` | TEXT | 抓取源名称 |
| `status` | TEXT | `success` / `failed` / `timeout` / `skipped` |
| `items_fetched` | INT | 抓取条数 |
| `items_saved` | INT | 写入 DB 条数 |
| `started_at` | TIMESTAMPTZ | 开始时间 |
| `finished_at` | TIMESTAMPTZ | 结束时间 |
| `error` | TEXT | 错误信息 |

#### 展示方式

在 pipeline_runs 的详情页中，展示该次运行的所有 scraper_runs（按 started_at 排序）。

---

## 三、Admin 页面结构建议

```
├── 数据源管理 (/scrapers)
│   ├── 列表页：所有 scraper_configs，支持 enabled 切换、新增、编辑
│   └── 编辑页：根据 scraper_type 显示不同的 config 表单
│
├── Prompt 管理 (/prompts)
│   ├── 列表页：按 stage 分组展示
│   └── 编辑页：大文本编辑器，支持占位符高亮
│
├── 排序规则 (/ranking)
│   ├── 分组管理 (rank_group_configs)：支持拖拽排序
│   └── 标签名额 (tag_slot_configs)
│
├── 系统设置 (/settings)
│   ├── 全局参数 (pipeline_params)
│   ├── 展示指标 (display_metrics_configs)
│   └── 正文规则 (content_fetch_rules)
│
└── 执行监控 (/runs)
    ├── Pipeline 执行列表 (pipeline_runs)
    └── 详情页：含 scraper_runs 子表 + stats + config_snapshot
```

---

## 四、关键交互逻辑

### 1. scraper_configs 编辑页

根据用户选择的 `scraper_type`，动态渲染 config JSON 的表单。

例如选择 `rss` 时显示：
- URL 输入框
- max_items 数字框
- source_tag 选择框
- fetch_window_hours 数字框

选择 `github_search` 时显示：
- queries 动态列表（每行：q + label）
- per_page 数字框
- etc.

也可以简单处理：直接用 JSON Editor 编辑 config 字段，附带该 scraper_type 的 schema 文档/示例。

### 2. rank_group_configs 的 source_names

这个字段是 Postgres text[] 数组。Admin 提交时需要传数组格式。

从 Supabase JS 客户端操作：
```js
await supabase
  .from('rank_group_configs')
  .update({ source_names: ['GitHub Trending', 'GitHub Search'] })
  .eq('id', id)
```

### 3. pipeline_params 的 value

value 是 JSONB 类型，但当前都是简单数字字符串。提交时需要确保是合法 JSON：
```js
// 正确
{ value: 120 }
// 或
{ value: "120" }
```

### 4. 数据关联

- `rank_group_configs.source_names` 中的值 ↔ `scraper_configs.name`
- `scraper_runs.pipeline_run_id` ↔ `pipeline_runs.id`
- `scraper_runs.scraper_config_id` ↔ `scraper_configs.id`

---

## 五、Supabase 连接信息

- URL: `https://wyhpcfjtmtitorinkevj.supabase.co`
- Anon Key: `sb_publishable_Mhngg1gf4z4dkj-xh5TsMg_Pz3crwfo`

Admin 前端使用 anon key 即可（确保表的 RLS 策略允许）。如果需要写操作，建议配置 RLS 或使用 service_role key 通过后端代理。

---

## 六、已有表（不需要 Admin 管理，仅参考）

这些是 Pipeline 写入的数据表，ahaIndex2 前端会读取：

| 表名 | 说明 |
|---|---|
| `raw_items` | 原始抓取数据 |
| `processed_items` | AI 加工后的数据 |
| `display_items` | 精排后的展示数据 |
| `daily_archives` | 每日归档 |
| `weekly_archives` | 每周归档 |
| `monthly_archives` | 每月归档 |
