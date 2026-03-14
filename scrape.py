# scrape.py
# 抓取入口：fetch → upsert raw_items，完毕
# 不做任何 AI 处理，不做任何过滤
# 支持通过 SCRAPER_NAME 环境变量指定单个 scraper

import os
import signal
from datetime import datetime
from scrapers.registry import discover_scrapers
from infra.db import upsert_raw_item

# 每个 scraper 最长运行时间（秒），超时直接跳过
SCRAPER_TIMEOUT = 120


class TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise TimeoutError("超时")


def run_with_timeout(scraper, timeout: int):
    """运行 scraper.fetch()，超时抛出 TimeoutError"""
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(timeout)
    try:
        return scraper.fetch()
    finally:
        signal.alarm(0)  # 取消定时器


def main():
    start_time = datetime.now()
    print(f"\n🚀 抓取启动 | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

    scraper_name = os.getenv("SCRAPER_NAME", "").strip()

    scrapers = discover_scrapers()

    if scraper_name:
        scrapers = [s for s in scrapers if s.__class__.__name__ == scraper_name]
        if not scrapers:
            print(f"❌ 找不到 scraper: {scraper_name}")
            print(f"   可用的有: {[s.__class__.__name__ for s in discover_scrapers()]}")
            exit(1)
        print(f"📋 指定运行: {scraper_name}\n")
    else:
        print(f"📋 自动发现 {len(scrapers)} 个抓取器\n")

    results = []  # (name, success, count, cost_seconds, error)

    for scraper in scrapers:
        name = scraper.__class__.__name__
        print(f"{'─' * 40}")
        print(f"▶ {name} | 开始 {datetime.now().strftime('%H:%M:%S')}")
        t0 = datetime.now()
        try:
            items = run_with_timeout(scraper, SCRAPER_TIMEOUT)
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
        except TimeoutError:
            cost = (datetime.now() - t0).total_seconds()
            results.append((name, False, 0, cost, f"超时（>{SCRAPER_TIMEOUT}s）"))
            print(f"  ⏱️ 超时跳过（>{SCRAPER_TIMEOUT}s）")
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
        status = "✅" if ok else "⏱️" if err and "超时" in err else "❌"
        detail = f"{count} 条 | {cost:.1f}s" if ok else f"{cost:.1f}s | {err}"
        print(f"  {status} {name:<40} {detail}")
    print(f"{'─' * 40}\n")


if __name__ == "__main__":
    main()
