# infra/db.py
# Supabase client + table name helpers

from __future__ import annotations

import os
import json
from datetime import date, datetime, timezone
from supabase import create_client, Client
from dotenv import load_dotenv
from .models import RawItem
from .time_utils import get_fetch_window

load_dotenv()

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_ROLE_KEY"],
        )
    return _client


# backward compat: old code that imports `supabase` directly from this module
# will fail at import time but that's OK since rank.py is deleted
supabase = None


def table_names(suffix: str = "") -> tuple[str, str, str]:
    s = suffix or os.getenv("TABLE_SUFFIX", "")
    return f"raw_items{s}", f"processed_items{s}", f"display_items{s}"


def enrich_table_names(suffix: str = "") -> tuple[str, str, str, str]:
    """
    返回 (item_enrichments, subjects, subject_mentions, subject_aliases) 4 张新表的名称。
    suffix='_test' 时用测试表；空字符串即生产表。
    """
    s = suffix or os.getenv("TABLE_SUFFIX", "")
    return (
        f"item_enrichments{s}",
        f"subjects{s}",
        f"subject_mentions{s}",
        f"subject_aliases{s}",
    )


_suffix = os.getenv("TABLE_SUFFIX", "")
RAW_TABLE, PROCESSED_TABLE, DISPLAY_TABLE = table_names(_suffix)
ITEM_ENRICHMENTS_TABLE, SUBJECTS_TABLE, SUBJECT_MENTIONS_TABLE, SUBJECT_ALIASES_TABLE = enrich_table_names(_suffix)


# ── 写入 ───────────────────────────────────────────────────────

def upsert_raw_item(item: RawItem, raw_table: str | None = None) -> None:
    sb = get_supabase()
    tbl = raw_table or RAW_TABLE
    result = sb.table(tbl).upsert(item.to_db_dict()).execute()
    if not result.data:
        raise Exception(f"upsert_raw_item 失败: {item.title}")


def upsert_processed_item(item: RawItem, ai_data: dict, display_metrics: dict, processed_table: str | None = None) -> None:
    sb = get_supabase()
    tbl = processed_table or PROCESSED_TABLE
    result = sb.table(tbl).upsert({
        "item_id": item.id,
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
        "extra": item.extra,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }).execute()
    if not result.data:
        raise Exception(f"upsert_processed_item 失败: {item.title}")


# ── 读取 ───────────────────────────────────────────────────────

def get_pending_items(raw_table: str | None = None, processed_table: str | None = None, fetch_window_hours: int = 24) -> list[RawItem]:
    sb = get_supabase()
    raw_tbl = raw_table or RAW_TABLE
    proc_tbl = processed_table or PROCESSED_TABLE

    start, end = get_fetch_window(fetch_window_hours)

    raw_data = (
        sb.table(raw_tbl)
        .select("*")
        .gte("created_at", start.isoformat())
        .lte("created_at", end.isoformat())
        .execute()
        .data
    )

    processed_raw_ids = {
        r["item_id"]
        for r in sb.table(proc_tbl)
        .select("item_id")
        .eq("snapshot_date", date.today().isoformat())
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

        def _parse_json(val):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return {}
            return val or {}

        items.append(RawItem(
            title=r["title"],
            original_url=r["original_url"],
            source_name=r["source_name"],
            source_type=r["source_type"],
            content_type=r["content_type"],
            author=r.get("author", ""),
            author_url=r.get("author_url", ""),
            body_text=r.get("body_text", ""),
            raw_metrics=_parse_json(r.get("raw_metrics")),
            extra=_parse_json(r.get("extra")),
            published_at=published_at,
        ))

    return items
