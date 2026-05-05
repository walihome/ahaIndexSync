# infra/jina.py
# Jina Reader API wrapper for full-text fetching

from __future__ import annotations

import os
import requests


JINA_READER_URL = "https://r.jina.ai/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_fulltext(url: str, timeout: int = 30) -> str:
    """用 Jina Reader 抓取 URL 全文。

    Returns:
        全文文本

    Raises:
        Exception: 抓取失败时抛出
    """
    jina_url = f"{JINA_READER_URL}{url}"
    resp = requests.get(jina_url, timeout=timeout, headers=HEADERS)

    if resp.status_code != 200:
        raise Exception(f"Jina returned {resp.status_code}: {resp.text[:200]}")

    text = resp.text.strip()
    if not text:
        raise Exception("Jina returned empty content")

    return text
