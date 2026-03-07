# scrapers/rss/rss_feeds_config.py
#
# 字段说明：
#   name           - 来源名称，写入 source_name
#   url            - RSS Feed 地址
#   max_items      - 每次最多召回条数，None 表示全量（适合官方博客）
#                    注意：max_items 是时间过滤之后的上限
#   skip_ai_filter - True 跳过关键词过滤（天然 AI 相关），False 走过滤
#   source_tag     - 来源标签，传给 AI 提示词，影响评分宽严

# ── 全局时间窗口（小时）──────────────────────────────────────
# 只保留此时间范围内发布的文章，避免每日重复
# 设为 25 而非 24，留 1 小时余量防止边界漏抓
FETCH_WINDOW_HOURS = 25
#
# source_tag 取值约定：
#   official_ai    - AI 公司官方博客，权重最高，评分宽松
#   ai_research    - AI 学术/研究机构，论文摘要，评分宽松
#   tech_media     - 科技媒体，需判断相关性
#   consumer_tech  - 消费科技，标准更严
#   dev_community  - 开发者社区
#
# 学术来源说明：
#   Google Scholar 和 IEEE 通过 RSSHub 公共实例拉取，若不稳定建议自建 RSSHub
#   自建文档：https://docs.rsshub.app/install/

RSS_FEEDS = [

    # ── AI 官方博客（全量召回，跳过过滤）─────────────────────
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/news/rss.xml",
        "max_items": None,
        "skip_ai_filter": True,
        "source_tag": "official_ai",
    },
    {
        "name": "Anthropic Blog",
        "url": "https://www.anthropic.com/rss.xml",
        "max_items": None,
        "skip_ai_filter": True,
        "source_tag": "official_ai",
    },
    {
        "name": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "max_items": None,
        "skip_ai_filter": True,
        "source_tag": "official_ai",
    },
    {
        "name": "Meta AI Blog",
        "url": "https://ai.meta.com/blog/rss/",
        "max_items": None,
        "skip_ai_filter": True,
        "source_tag": "official_ai",
    },

    # ── 科技媒体（限量 + 关键词过滤）────────────────────────
    {
        "name": "36氪",
        "url": "https://36kr.com/feed",
        "max_items": 3,
        "skip_ai_filter": False,
        "source_tag": "tech_media",
    },
    {
        "name": "奇客Solidot",
        "url": "https://www.solidot.org/index.rss",
        "max_items": 3,
        "skip_ai_filter": False,
        "source_tag": "tech_media",
    },
    {
        "name": "IT之家",
        "url": "https://www.ithome.com/rss/",
        "max_items": 2,
        "skip_ai_filter": False,
        "source_tag": "tech_media",
    },

    # ── 消费科技（标准更严，最多 1 条）──────────────────────
    {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "max_items": 1,
        "skip_ai_filter": False,
        "source_tag": "consumer_tech",
    },

    # ── 开发者社区────────────────────────────────────────────
    {
        "name": "V2EX",
        "url": "https://v2ex.com/index.xml",
        "max_items": 2,
        "skip_ai_filter": False,
        "source_tag": "dev_community",
    },

]
