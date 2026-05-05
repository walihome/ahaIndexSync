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


def fetch_fulltext(url: str, timeout: int = 30) -> tuple[str, float]:
    """用 Jina Reader 抓取 URL 全文。

    Returns:
        (text, quality_score): 全文文本和质量分（0.0-1.0）

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

    # 简单质量评分：基于文本长度
    length = len(text)
    if length < 100:
        quality = 0.1
    elif length < 500:
        quality = 0.3
    elif length < 2000:
        quality = 0.6
    elif length < 5000:
        quality = 0.8
    else:
        quality = 0.9

    return text, quality
