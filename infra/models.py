# infra/models.py
# 数据模型定义，全项目唯一的 RawItem 来源

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawItem:
    title: str
    original_url: str
    source_name: str       # "GitHub" / "OpenAI Blog" / "HackerNews" / "X"
    source_type: str       # "REPO" / "BLOG" / "NEWS" / "TWEET"
    content_type: str      # "repo" / "article" / "tweet"
    author: str = ""
    author_url: str = ""
    body_text: str = ""
    raw_metrics: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)
    published_at: Optional[datetime] = None

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
        }


class BaseScraper:
    """所有抓取器的基类"""
    source_name: str = ""
    source_type: str = ""
    content_type: str = ""

    def fetch(self) -> list[RawItem]:
        raise NotImplementedError