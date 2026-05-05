# stages/fetch_content.py
# Stage 1.5: 全文抓取 — 用 Jina Reader 补充 items_content.enriched_body

from __future__ import annotations

from datetime import date

from supabase import Client
from pipeline.config_loader import PipelineConfig
from infra.db import table_names, get_supabase
from infra.jina import fetch_fulltext as jina_fetch


def run_fetch_content(sb: Client, config: PipelineConfig, table_suffix: str = "", snapshot_date: str | None = None) -> dict:
    """抓取待处理条目的全文，写入 items_content.enriched_body。

    降级策略：fetch 失败的条目，process 阶段 COALESCE 回退到 raw_body。
    """
    _, _, _, content_table = table_names(table_suffix)
    skip_domains = config.skip_domains or {"twitter.com", "x.com", "medium.com", "zhihu.com", "v2ex.com"}

    # 查询待处理条目
    # JOIN 表名和响应 key 需要跟随后缀
    raw_table = "raw_items_test" if table_suffix == "_test" else "raw_items"

    query = (
        sb.table(content_table)
        .select(f"item_id, raw_body, {raw_table}!inner(original_url, source_name)")
        .is_("enriched_body", "null")
        .lt("fetch_attempts", 3)
    )
    if snapshot_date:
        query = query.eq(f"{raw_table}.snapshot_date", snapshot_date)

    pending = query.execute().data or []

    if not pending:
        print("  ✅ 无待全文抓取的数据")
        return {"total": 0, "success": 0, "failed": 0, "skipped": 0}

    print(f"  📋 待抓取 {len(pending)} 条")
    success, failed, skipped = 0, 0, 0

    for row in pending:
        item_id = row["item_id"]
        url = row[raw_table]["original_url"]
        source_name = row[raw_table].get("source_name", "")

        # skip_domains 命中的源跳过
        if any(domain in url for domain in skip_domains):
            skipped += 1
            continue

        try:
            text = jina_fetch(url)
            sb.table(content_table).update({
                "enriched_body": text,
                "enriched_source": "jina",
            }).eq("item_id", item_id).execute()
            # fetch_attempts 通过 trigger 或 RPC 递增
            sb.rpc("increment_fetch_attempts", {"p_item_id": item_id}).execute()
            success += 1
            print(f"    ✅ {source_name}: {url[:60]}")
        except Exception as e:
            sb.table(content_table).update({
                "last_fetch_error": str(e)[:500],
            }).eq("item_id", item_id).execute()
            sb.rpc("increment_fetch_attempts", {"p_item_id": item_id}).execute()
            failed += 1
            print(f"    ❌ {source_name}: {e}")

    print(f"\n  📊 Fetch Content 完成: 成功 {success} | 失败 {failed} | 跳过 {skipped}")
    return {"total": len(pending), "success": success, "failed": failed, "skipped": skipped}
