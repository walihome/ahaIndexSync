# infra/models.py

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Any


@dataclass
class RawItem:
    title: str
    original_url: str
    source_name: str
    source_type: str
    content_type: str
    author: str = ""
    author_url: str = ""
    body_text: str = ""  # Python-only: scrapers 设置，不写入 DB（已迁移到 items_content.raw_body）
    raw_metrics: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    published_at: Optional[datetime] = None
    # 阶段 5 新增字段
    snapshot_date: Optional[date] = None
    scraper_slug: str = ""
    scraper_config_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return hashlib.md5(self.original_url.encode()).hexdigest()

    def to_db_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "original_url": self.original_url,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "author": self.author,
            "author_url": self.author_url,
            "raw_metrics": self.raw_metrics,
            "extra": self.extra,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }
        # 阶段 5 字段：有值时才写入，避免覆盖历史数据
        if self.snapshot_date is not None:
            d["snapshot_date"] = self.snapshot_date.isoformat()
        if self.scraper_slug:
            d["scraper_slug"] = self.scraper_slug
        if self.scraper_config_snapshot:
            d["scraper_config_snapshot"] = self.scraper_config_snapshot
        return d


@dataclass
class ContentRecord:
    """items_content 表的内存视图。与 raw_items 1:1 关联。"""
    item_id: str
    raw_body: Optional[str] = None
    enriched_body: Optional[str] = None
    enriched_source: Optional[str] = None       # 'jina' / 'trafilatura' / None
    enriched_quality: Optional[float] = None
    enriched_at: Optional[datetime] = None
    fetch_attempts: int = 0
    last_fetch_error: Optional[str] = None

    @property
    def body(self) -> str:
        """下游统一取内容：优先全文，回退到原始摘要。"""
        return self.enriched_body or self.raw_body or ""


class BaseScraper:
    """配置驱动的抓取引擎基类。"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    def fetch(self) -> list[RawItem]:
        raise NotImplementedError
