"""
Pipeline 执行追踪：写入 pipeline_runs / scraper_runs。
"""

from __future__ import annotations

from datetime import datetime, timezone
from supabase import Client


class RunTracker:
    def __init__(self, sb: Client, run_type: str = "daily", table_suffix: str = ""):
        self.sb = sb
        self.run_id: str | None = None
        self.run_type = run_type
        self.table_suffix = table_suffix

    def start_run(self, config_snapshot: dict) -> str:
        row = {
            "run_type": self.run_type,
            "status": "running",
            "table_suffix": self.table_suffix,
            "config_snapshot": config_snapshot,
        }
        result = self.sb.table("pipeline_runs").insert(row).execute()
        self.run_id = result.data[0]["id"]
        print(f"🆔 Pipeline run: {self.run_id}")
        return self.run_id

    def finish_run(self, stats: dict, error: str | None = None):
        if not self.run_id:
            return
        update = {
            "status": "failed" if error else "success",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
        }
        if error:
            update["error"] = error[:2000]
        self.sb.table("pipeline_runs").update(update).eq("id", self.run_id).execute()

    def start_scraper(self, scraper_config_id: str, scraper_type: str, scraper_name: str) -> str:
        row = {
            "pipeline_run_id": self.run_id,
            "scraper_config_id": scraper_config_id,
            "scraper_type": scraper_type,
            "scraper_name": scraper_name,
            "status": "running",
        }
        result = self.sb.table("scraper_runs").insert(row).execute()
        return result.data[0]["id"]

    def finish_scraper(self, scraper_run_id: str, status: str, items_fetched: int = 0, items_saved: int = 0, error: str | None = None):
        update = {
            "status": status,
            "items_fetched": items_fetched,
            "items_saved": items_saved,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        if error:
            update["error"] = error[:2000]
        self.sb.table("scraper_runs").update(update).eq("id", scraper_run_id).execute()
