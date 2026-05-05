# stages/coarse_filter.py
"""
粗排过滤：Process 之后、Enrich 之前。
只做"排除"，不做打分。保留的候选进入 Enrich。

排除条件（满足任一即排除）：
  - aha_index < coarse_filter_min_aha（默认 0.25）
  - 死链（HTTP 检查）
  - URL 重复（保留 aha_index 更高的一条）

现有 Rank 阶段的 _dedup_by_url / _check_links_batch 已搬来此处。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import Client

from pipeline.config_loader import PipelineConfig
from infra.db import table_names
from infra.time_utils import today_str
from infra.link_checker import is_accessible


def _dedup_by_url(data: list[dict]) -> tuple[list[dict], list[dict]]:
    seen: dict[str, dict] = {}
    dupes = []
    for item in data:
        url = item.get("original_url", "")
        if not url:
            continue
        if url in seen:
            existing = seen[url]
            if (item.get("aha_index", 0) or 0) > (existing.get("aha_index", 0) or 0):
                dupes.append(existing)
                seen[url] = item
            else:
                dupes.append(item)
        else:
            seen[url] = item
    return list(seen.values()), dupes


def _check_links_batch(candidates: list[dict], max_workers: int = 10) -> tuple[list[dict], list[dict]]:
    alive, dead = [], []

    def _check(item):
        url = item.get("original_url", "")
        return item, is_accessible(url) if url else True

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_check, c): c for c in candidates}
        for future in as_completed(futures):
            try:
                item, ok = future.result()
                (alive if ok else dead).append(item)
            except Exception:
                alive.append(futures[future])
    return alive, dead


def run_coarse_filter(sb: Client, config: PipelineConfig, table_suffix: str = "") -> dict:
    _, processed_table, _, _ = table_names(table_suffix)
    today = today_str()

    min_aha = float(config.get_param("coarse_filter_min_aha", 0.25))
    link_workers = int(config.get_param("link_check_max_workers", 10))

    data = sb.table(processed_table).select("*").eq("snapshot_date", today).execute().data or []
    initial = len(data)
    print(f"📋 今日 processed_items 共 {initial} 条")

    if not data:
        return {"initial": 0, "dedup_removed": 0, "dead_links": 0, "low_aha": 0, "survived": 0, "items": []}

    data, dupes = _dedup_by_url(data)
    if dupes:
        print(f"🔀 去重: 去除 {len(dupes)} 条，保留 {len(data)} 条")

    before_aha = len(data)
    data = [d for d in data if (d.get("aha_index") or 0) >= min_aha]
    low_aha = before_aha - len(data)
    if low_aha:
        print(f"⚖️ aha_index<{min_aha}: 去除 {low_aha} 条，保留 {len(data)} 条")

    if data:
        print(f"🔗 链接检查中 ({len(data)} 条)...")
        data, dead_links = _check_links_batch(data, link_workers)
        if dead_links:
            print(f"🔗 死链: {len(dead_links)} 条，保留 {len(data)} 条")
    else:
        dead_links = []

    data.sort(key=lambda x: x.get("aha_index") or 0, reverse=True)

    print(f"📊 粗排完成: {initial} → {len(data)} 条进入 Enrich")
    return {
        "initial": initial,
        "dedup_removed": len(dupes),
        "low_aha": low_aha,
        "dead_links": len(dead_links),
        "survived": len(data),
        "items": data,
    }
