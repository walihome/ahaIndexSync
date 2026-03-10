# infra/db.py
# 纯数据库读写，不含任何业务逻辑

import os
from datetime import date, datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
from .models import RawItem
from .time_utils import get_fetch_window

load_dotenv()

supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
)


# ── 写入 ───────────────────────────────────────────────────────

def upsert_raw_item(item: RawItem) -> None:
    result = supabase.table("raw_items").upsert(item.to_db_dict()).execute()
    if not result.data:
        raise Exception(f"upsert_raw_item 失败: {item.title}")


def upsert_processed_item(item: RawItem, ai_data: dict, display_metrics: dict) -> None:
    result = supabase.table("processed_items").upsert({
        "raw_id": item.id,
        "snapshot_date": date.today().isoformat(),
        "raw_title": item.title,
        "original_url": item.original_url,
        "source_name": item.source_name,
        "content_type": item.content_type,
        "author": item.author,
        "raw_metrics": item.raw_metrics,
        "model": ai_data.get("model", "unknown"),
        "processed_title": ai_data.get("processed_title"),
        "summary": ai_data.get("summary"),
        "category": ai_data.get("category"),
        "tags": ai_data.get("tags", []),
        "keywords": ai_data.get("keywords", []),
        "aha_index": float(ai_data.get("aha_index", 0.5)),
        "expert_insight": ai_data.get("expert_insight"),
        "display_metrics": display_metrics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if not result.data:
        raise Exception(f"upsert_processed_item 失败: {item.title}")


# ── 读取 ───────────────────────────────────────────────────────

def get_pending_items() -> list[RawItem]:
    """
    返回今日写入但尚未处理的 raw_items。
    用时间窗口过滤 raw_items，再与 processed_items 做 diff。
    """
    start, end = get_fetch_window()

    raw_data = (
        supabase.table("raw_items")
        .select("*")
        .gte("created_at", start.isoformat())
        .lte("created_at", end.isoformat())
        .execute()
        .data
    )

    processed_raw_ids = {
        r["raw_id"]
        for r in supabase.table("processed_items")
        .select("raw_id")
        .gte("created_at", start.isoformat())
        .execute()
        .data
    }

    pending = [r for r in raw_data if r["id"] not in processed_raw_ids]

    items = []
    for r in pending:
        published_at = None
        if r.get("published_at"):
            try:
                published_at = datetime.fromisoformat(r["published_at"])
            except Exception:
                pass

        items.append(RawItem(
            title=r["title"],
            original_url=r["original_url"],
            source_name=r["source_name"],
            source_type=r["source_type"],
            content_type=r["content_type"],
            author=r.get("author", ""),
            author_url=r.get("author_url", ""),
            body_text=r.get("body_text", ""),
            raw_metrics=r.get("raw_metrics", {}),
            extra=r.get("extra", {}),
            published_at=published_at,
        ))

    return items