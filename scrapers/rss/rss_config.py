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

# source_tag 取值约定：
#   official_ai    - AI 公司官方博客，权重最高，评分宽松
#   ai_research    - AI 学术/研究机构，论文/周报
#   tech_media     - 科技媒体，需判断相关性
#   consumer_tech  - 消费科技，标准更严
#   dev_community  - 开发者社区
#   engineering    - 工程领域，关注大变更/新范式

RSS_FEEDS = [

    # ── AI 官方博客（限量 + 跳过过滤）────────────────────────
    # OpenAI RSS 包含历史全量文章（878条），依赖时间窗口过滤，保底限 10 条
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/news/rss.xml",
        "max_items": 10,
        "skip_ai_filter": True,
        "source_tag": "official_ai",
    },
    # DeepMind 同理，限 5 条
    {
        "name": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss.xml",
        "max_items": 5,
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
        "name": "虎嗅",
        "url": "https://www.huxiu.com/rss/0.xml",
        "max_items": 2,
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

    # ── AI 研究/学术（天然相关，跳过过滤）───────────────────
    {
        # 每日精选 AI 论文，Huggingface 社区投票，质量极高
        "name": "Huggingface Daily Papers",
        "url": "https://rsshub.app/huggingface/daily-papers",
        "max_items": 5,
        "skip_ai_filter": True,
        "source_tag": "ai_research",
    },
    {
        "name": "Huggingface 中文博客",
        "url": "https://rsshub.app/huggingface/blog-zh",
        "max_items": 3,
        "skip_ai_filter": True,
        "source_tag": "ai_research",
    },
    {
        # 吴恩达团队 AI 周报，每周一期
        "name": "deeplearning.ai TheBatch",
        "url": "https://rsshub.app/deeplearning/thebatch",
        "max_items": 3,
        "skip_ai_filter": True,
        "source_tag": "ai_research",
    },
    {
        # 国内顶级 AI 研究院，智源社区活动/论文动态
        "name": "北京智源 BAAI",
        "url": "https://rsshub.app/baai/hub/events",
        "max_items": 2,
        "skip_ai_filter": False,
        "source_tag": "ai_research",
    },

    # ── 工程领域大变更────────────────────────────────────────
    {
        # 云原生/容器领域，K8s、Service Mesh、eBPF 等范式变化
        "name": "CNCF Blog",
        "url": "https://rsshub.app/cncf/blog",
        "max_items": 2,
        "skip_ai_filter": False,
        "source_tag": "engineering",
    },
    {
        # Google 工程博客，Web 性能/标准/浏览器 API 重大变化
        "name": "web.dev",
        "url": "https://rsshub.app/web/blog",
        "max_items": 2,
        "skip_ai_filter": False,
        "source_tag": "engineering",
    },

]
