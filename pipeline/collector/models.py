from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class RelatedArticle:
    title: str
    url: str
    source: Optional[str] = None


@dataclass(frozen=True)
class RawItem:
    """소스 어댑터가 공통으로 반환하는 수집 결과 단위."""

    source_id: str
    region_code: str
    title: str
    url: str
    snippet: str = ""
    published_at: Optional[datetime] = None
    related: tuple[RelatedArticle, ...] = ()


@dataclass(frozen=True)
class SourceConfig:
    id: str
    region_code: str
    kind: str  # "google_trends" | "google_news"
    url: str


@dataclass
class SourceFailure:
    source_id: str
    error: str


@dataclass
class CollectResult:
    items: list[RawItem] = field(default_factory=list)
    failures: list[SourceFailure] = field(default_factory=list)

    @property
    def all_failed(self) -> bool:
        return not self.items and bool(self.failures)
