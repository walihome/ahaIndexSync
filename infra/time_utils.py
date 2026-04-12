# infra/time_utils.py

from datetime import datetime, timedelta


def get_fetch_window(hours: int = 24) -> tuple[datetime, datetime]:
    now = datetime.now()
    return now - timedelta(hours=hours), now


def today_str() -> str:
    return datetime.now().date().isoformat()
