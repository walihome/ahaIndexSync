# config/rank_config.py
# 精排分组配置
# 定义哪些 source 归入哪个展示分组，以及每组的截断和排序规则
#
# sort_by 说明：
#   "aha_index"         - AI 打分
#   "stars"             - GitHub stars（raw_metrics 字段）
#   "score"             - HN score（raw_metrics 字段）
#   "likes"             - Twitter 点赞（raw_metrics 字段）
#   所有字段运行时从 {aha_index, **raw_metrics} 打平后取值
#
# ai_rerank 说明：
#   False - 直接按 sort_by 排序取 top limit 条
#   True  - 把候选全部喂给大模型，让它选出最值得推的 limit 条并重新生成摘要

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
        "limit": 5,
        "sort_by": "aha_index",
        "ai_rerank": False,
    },
    {
        "group": "开源项目",
        "sources": ["GitHub Trending", "GitHub Search"],
        "limit": 10,
        "sort_by": "stars",
        "ai_rerank": False,
    },
    {
        "group": "技术社区",
        "sources": ["HackerNews"],
        "limit": 10,
        "sort_by": "score",
        "ai_rerank": False,
    },
    {
        "group": "社交热点",
        "sources": ["X (Twitter)"],
        "limit": 5,
        "sort_by": "likes",
        "ai_rerank": False,
    },
    {
        "group": "学术论文",
        "sources": ["Huggingface Daily Papers"],
        "limit": 5,
        "sort_by": "aha_index",
        "ai_rerank": False,
    },
    {
        "group": "工程动态",
        "sources": ["CNCF Blog", "Chrome Developers Blog"],
        "limit": 3,
        "sort_by": "aha_index",
        "ai_rerank": False,
    },
    {
        "group": "国内资讯",
        "sources": ["少数派", "IT之家", "虎嗅", "36氪", "V2EX", "奇客Solidot"],
        "limit": 1,
        "sort_by": "aha_index",
        "ai_rerank": True,   # 大模型从候选里选最值得推的1条并重新总结
    },
]
