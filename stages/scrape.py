# stages/scrape.py

from __future__ import annotations

import signal
from datetime import datetime

from supabase import Client
from pipeline.config_loader import PipelineConfig
from pipeline.run_tracker import RunTracker
from infra.db import upsert_raw_item, table_names
from scrapers.registry import get_engine


class _TimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _TimeoutError("超时")


def run_scrape(sb: Client, config: PipelineConfig, tracker: RunTracker, table_suffix: str = "") -> dict:
    raw_table, _, _ = table_names(table_suffix)
    timeout = int(config.get_param("scraper_timeout", 120))

    total_saved = 0
    total_errors = 0

    for sc in config.scrapers:
        engine_cls = get_engine(sc.scraper_type)
        if not engine_cls:
            print(f"  ⚠️ 未知引擎类型: {sc.scraper_type}，跳过 {sc.name}")
            total_errors += 1
            continue

        scraper_run_id = tracker.start_scraper(sc.id, sc.scraper_type, sc.name)
        print(f"\n▶ [{sc.scraper_type}] {sc.name}")
        t0 = datetime.now()

        try:
            engine = engine_cls(name=sc.name, config=sc.config)

            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout)
            try:
                items = engine.fetch()
            finally:
                signal.alarm(0)

            saved = 0
            for item in items:
                try:
                    upsert_raw_item(item, raw_table)
                    saved += 1
                except Exception as e:
                    print(f"  ⚠️ 写库失败: {item.title[:40]} | {e}")

            cost = (datetime.now() - t0).total_seconds()
            tracker.finish_scraper(scraper_run_id, "success", items_fetched=len(items), items_saved=saved)
            total_saved += saved
            print(f"  ✅ 写入 {saved}/{len(items)} 条 | {cost:.1f}s")

        except _TimeoutError:
            cost = (datetime.now() - t0).total_seconds()
            tracker.finish_scraper(scraper_run_id, "timeout", error=f"超时（>{timeout}s）")
            total_errors += 1
            print(f"  ⏱️ 超时跳过（>{timeout}s）")

        except Exception as e:
            cost = (datetime.now() - t0).total_seconds()
            tracker.finish_scraper(scraper_run_id, "failed", error=str(e))
            total_errors += 1
            print(f"  ❌ 失败: {e}")

    print(f"\n📊 Scrape 完成: 写入 {total_saved} 条，错误 {total_errors} 个")
    return {"saved": total_saved, "errors": total_errors}
