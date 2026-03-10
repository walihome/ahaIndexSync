# scrape.py
# 抓取入口：fetch → upsert raw_items，完毕
# 不做任何 AI 处理，不做任何过滤

from datetime import datetime
from scrapers.registry import discover_scrapers
from infra.db import upsert_raw_item


def main():
    start_time = datetime.now()
    print(f"\n🚀 抓取启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    scrapers = discover_scrapers()
    print(f"📋 自动发现 {len(scrapers)} 个抓取器\n")

    results = []  # (name, success, count, cost_seconds, error)

    for scraper in scrapers:
        name = scraper.__class__.__name__
        print(f"{'─' * 40}")
        print(f"▶ {name}")
        t0 = datetime.now()
        try:
            items = scraper.fetch()
            saved = 0
            for item in items:
                try:
                    upsert_raw_item(item)
                    saved += 1
                except Exception as e:
                    print(f"  ⚠️ 写库失败: {item.title[:40]} | {e}")

            cost = (datetime.now() - t0).total_seconds()
            results.append((name, True, saved, cost, None))
            print(f"  ✅ 写入 {saved}/{len(items)} 条 | {cost:.1f}s")
        except Exception as e:
            cost = (datetime.now() - t0).total_seconds()
            results.append((name, False, 0, cost, str(e)))
            print(f"  ❌ 失败: {e}")

    # ── 汇总 ──────────────────────────────────────────────────
    total_cost = (datetime.now() - start_time).total_seconds()
    success_count = sum(1 for _, ok, *_ in results if ok)
    total_saved = sum(c for _, ok, c, *_ in results if ok)

    print(f"\n{'═' * 40}")
    print(f"✨ 完成 | {success_count}/{len(results)} 成功 | 共写入 {total_saved} 条 | {total_cost:.1f}s")
    print(f"{'─' * 40}")
    for name, ok, count, cost, err in results:
        status = "✅" if ok else "❌"
        detail = f"{count} 条 | {cost:.1f}s" if ok else f"{cost:.1f}s | {err}"
        print(f"  {status} {name:<40} {detail}")
    print(f"{'─' * 40}\n")


if __name__ == "__main__":
    main()