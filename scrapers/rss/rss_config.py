# scrapers/rss/rss_config.py
#
# 字段说明：
#   name        - 来源名称，写入 source_name
#   url         - RSS Feed 地址
#   max_items   - 时间过滤后的条数上限，None 表示全量
#   source_tag  - 传给 AI 处理阶段，影响评分宽严
#
# source_tag 取值：
#   official_ai    - AI 公司官方博客，权重最高
#   ai_research    - AI 学术/研究机构
#   tech_media     - 科技媒体
#   consumer_tech  - 消费科技
#   dev_community  - 开发者社区
#   engineering    - 工程领域

FETCH_WINDOW_HOURS = 25

RSS_FEEDS = [

    # ── AI 官方博客 ───────────────────────────────────────────
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/news/rss.xml",
        "max_items": 10,
        "source_tag": "official_ai",
    },
    {
        "name": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "max_items": 5,
        "source_tag": "official_ai",
    },

    # ── 科技媒体 ──────────────────────────────────────────────
    {
        "name": "36氪",
        "url": "https://36kr.com/feed",
        "max_items": 3,
        "source_tag": "tech_media",
    },
    {
        "name": "虎嗅",
        "url": "https://www.huxiu.com/rss/0.xml",
        "max_items": 2,
        "source_tag": "tech_media",
    },
    {
        "name": "奇客Solidot",
        "url": "https://www.solidot.org/index.rss",
        "max_items": 3,
        "source_tag": "tech_media",
    },
    {
        "name": "IT之家",
        "url": "https://www.ithome.com/rss/",
        "max_items": 2,
        "source_tag": "tech_media",
    },

    # ── 消费科技 ──────────────────────────────────────────────
    {
        "name": "少数派",
        "url": "https://sspai.com/feed",
        "max_items": 1,
        "source_tag": "consumer_tech",
    },

    # ── 开发者社区 ────────────────────────────────────────────
    {
        "name": "V2EX",
        "url": "https://v2ex.com/index.xml",
        "max_items": 2,
        "source_tag": "dev_community",
    },

    # ── AI 研究/学术 ──────────────────────────────────────────
    {
        "name": "Huggingface Daily Papers",
        "url": "https://raw.githubusercontent.com/huangboming/huggingface-daily-paper-feed/refs/heads/main/feed.xml",
        "max_items": 5,
        "source_tag": "ai_research",
    },

    # ── 工程领域 ──────────────────────────────────────────────
    {
        "name": "CNCF Blog",
        "url": "https://www.cncf.io/feed/",
        "max_items": 2,
        "source_tag": "engineering",
    },
    {
        "name": "Chrome Developers Blog",
        "url": "https://developer.chrome.com/static/blog/feed.xml",
        "max_items": 2,
        "source_tag": "engineering",
    },

]