# scrapers/community/linuxdo_hot.py
# 抓取 linux.do 今日热议：回复最多的 1 条 + 点击最多的 1 条
# 如果两条是同一个帖子，合并为 1 条
# linux.do 基于 Discourse，使用标准 Discourse API

import requests
from datetime import datetime, timezone
from infra.models import BaseScraper, RawItem

LINUXDO_TOP_API = "https://linux.do/top.json?period=daily"
LINUXDO_TOPIC_API = "https://linux.do/t/{topic_id}.json"
LINUXDO_BASE = "https://linux.do"

# 只对 top N 补抓评论内容
TOP_N = 10

# 最多抓多少条评论
MAX_REPLIES_TO_FETCH = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _fetch_top_topics() -> list[dict]:
    """调用 Discourse top API，返回今日热门帖子列表"""
    try:
        resp = requests.get(LINUXDO_TOP_API, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  ⚠️ linux.do Top API 返回 {resp.status_code}")
            return []
        data = resp.json()
        # Discourse top.json 结构：topic_list.topics
        topics = data.get("topic_list", {}).get("topics", [])
        return topics
    except Exception as e:
        print(f"  ⚠️ linux.do Top API 失败: {e}")
        return []


def _fetch_topic_replies(topic_id: int) -> list[str]:
    """从 Discourse API 获取帖子的回复内容"""
    url = LINUXDO_TOPIC_API.format(topic_id=topic_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return []

        data = resp.json()
        post_stream = data.get("post_stream", {})
        posts = post_stream.get("posts", [])

        replies = []
        for post in posts[1:MAX_REPLIES_TO_FETCH + 1]:  # 跳过第一条（原帖）
            # Discourse 返回 cooked（HTML）和 raw（原文）
            # 优先用 raw，没有的话用 cooked 去 HTML 标签
            text = post.get("raw", "")
            if not text:
                cooked = post.get("cooked", "")
                import re
                text = re.sub(r'<[^>]+>', '', cooked).strip()
                text = re.sub(r'\s+', ' ', text)
            if text:
                replies.append(text[:300])  # 每条截取 300 字

        return replies
    except Exception as e:
        print(f"  ⚠️ 抓取评论失败 (topic {topic_id}): {e}")
        return []


def _format_replies_text(replies: list[str]) -> str:
    """把评论列表格式化为可读文本"""
    if not replies:
        return ""
    lines = []
    for i, r in enumerate(replies, 1):
        text = r[:200] + ("..." if len(r) > 200 else "")
        lines.append(f"[回复{i}] {text}")
    return "\n".join(lines)


class LinuxDoHotScraper(BaseScraper):
    source_name = "LINUX DO"
    source_type = "ARTICLE"
    content_type = "linuxdo_hot"

    def fetch(self) -> list[RawItem]:
        topics = _fetch_top_topics()
        if not topics:
            print("  linux.do Top API 无数据")
            return []

        print(f"  Top API 返回 {len(topics)} 条，补抓 top {min(TOP_N, len(topics))} 条的评论...")

        enriched = []
        for t in topics[:TOP_N]:
            topic_id = t["id"]
            title = t.get("title", "")
            views = t.get("views", 0)
            posts_count = t.get("posts_count", 0) - 1  # Discourse 的 posts_count 包含原帖，减 1 得到回复数
            like_count = t.get("like_count", 0)
            slug = t.get("slug", "")

            topic_url = f"{LINUXDO_BASE}/t/{slug}/{topic_id}" if slug else f"{LINUXDO_BASE}/t/topic/{topic_id}"

            # 补抓评论内容
            replies_text = _fetch_topic_replies(topic_id)

            enriched.append({
                "id": topic_id,
                "title": title,
                "url": topic_url,
                "posts_count": max(posts_count, 0),
                "views": views,
                "like_count": like_count,
                "replies_text": replies_text,
                "category": t.get("category_id", ""),
                "created_at": t.get("created_at", ""),
            })
            print(f"    [{title[:30]}...] 回复:{posts_count} 点击:{views} 点赞:{like_count} 抓取评论:{len(replies_text)}条")

        if not enriched:
            return []

        # 找回复最多的和点击最多的
        top_by_replies = max(enriched, key=lambda x: x["posts_count"])
        top_by_views = max(enriched, key=lambda x: x["views"])

        items = []

        if top_by_replies["id"] == top_by_views["id"]:
            t = top_by_replies
            print(f"  回复最多 & 点击最多是同一条: [{t['title'][:40]}]")
            items.append(self._build_item(t, "最热+最多评论"))
        else:
            print(f"  回复最多: [{top_by_replies['title'][:30]}] ({top_by_replies['posts_count']}条回复)")
            print(f"  点击最多: [{top_by_views['title'][:30]}] ({top_by_views['views']}次点击)")
            items.append(self._build_item(top_by_replies, "最多评论"))
            items.append(self._build_item(top_by_views, "最多点击"))

        print(f"  最终返回 {len(items)} 条")
        return items

    def _build_item(self, t: dict, rank_type: str) -> RawItem:
        """构建 RawItem"""
        body_parts = []

        replies_text = _format_replies_text(t["replies_text"])
        if replies_text:
            body_parts.append(f"【热门讨论】\n{replies_text}")

        body_text = "\n".join(body_parts)

        # 解析创建时间
        published_at = None
        if t.get("created_at"):
            try:
                published_at = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        return RawItem(
            title=t["title"],
            original_url=t["url"],
            source_name=self.source_name,
            source_type=self.source_type,
            content_type=self.content_type,
            author="",
            author_url="",
            body_text=body_text[:2000],
            raw_metrics={
                "replies": t["posts_count"],
                "views": t["views"],
                "likes": t["like_count"],
            },
            extra={
                "source_tag": "dev_community",
                "rank_type": rank_type,
                "top_replies_count": len(t["replies_text"]),
            },
            published_at=published_at,
        )