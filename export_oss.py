"""
数据导出：Supabase → JSON → OSS

将 display_items 表导出为静态 JSON 文件上传到 OSS，
供前端直接拉取，替代实时查询 Supabase。

OSS 文件结构:
    api/latest.json                    → 最新一期数据（含 snapshot_date + items）
    api/daily/{year}/{month}/{date}.json → 按日期归档，如 api/daily/2026/03/2026-03-23.json
    api/dates.json                     → 可用日期列表（供归档页使用）

用法:
    python export_oss.py
"""

import os
import json
from datetime import datetime

from supabase import create_client
from infra.oss_client import put_bytes, exists


def _get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return create_client(url, key)


def _get_table_name():
    suffix = os.getenv("TABLE_SUFFIX", "")
    return f"display_items{suffix}"


def export_to_oss():
    sb = _get_supabase()
    table = _get_table_name()

    # 1. 查最新 snapshot_date
    latest_resp = (
        sb.table(table)
        .select("snapshot_date")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )

    if not latest_resp.data:
        print("⚠️ display_items 表为空，跳过导出")
        return

    latest_date = latest_resp.data[0]["snapshot_date"]
    print(f"📅 最新日期: {latest_date}")

    # 2. 拉取该日期的全部数据
    items_resp = (
        sb.table(table)
        .select("*")
        .eq("snapshot_date", latest_date)
        .order("rank", desc=False)
        .execute()
    )

    items = items_resp.data or []
    print(f"📦 共 {len(items)} 条数据")

    # 3. 上传 api/daily/{date}.json
    year = latest_date[:4]
    month = latest_date[5:7]
    daily_key = f"api/daily/{year}/{month}/{latest_date}.json"
    daily_payload = json.dumps(
        {"snapshot_date": latest_date, "items": items},
        ensure_ascii=False,
    )
    daily_url = put_bytes(
        daily_payload.encode("utf-8"),
        daily_key,
        "application/json; charset=utf-8",
    )
    print(f"✅ {daily_key} → {daily_url}")

    # 4. 上传 api/latest.json（内容跟当天一样）
    latest_key = "api/latest.json"
    latest_url = put_bytes(
        daily_payload.encode("utf-8"),
        latest_key,
        "application/json; charset=utf-8",
    )
    print(f"✅ {latest_key} → {latest_url}")

    # 5. 更新 api/dates.json（所有可用日期列表）
    dates_resp = (
        sb.table(table)
        .select("snapshot_date")
        .order("snapshot_date", desc=True)
        .execute()
    )
    all_dates = sorted(
        set(row["snapshot_date"] for row in (dates_resp.data or [])),
        reverse=True,
    )
    dates_key = "api/dates.json"
    dates_payload = json.dumps(
        {"dates": all_dates},
        ensure_ascii=False,
    )
    dates_url = put_bytes(
        dates_payload.encode("utf-8"),
        dates_key,
        "application/json; charset=utf-8",
    )
    print(f"✅ {dates_key} → {dates_url}")

    print(f"\n🎉 导出完成，共 {len(items)} 条，日期 {latest_date}")


if __name__ == "__main__":
    export_to_oss()
