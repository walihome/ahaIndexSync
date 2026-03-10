# infra/display_metrics.py
# 前端展示字段组装，根据 content_type 配置决定展示哪些指标

from datetime import datetime, timezone
from .models import RawItem

# key: 从 raw_metrics 或 extra 里取值
# format: number / days_ago / date / text
DISPLAY_METRICS_CONFIG = {
    "repo": [
        {"label": "⭐ Stars",  "key": "stars",      "format": "number"},
        {"label": "📅 创建",   "key": "created_at", "format": "days_ago"},
    ],
    "article": [
        {"label": "📅 发布",   "key": "published_at", "format": "date"},
    ],
    "tweet": [
        {"label": "❤️ 点赞",  "key": "likes",    "format": "number"},
        {"label": "🔁 转发",  "key": "retweets", "format": "number"},
        {"label": "💬 回复",  "key": "replies",  "format": "number"},
    ],
    "news": [
        {"label": "▲ 热度",   "key": "score",    "format": "number"},
        {"label": "💬 评论",  "key": "comments", "format": "number"},
    ],
}


def build_display_metrics(item: RawItem) -> dict:
    config = DISPLAY_METRICS_CONFIG.get(item.content_type, [])
    data = {
        **item.extra,
        **item.raw_metrics,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "source_name": item.source_name,
    }

    result = []
    for field in config:
        key = field["key"]
        fmt = field["format"]
        val = data.get(key)
        if val is None:
            continue

        if fmt == "number":
            display = f"{int(val):,}"
        elif fmt == "days_ago":
            created = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - created).days
            display = "今天" if days == 0 else f"{days} 天前"
        elif fmt == "date":
            display = str(val)[:10].replace("-", "/")
        else:
            display = str(val)

        result.append({"label": field["label"], "value": display})

    return {"items": result}