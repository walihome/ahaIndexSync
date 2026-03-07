# scrapers/displayMetrics.py
#
# 配置说明：
#   - 按 content_type 分组（repo / article / tweet）
#   - key: 从 raw_metrics 或 extra 里取值的字段名
#   - label: 前端展示的文字
#   - format: 格式化方式
#       number   → 千分位数字，如 7,038
#       days_ago → 距今天数，如 "2天前"
#       date     → 日期，如 "2026/03/06"
#       text     → 原样输出

DISPLAY_METRICS_CONFIG = {

    "repo": [
        {"label": "⭐ Stars",  "key": "stars",      "format": "number"},
        {"label": "📅 创建",   "key": "created_at", "format": "days_ago"},
    ],

    "article": [
        {"label": "📅 发布",   "key": "published_at", "format": "date"},
    ],

    "tweet": [
        {"label": "❤️ 点赞",  "key": "likes",        "format": "number"},
        {"label": "🔁 转发",  "key": "retweets",     "format": "number"},
        {"label": "💬 回复",  "key": "replies",      "format": "number"},
    ],

    "news": [
        {"label": "▲ 热度",   "key": "score",        "format": "number"},
        {"label": "💬 评论",  "key": "comments",     "format": "number"},
    ],

}
