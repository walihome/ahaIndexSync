# infra/time_utils.py
# 时间窗口工具，统一使用北京时间（系统 TZ=Asia/Shanghai）

from datetime import datetime, timedelta


def get_fetch_window() -> tuple[datetime, datetime]:
    """
    返回本次应处理的时间窗口：过去 24 小时。
    使用本地时间（北京时间），与 snapshot_date 保持一致。
    """
    now = datetime.now()
    start = now - timedelta(hours=24)
    return start, now


def today_str() -> str:
    """返回北京时间今日日期字符串，如 '2026-03-15'"""
    return datetime.now().date().isoformat()
