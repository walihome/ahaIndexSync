# scrapers/rss/rss_config.py
#
# 字段说明：
#   name        - 来源名称，写入 source_name
#   url         - RSS Feed 地址（普通 RSS 直接填，Twitter 留空由代码拼接）
#   max_items   - 时间过滤后的条数上限，None 表示全量
#   source_tag  - 传给 AI 处理阶段，影响评分宽严
#   content_type - 内容类型，tweet / article 等
#   aggregate   - True 时走聚合模式，多条推文合并成一条摘要
#   twitter_user - Twitter 用户名（仅 Nitter RSS 使用）
#
# source_tag 取值：
#   official_ai    - AI 公司官方博客，权重最高
#   ai_research    - AI 学术/研究机构
#   tech_media     - 科技媒体
#   consumer_tech  - 消费科技
#   dev_community  - 开发者社区
#   engineering    - 工程领域
#   social         - 社交媒体（推文）

FETCH_WINDOW_HOURS = 25

# ── Nitter 实例配置 ──────────────────────────────────────────
# 按优先级排列，第一个失败会自动尝试下一个
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacyredirect.com",
]

# ── Twitter 账号列表 ─────────────────────────────────────────
# 在这里集中管理要抓取的 Twitter 账号
# url 字段留空，由 rss_scraper.py 根据 NITTER_INSTANCES 自动拼接
TWITTER_ACCOUNTS = [
    # AI 领域领袖
    {"twitter_user": "elonmusk",       "name": "Twitter @elonmusk",       "source_tag": "social"},
    {"twitter_user": "sama",           "name": "Twitter @sama",           "source_tag": "social"},
    {"twitter_user": "ylecun",         "name": "Twitter @ylecun",         "source_tag": "social"},
    {"twitter_user": "kaboris",        "name": "Twitter @kaboris",        "source_tag": "social"},

    # AI 公司 / 研究机构
    {"twitter_user": "OpenAI",         "name": "Twitter @OpenAI",         "source_tag": "official_ai"},
    {"twitter_user": "AnthropicAI",    "name": "Twitter @AnthropicAI",    "source_tag": "official_ai"},
    {"twitter_user": "GoogleDeepMind", "name": "Twitter @GoogleDeepMind", "source_tag": "official_ai"},
    {"twitter_user": "xaboratory",     "name": "Twitter @xaboratory",     "source_tag": "official_ai"},

    # AI 研究员 / 开发者
    {"twitter_user": "karpathy",       "name": "Twitter @karpathy",       "source_tag": "ai_research"},
    {"twitter_user": "goodaboris",     "name": "Twitter @goodaboris",     "source_tag": "ai_research"},
    {"twitter_user": "jimfan",         "name": "Twitter @jimfan",         "source_tag": "ai_research"},
    {"twitter_user": "swaboris",       "name": "Twitter @swaboris",       "source_tag": "ai_research"},
]

# 把 TWITTER_ACCOUNTS 转成统一的 feed 配置格式
_TWITTER_FEEDS = [
    {
        "name": acct["name"],
        "url": "",                          # 由 scraper 动态填充
        "twitter_user": acct["twitter_user"],
        "content_type": "tweet",
        "source_tag": acct.get("source_tag", "social"),
        "aggregate": True,
    }
    for acct in TWITTER_ACCOUNTS
]

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

    # ── Twitter (Nitter RSS) ─────────────────────────────────
    *_TWITTER_FEEDS,

]