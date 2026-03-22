# scrapers/community/v2ex_hot.py
#
# 抓取 V2EX 今日热议：评论最多的 1 条 + 点击最多的 1 条
# 如果两条是同一个帖子，合并为 1 条
# 同时抓取热门讨论内容（top N 评论）

import re
import requests
from datetime import datetime, timezone
from infra.models import BaseScraper, RawItem

V2EX_HOT_API = "https://www.v2ex.com/api/topics/hot.json"
V2EX_REPLIES_API = "https://www.v2ex.com/api/replies/show.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# 抓取帖子页面的前 N 条评论（通过 API）
MAX_REPLIES_TO_FETCH = 30
# 最终保留的精选评论数
MAX_REPLIES_TO_KEEP = 15


def _fetch_hot_topics() -> list[dict]:
    """调用 V2EX hot API，返回热门帖子列表"""
    try:
        resp = requests.get(V2EX_HOT_API, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ V2EX hot API 返回 {resp.status_code}")
            return []
        return resp.json()
    except Exception as e:
        print(f"  ⚠️ V2EX hot API 失败: {e}")
        return []


def _fetch_clicks(topic_url: str) -> int:
    """从帖子网页解析点击数"""
    try:
        resp = requests.get(topic_url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return 0
        # 匹配 "2506 次点击" 或 "12345 次点击"
        match = re.search(r'(\d+)\s*次点击', resp.text)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def _fetch_replies(topic_id: int) -> list[dict]:
    """通过 API 获取帖子评论"""
    try:
        resp = requests.get(
            V2EX_REPLIES_API,
            params={"topic_id": topic_id, "p": 1},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        replies = resp.json()
        return replies[:MAX_REPLIES_TO_FETCH] if isinstance(replies, list) else []
    except Exception:
        return []


def _clean_html(text: str) -> str:
    """去掉 HTML 标签"""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _build_discussion_text(topic: dict, replies: list[dict]) -> str:
    """
    拼装讨论内容：
    - 原帖正文
    - 精选评论（按点赞数排序取 top N）
    """
    lines = []

    # 原帖
    content = _clean_html(topic.get("content_rendered") or topic.get("content") or "")
    if content:
        lines.append(f"【原帖】{content}")
        lines.append("")

    if not replies:
        return "\n".join(lines)

    # 按点赞数（thanked）排序，取精华评论
    # V2EX API 的 reply 没有 thanked 字段，按顺序取前 N 条
    # 如果有 thanked 字段则优先按点赞排序
    sorted_replies = sorted(
        replies,
        key=lambda r: r.get("thanked", 0),
        reverse=True,
    )

    top_replies = sorted_replies[:MAX_REPLIES_TO_KEEP]

    lines.append(f"【热门讨论】（共 {topic.get('replies', 0)} 条回复，精选 {len(top_replies)} 条）")
    lines.append("")

    for r in top_replies:
        author = r.get("member", {}).get("username", "匿名")
        text = _clean_html(r.get("content_rendered") or r.get("content") or "")
        if not text:
            continue
        thanked = r.get("thanked", 0)
        prefix = f"👍{thanked} " if thanked else ""
        lines.append(f"{prefix}@{author}: {text}")
        lines.append("")

    return "\n".join(lines)


def _build_raw_item(topic: dict, clicks: int, replies_text: str, tag: str) -> RawItem:
    """构建 RawItem"""
    topic_id = topic["id"]
    title = topic.get("title", "")
    url = topic.get("url") or f"https://www.v2ex.com/t/{topic_id}"
    author = topic.get("member", {}).get("username", "")
    node_name = topic.get("node", {}).get("title", "")
    replies_count = topic.get("replies", 0)
    content = _clean_html(topic.get("content_rendered") or topic.get("content") or "")

    return RawItem(
        title=title,
        original_url=url,
        source_name="V2EX",
        source_type="ARTICLE",
        content_type="v2ex_hot",
        author=author,
        author_url=f"https://www.v2ex.com/member/{author}" if author else "",
        body_text=replies_text or content,
        raw_metrics={
            "replies": replies_count,
            "clicks": clicks,
        },
        extra={
            "topic_id": topic_id,
            "node": node_name,
            "hot_tag": tag,  # "most_replied" / "most_clicked" / "most_replied_and_clicked"
            "source_tag": "dev_community",
        },
        published_at=datetime.fromtimestamp(
            topic.get("created", 0), tz=timezone.utc
        ) if topic.get("created") else None,
    )


class V2EXHotScraper(BaseScraper):
    source_name = "V2EX"
    source_type = "ARTICLE"
    content_type = "v2ex_hot"

    def fetch(self) -> list[RawItem]:
        # 1. 获取热门帖子
        topics = _fetch_hot_topics()
        if not topics:
            print("  无热门帖子")
            return []

        print(f"  热门帖子 {len(topics)} 条，开始补抓点击数...")

        # 2. 对 top 10 帖子补抓点击数（避免请求太多）
        top_n = min(10, len(topics))
        for i in range(top_n):
            t = topics[i]
            url = t.get("url") or f"https://www.v2ex.com/t/{t['id']}"
            clicks = _fetch_clicks(url)
            t["_clicks"] = clicks
            print(f"    [{i+1}] {t.get('title', '')[:30]}... | 💬{t.get('replies', 0)} 👁️{clicks}")

        # 未抓取点击数的帖子设为 0
        for t in topics[top_n:]:
            t["_clicks"] = 0

        # 3. 找评论最多的和点击最多的
        most_replied = max(topics[:top_n], key=lambda t: t.get("replies", 0))
        most_clicked = max(topics[:top_n], key=lambda t: t.get("_clicks", 0))

        results = []

        if most_replied["id"] == most_clicked["id"]:
            # 同一条帖子：合并
            topic = most_replied
            print(f"  🔥 评论最多 & 点击最多是同一条: {topic.get('title', '')[:40]}")

            replies = _fetch_replies(topic["id"])
            discussion = _build_discussion_text(topic, replies)
            item = _build_raw_item(topic, topic["_clicks"], discussion, "most_replied_and_clicked")
            results.append(item)
        else:
            # 两条不同的帖子
            print(f"  💬 评论最多: {most_replied.get('title', '')[:40]} ({most_replied.get('replies', 0)} 条)")
            print(f"  👁️ 点击最多: {most_clicked.get('title', '')[:40]} ({most_clicked['_clicks']} 次)")

            for topic, tag in [(most_replied, "most_replied"), (most_clicked, "most_clicked")]:
                replies = _fetch_replies(topic["id"])
                discussion = _build_discussion_text(topic, replies)
                item = _build_raw_item(topic, topic["_clicks"], discussion, tag)
                results.append(item)

        print(f"  ✅ 返回 {len(results)} 条")
        return results