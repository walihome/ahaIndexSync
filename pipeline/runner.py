"""
Pipeline 编排器：加载配置 → 按阶段顺序执行。
"""

from __future__ import annotations

import os
from datetime import datetime

from supabase import create_client
from dotenv import load_dotenv

from pipeline.config_loader import load_config
from pipeline.run_tracker import RunTracker


def get_supabase():
    load_dotenv()
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def run_pipeline(
    mode: str = "daily",
    table_suffix: str = "",
    scraper_name: str = "",
):
    start_time = datetime.now()
    print(f"\n{'═' * 60}")
    print(f"🚀 Pipeline 启动 | mode={mode} | {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═' * 60}\n")

    sb = get_supabase()
    config = load_config(sb)

    if not scraper_name and not config.scrapers:
        print("❌ 配置异常: scraper_configs 表中没有启用的 scraper！")
        print("   请先执行 sql/002_seed_data.sql 初始化配置数据")
        print("   或检查 Supabase 中 scraper_configs 表是否有 enabled=true 的记录")
        raise RuntimeError("No enabled scrapers found in scraper_configs table. Run sql/002_seed_data.sql to seed config data.")

    if not config.rank_groups:
        print("⚠️ 配置警告: rank_group_configs 表为空，Rank 阶段将不会产出 display 数据")

    if scraper_name:
        config.scrapers = [s for s in config.scrapers if s.name == scraper_name or s.scraper_type == scraper_name]
        if not config.scrapers:
            print(f"❌ 找不到 scraper: {scraper_name}")
            return

    tracker = RunTracker(sb, run_type=mode, table_suffix=table_suffix)
    tracker.start_run(config.to_snapshot())

    stats = {"scraped": 0, "processed": 0, "ranked": 0, "archived": 0, "errors": 0}

    try:
        # Stage 1: Scrape
        print(f"\n{'─' * 40}")
        print("📡 Stage 1: Scrape")
        print(f"{'─' * 40}")
        from stages.scrape import run_scrape
        scrape_stats = run_scrape(sb, config, tracker, table_suffix)
        stats["scraped"] = scrape_stats.get("saved", 0)
        stats["errors"] += scrape_stats.get("errors", 0)

        # Stage 2: Process
        print(f"\n{'─' * 40}")
        print("🤖 Stage 2: Process")
        print(f"{'─' * 40}")
        from stages.process import run_process
        process_stats = run_process(sb, config, table_suffix)
        stats["processed"] = process_stats.get("success", 0)
        stats["errors"] += process_stats.get("failed", 0)

        # Stage 3: Rank
        print(f"\n{'─' * 40}")
        print("🏆 Stage 3: Rank")
        print(f"{'─' * 40}")
        from stages.rank import run_rank
        rank_stats = run_rank(sb, config, table_suffix)
        stats["ranked"] = rank_stats.get("display_count", 0)

        # Stage 4: Archive (only for production runs)
        if not table_suffix:
            print(f"\n{'─' * 40}")
            print("📦 Stage 4: Archive")
            print(f"{'─' * 40}")
            from stages.archive import run_archive
            archive_stats = run_archive(sb, config)
            stats["archived"] = archive_stats.get("daily", 0)

        tracker.finish_run(stats)

    except Exception as e:
        stats["errors"] += 1
        tracker.finish_run(stats, error=str(e))
        print(f"\n❌ Pipeline 失败: {e}")
        raise

    total_cost = (datetime.now() - start_time).total_seconds()
    print(f"\n{'═' * 60}")
    print(f"✨ Pipeline 完成 | {total_cost:.1f}s | scraped={stats['scraped']} "
          f"processed={stats['processed']} ranked={stats['ranked']} errors={stats['errors']}")
    print(f"{'═' * 60}\n")
