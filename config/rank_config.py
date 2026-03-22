# config/rank_config.py
# 精排分组配置
#
# 字段说明：
#   group        - 展示分组名
#   sources      - 归入这组的 source_name 列表
#   limit        - 最多展示几条
#   must_include - True = 只要有内容就一定展示，不会因为分组逻辑被跳过
#
# 所有分组统一使用 AI 多维度打分，raw_metrics 作为参考传入 prompt

RANK_GROUPS = [
    {
        "group": "官方动态",
        "sources": [
            "Anthropic Blog",
            "OpenAI Blog",
            "Mistral AI Blog",
            "xAI Blog",
            "Cohere Blog",
            "Stability AI Blog",
        ],
        "limit": 5,
        "must_include": True,   # AI 官方动态必须展示
    },
    {
        "group": "开源项目",
        "sources": ["GitHub Trending", "GitHub Search"],
        "limit": 10,
        "must_include": False,
    },
    {
        "group": "技术社区",
        "sources": ["HackerNews"],
        "limit": 10,
        "must_include": False,
    },
    {
        "group": "社交热点",
        "sources": [
            "X (Twitter)",
            "Twitter @anthropic", "Twitter @openai", "Twitter @GoogleDeepMind",
            "Twitter @MetaAI", "Twitter @MistralAI", "Twitter @xai",
            "Twitter @huggingface", "Twitter @nvidia",
            "Twitter @sama", "Twitter @karpathy", "Twitter @ylecun",
            "Twitter @demishassabis", "Twitter @GaryMarcus", "Twitter @emollick",
            "Twitter @drjimfan", "Twitter @bindureddy", "Twitter @ilyasut",
            "Twitter @svpino", "Twitter @hardmaru", "Twitter @fchollet",
            "Twitter @jeremyphoward", "Twitter @alexalbert__", "Twitter @swyx",
            "Twitter @kaifulee", "Twitter @drfeifei",
        ],
        "limit": 5,
        "must_include": False,
    },
    {
        "group": "学术论文",
        "sources": ["Huggingface Daily Papers"],
        "limit": 5,
        "must_include": False,
    },
    {
        "group": "工程动态",
        "sources": ["CNCF Blog", "Chrome Developers Blog"],
        "limit": 3,
        "must_include": False,
    },
    {
        "group": "平台动态",
        "sources": ["Apple Developer News"],
        "limit": 2,
        "must_include": True,   # 苹果开发者政策/规范必须展示
    },
    {
        "group": "国内资讯",
        "sources": ["虎嗅", "V2EX", "奇客Solidot"],
        "limit": 1,
        "must_include": False,
    },
]