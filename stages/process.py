# stages/process.py

from __future__ import annotations

import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from supabase import Client
from pipeline.config_loader import PipelineConfig
from infra.db import get_pending_items_with_content, upsert_processed_item, table_names
from infra.llm import call_llm
from infra.content_fetcher import enrich_body_text
from infra.display_metrics import build_display_metrics
from infra.models import RawItem, ContentRecord
from infra.oss import upload_image_to_oss
from infra.time_utils import get_today_str


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")
_VIDEO_EXTS = (".mp4", ".webm", ".mov")


def _media_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [u for u in value if isinstance(u, str) and u.strip()]


def _oss_date_str(snapshot_date: str | None = None) -> str:
    return (snapshot_date or get_today_str()).replace("-", "")


def _should_skip_body_image(item: RawItem) -> bool:
    # Repo README images are already collected by the GitHub scrapers. Jina's
    # GitHub output often repeats the same README images with different raw URLs.
    return item.content_type == "repo" and bool(_media_list(item.extra.get("readme_images")))


def _extract_and_upload_media(item: RawItem, content: ContentRecord, snapshot_date: str | None = None) -> None:
    """从 enriched_body 提取非头像图片，与 extra.media_urls 合并后上传 OSS。"""
    urls: list[str] = []

    # 1. 从 enriched_body 提取
    body = content.enriched_body or ""
    skip_body_images = _should_skip_body_image(item)
    if body:
        for alt, url in re.findall(r'!\[([^\]]*)\]\(([^)]+)\)', body):
            lower = url.lower()
            if "avatar" in lower or "logo" in lower:
                continue
            if skip_body_images and any(lower.endswith(ext) for ext in _IMAGE_EXTS):
                continue
            if any(lower.endswith(ext) for ext in _IMAGE_EXTS + _VIDEO_EXTS):
                urls.append(url)

    # 2. 合并 scraper 已有的 media_urls
    existing = _media_list(item.extra.get("media_urls"))
    urls = list(dict.fromkeys(existing + urls))  # 去重保序

    # 3. 上传图片到 OSS（视频保留原始链接）
    date_str = _oss_date_str(snapshot_date)
    oss_urls: list[str] = []
    for u in urls:
        if any(u.lower().endswith(ext) for ext in _VIDEO_EXTS):
            oss_urls.append(u)  # 视频不上传
        else:
            oss_urls.append(upload_image_to_oss(u, date_str) or u)

    if oss_urls:
        item.extra["media_urls"] = oss_urls


def _process_item(item: RawItem, content: ContentRecord, config: PipelineConfig, api_key: str, processed_table: str, snapshot_date: str | None = None) -> tuple[bool, str]:
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

        # 提取 enriched_body 中的非头像图片，合并到 media_urls 并上传 OSS
        _extract_and_upload_media(item, content, snapshot_date=snapshot_date)

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
            executor.submit(_process_item, item, content, config, api_key, processed_table, snapshot_date): item
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
