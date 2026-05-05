# infra/models.py

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawItem:
    title: str
    original_url: str
    source_name: str
    source_type: str
    content_type: str
    author: str = ""
    author_url: str = ""
    body_text: str = ""
    raw_metrics: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    published_at: Optional[datetime] = None
    content_source: str = "scraper"
    content_quality: Optional[float] = None

    @property
    def id(self) -> str:
        return hashlib.md5(self.original_url.encode()).hexdigest()

    def to_db_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "original_url": self.original_url,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "author": self.author,
            "author_url": self.author_url,
            "body_text": self.body_text,
            "raw_metrics": self.raw_metrics,
            "extra": self.extra,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "content_source": self.content_source,
            "content_quality": self.content_quality,
        }


class BaseScraper:
    """配置驱动的抓取引擎基类。"""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config

    def fetch(self) -> list[RawItem]:
        raise NotImplementedError
