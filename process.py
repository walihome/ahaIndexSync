# process.py
# AI 处理入口：读 raw_items diff → enrich → AI 加工 → 写 processed_items

from datetime import datetime
from infra.db import get_pending_items, upsert_processed_item
from infra.llm import process_with_ai
from infra.content_fetcher import enrich_body_text
from infra.display_metrics import build_display_metrics


def main():
    start_time = datetime.now()
    print(f"\n🤖 AI 处理启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    pending = get_pending_items()
    print(f"📋 待处理 {len(pending)} 条\n")

    if not pending:
        print("✅ 无待处理数据，退出")
        return

    success, failed = 0, 0

    for item in pending:
        try:
            # 1. 补全正文
            item.body_text = enrich_body_text(item)

            # 2. AI 处理
            ai_data = process_with_ai(item)
            if not ai_data:
                print(f"  ⚠️ AI 处理返回空: {item.title[:50]}")
                failed += 1
                continue

            # 3. 组装展示指标
            display_metrics = build_display_metrics(item)

            # 4. 写库
            upsert_processed_item(item, ai_data, display_metrics)

            print(f"  ✅ {item.source_name} | {item.title[:50]}")
            success += 1

        except Exception as e:
            print(f"  ❌ 失败: {item.title[:50]} | {e}")
            failed += 1

    total_cost = (datetime.now() - start_time).total_seconds()
    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | 成功 {success} | 失败 {failed} | {total_cost:.1f}s\n")


if __name__ == "__main__":
    main()