# config/rank_config.py
# 精排分组配置
#
# 字段说明：
#   group        - 展示分组名
#   sources      - 归入这组的 source_name 列表
#   limit        - 最多展示几条，None = 全量
#   sort_by      - 排序字段，从 {aha_index, **raw_metrics} 打平后取值
#   ai_rerank    - True = 让大模型从候选里选出最值得推的 limit 条
#   must_include - True = 只要有内容就一定展示，不会因为分组逻辑被跳过

RANK_GROUPS = [
    {
        "group": "官方动态",
        "sources": [
            "Anthropic Blog",
            "OpenAI Blog",
            "Google DeepMind Blog",
            "Meta AI Blog",
            "Mistral AI Blog",
            "xAI Blog",
            "Cohere Blog",
            "Stability AI Blog",
        ],
        "limit": 3,
        "sort_by": "aha_index",
        "ai_rerank": False,
        "must_include": True,   # AI 官方动态必须展示
    },
    {
        "group": "开源项目",
        "sources": ["GitHub Trending", "GitHub Search"],
        "limit": 10,
        "sort_by": "stars",
        "ai_rerank": False,
        "must_include": False,
    },
    {
        "group": "技术社区",
        "sources": ["HackerNews"],
        "limit": 10,
        "sort_by": "score",
        "ai_rerank": False,
        "must_include": False,
    },
    {
        "group": "社交热点",
        "sources": ["X (Twitter)"],
        "limit": 5,
        "sort_by": "likes",
        "ai_rerank": False,
        "must_include": False,
    },
    {
        "group": "学术论文",
        "sources": ["Huggingface Daily Papers"],
        "limit": 5,
        "sort_by": "aha_index",
        "ai_rerank": False,
        "must_include": False,
    },
    {
        "group": "工程动态",
        "sources": ["CNCF Blog", "Chrome Developers Blog"],
        "limit": 3,
        "sort_by": "aha_index",
        "ai_rerank": False,
        "must_include": False,
    },
    {
        "group": "平台动态",
        "sources": ["Apple Developer News"],
        "limit": 2,
        "sort_by": "aha_index",
        "ai_rerank": False,
        "must_include": True,   # 苹果开发者政策/规范必须展示
    },
    {
        "group": "国内资讯",
        "sources": ["少数派", "IT之家", "虎嗅", "36氪", "V2EX", "奇客Solidot"],
        "limit": 1,
        "sort_by": "aha_index",
        "ai_rerank": True,
        "must_include": False,
    },
]
