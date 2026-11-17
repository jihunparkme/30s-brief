from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Callable, Iterable, Optional

from .adapters import ADAPTERS
from .models import CollectResult, RawItem, SourceConfig, SourceFailure
from .sources import SOURCES

log = logging.getLogger(__name__)

USER_AGENT = "30s-brief-collector/1.0 (+https://github.com/jihunparkme/30s-brief)"
TIMEOUT_SEC = 15
RETRIES = 2

Fetcher = Callable[[str], str]


def http_fetch(url: str) -> str:
    url = urllib.parse.quote(url, safe=":/?&=+%@,;")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8")


def _dedupe(items: Iterable[RawItem]) -> list[RawItem]:
    seen: set[tuple[str, str]] = set()
    out: list[RawItem] = []
    for it in items:
        key = (it.region_code, it.url or it.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def collect_source(source: SourceConfig, fetch: Fetcher = http_fetch) -> list[RawItem]:
    adapter = ADAPTERS[source.kind]
    last_exc: Optional[Exception] = None
    for _ in range(RETRIES + 1):
        try:
            return adapter(fetch(source.url), source)
        except Exception as exc:  # 네트워크·파싱 오류 모두 소스 단위로 격리
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def collect_all(
    sources: Iterable[SourceConfig] = SOURCES, fetch: Fetcher = http_fetch
) -> CollectResult:
    """일부 소스가 실패해도 성공한 소스의 결과를 반환하고 실패는 기록한다."""
    result = CollectResult()
    for source in sources:
        try:
            result.items.extend(collect_source(source, fetch))
        except Exception as exc:
            log.warning("source %s failed: %s", source.id, exc)
            result.failures.append(SourceFailure(source.id, f"{type(exc).__name__}: {exc}"))
    result.items = _dedupe(result.items)
    return result
