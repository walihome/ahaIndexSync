# infra/jina.py
# Jina Reader API wrapper for full-text fetching

from __future__ import annotations

import time
import threading
import requests


JINA_READER_URL = "https://r.jina.ai/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Rate limiter ────────────────────────────────────────────────
# Jina free tier: 20 QPS → 50ms interval; use 60ms for safety margin
_MIN_INTERVAL = 0.06  # seconds between requests
_last_request_time = 0.0
_lock = threading.Lock()

# 429 retry config
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds


def _throttle():
    """Enforce minimum interval between outgoing requests."""
    global _last_request_time
    with _lock:
        now = time.monotonic()
        elapsed = now - _last_request_time
        if elapsed < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - elapsed)
        _last_request_time = time.monotonic()


def _parse_retry_after(resp) -> float | None:
    """Extract retryAfter seconds from Jina's JSON 429 body."""
    try:
        data = resp.json()
        val = data.get("retryAfter")
        if val is not None:
            return max(float(val), 1.0)
    except Exception:
        pass
    return None


def fetch_fulltext(url: str, timeout: int = 30) -> str:
    """用 Jina Reader 抓取 URL 全文。

    自动限流（≤20 QPS）+ 429 指数退避重试。

    Returns:
        全文文本

    Raises:
        Exception: 抓取失败时抛出
    """
    jina_url = f"{JINA_READER_URL}{url}"

    for attempt in range(_MAX_RETRIES + 1):
        _throttle()
        resp = requests.get(jina_url, timeout=timeout, headers=HEADERS)

        if resp.status_code == 200:
            text = resp.text.strip()
            if not text:
                raise Exception("Jina returned empty content")
            return text

        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp) or (_BACKOFF_BASE * (2 ** attempt))
            if attempt < _MAX_RETRIES:
                print(f"    ⏳ Jina 429, 等待 {retry_after:.1f}s 后重试 ({attempt + 1}/{_MAX_RETRIES})")
                time.sleep(retry_after)
                continue
            raise Exception(f"Jina returned 429 after {_MAX_RETRIES} retries: {resp.text[:200]}")

        # 非 429 错误不重试
        raise Exception(f"Jina returned {resp.status_code}: {resp.text[:200]}")

    raise Exception(f"Jina failed after {_MAX_RETRIES} retries for {url}")
