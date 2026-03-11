# infra/time_utils.py
# 时间窗口工具，全局统一，抓取和展示都用这一份

from datetime import datetime, timezone, timedelta


def get_fetch_window() -> tuple[datetime, datetime]:
    """
    返回本次应处理的时间窗口：过去 24 小时内写入数据库的数据。
    用 created_at（写入时间）而非 published_at（发布时间），
    不受来源时区影响，内外网源统一对齐。
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=36)
    return start, now