# process.py
# AI 处理入口：读 raw_items diff → enrich → AI 加工 → 写 processed_items

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from infra.db import get_pending_items, upsert_processed_item
from infra.llm import process_with_ai
from infra.content_fetcher import enrich_body_text
from infra.display_metrics import build_display_metrics
from infra.models import RawItem

MAX_WORKERS = 3  # Kimi 付费版并发数，可按实际限额调整


def process_item(item: RawItem) -> tuple[bool, str]:
    """处理单条，返回 (success, title)"""
    try:
        item.body_text = enrich_body_text(item)
        ai_data = process_with_ai(item)
        if not ai_data:
            return False, item.title

        display_metrics = build_display_metrics(item)
        upsert_processed_item(item, ai_data, display_metrics)
        return True, item.title

    except Exception as e:
        print(f"  ❌ 失败: {item.title[:50]} | {e}")
        return False, item.title


def main():
    start_time = datetime.now()
    print(f"\n🤖 AI 处理启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    pending = get_pending_items()
    print(f"📋 待处理 {len(pending)} 条，并发数 {MAX_WORKERS}\n")

    if not pending:
        print("✅ 无待处理数据，退出")
        return

    success, failed = 0, 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_item, item): item for item in pending}

        for future in as_completed(futures):
            ok, title = future.result()
            if ok:
                success += 1
                print(f"  ✅ {title[:50]}")
            else:
                failed += 1

    total_cost = (datetime.now() - start_time).total_seconds()
    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | 成功 {success} | 失败 {failed} | {total_cost:.1f}s\n")


if __name__ == "__main__":
    main()
