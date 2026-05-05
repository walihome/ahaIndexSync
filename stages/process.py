# stages/process.py

from __future__ import annotations

import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import Client
from pipeline.config_loader import PipelineConfig
from infra.db import get_pending_items_with_content, upsert_processed_item, table_names
from infra.llm import call_llm
from infra.content_fetcher import enrich_body_text
from infra.display_metrics import build_display_metrics
from infra.models import RawItem, ContentRecord


def _process_item(item: RawItem, content: ContentRecord, config: PipelineConfig, api_key: str, processed_table: str) -> tuple[bool, str]:
    try:
        item.body_text = enrich_body_text(item, config.skip_domains, config.fulltext_tags, content=content)

        prompt_cfg = config.get_prompt("process_main")
        if not prompt_cfg:
            print("  ⚠️ process_main prompt 未配置")
            return False, item.title

        prompt = prompt_cfg.render(
            source_name=item.source_name,
            source_tag=item.extra.get("source_tag", ""),
            title=item.title,
            body_text=item.body_text[:800] if item.body_text else "无",
            raw_metrics=json.dumps(item.raw_metrics, ensure_ascii=False),
        )

        system_cfg = config.get_prompt("process_system")
        system_prompt = system_cfg.template if system_cfg else "You only output JSON."

        ai_data = call_llm(prompt, prompt_cfg, system_prompt=system_prompt, api_key=api_key)
        if not ai_data:
            return False, item.title

        display_metrics = build_display_metrics(item, config.display_metrics or None)
        upsert_processed_item(item, ai_data, display_metrics, processed_table)
        return True, item.title

    except Exception as e:
        print(f"  ❌ 失败: {item.title[:50]} | {e}")
        return False, item.title


def run_process(sb: Client, config: PipelineConfig, table_suffix: str = "", snapshot_date: str | None = None) -> dict:
    raw_table, processed_table, _, content_table = table_names(table_suffix)
    api_key = os.getenv("KIMI_API_KEY", "")
    max_workers = int(config.get_param("process_max_workers", 3))
    fetch_window = int(config.get_param("fetch_window_hours", 24))

    pending = get_pending_items_with_content(raw_table, content_table, processed_table, fetch_window, snapshot_date=snapshot_date)
    print(f"📋 待处理 {len(pending)} 条，并发数 {max_workers}")

    if not pending:
        print("✅ 无待处理数据")
        return {"success": 0, "failed": 0}

    success, failed = 0, 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_item, item, content, config, api_key, processed_table): item
            for item, content in pending
        }
        for future in as_completed(futures):
            ok, title = future.result()
            if ok:
                success += 1
                print(f"  ✅ {title[:50]}")
            else:
                failed += 1

    print(f"\n📊 Process 完成: 成功 {success} | 失败 {failed}")
    return {"success": success, "failed": failed}
