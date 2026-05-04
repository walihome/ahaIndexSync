# infra/time_utils.py

from datetime import datetime, date, timedelta

_override_date: str | None = None


def set_override_date(d: str | None) -> None:
    """设置覆盖日期，用于回补历史数据。设为 None 恢复默认行为。"""
    global _override_date
    _override_date = d


def get_today_str() -> str:
    """返回今天的日期字符串，优先使用覆盖日期。"""
    if _override_date:
        return _override_date
    return date.today().isoformat()


def get_fetch_window(hours: int = 24) -> tuple[datetime, datetime]:
    now = datetime.now()
    return now - timedelta(hours=hours), now


def today_str() -> str:
    return get_today_str()
