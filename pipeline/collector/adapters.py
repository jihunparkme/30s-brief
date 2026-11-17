from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Optional

from .models import RawItem, RelatedArticle, SourceConfig

HT_NS = "{https://trends.google.com/trending/rss}"
_TAG_RE = re.compile(r"<[^>]+>")


def _text(el: Optional[ET.Element]) -> str:
    return (el.text or "").strip() if el is not None else ""


def _clean(raw: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", raw)).split())


def _parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _channel_items(xml_text: str) -> list[ET.Element]:
    root = ET.fromstring(xml_text)
    return root.findall("./channel/item")


def parse_google_trends(xml_text: str, source: SourceConfig) -> list[RawItem]:
    """검색 급등 키워드 1건을 이슈 후보 1건으로 변환하고 ht:news_item은 related로 보존."""
    items: list[RawItem] = []
    for el in _channel_items(xml_text):
        title = _text(el.find("title"))
        if not title:
            continue
        related = tuple(
            RelatedArticle(
                title=_clean(_text(n.find(f"{HT_NS}news_item_title"))),
                url=_text(n.find(f"{HT_NS}news_item_url")),
                source=_text(n.find(f"{HT_NS}news_item_source")) or None,
            )
            for n in el.findall(f"{HT_NS}news_item")
            if _text(n.find(f"{HT_NS}news_item_url"))
        )
        snippet = " / ".join(r.title for r in related if r.title)
        items.append(
            RawItem(
                source_id=source.id,
                region_code=source.region_code,
                title=title,
                # <link>는 피드 URL로 고정되어 있어 대표 기사 URL을 우선 사용
                url=related[0].url if related else _text(el.find("link")),
                snippet=snippet,
                published_at=_parse_date(_text(el.find("pubDate"))),
                related=related,
            )
        )
    return items


def parse_google_news(xml_text: str, source: SourceConfig) -> list[RawItem]:
    items: list[RawItem] = []
    for el in _channel_items(xml_text):
        title = _clean(_text(el.find("title")))
        url = _text(el.find("link"))
        if not title or not url:
            continue
        src_el = el.find("source")
        outlet = _text(src_el) or None
        # Google News 제목은 "헤드라인 - 매체명" 형태
        if outlet and title.endswith(f" - {outlet}"):
            title = title[: -len(outlet) - 3].rstrip()
        items.append(
            RawItem(
                source_id=source.id,
                region_code=source.region_code,
                title=title,
                url=url,
                snippet="",
                published_at=_parse_date(_text(el.find("pubDate"))),
                related=(RelatedArticle(title=title, url=url, source=outlet),),
            )
        )
    return items


ADAPTERS: dict[str, Callable[[str, SourceConfig], list[RawItem]]] = {
    "google_trends": parse_google_trends,
    "google_news": parse_google_news,
}
