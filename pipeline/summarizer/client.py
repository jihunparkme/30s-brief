from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence

from collector.collector import _ssl_context
from collector.models import RawItem

from .schema import RESPONSE_SCHEMA, SchemaError, validate_regions

log = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
DEFAULT_MODEL = "gemini-2.5-flash"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# 무료 쿼터 보호를 위해 6개 권역을 2회 호출로 묶는다.
REGION_BATCHES: tuple[tuple[str, ...], ...] = (("KR", "US", "CN"), ("JP", "EU", "ME"))
MAX_ITEMS_PER_REGION = 30
SCHEMA_RETRIES = 2  # PRD US-9: 스키마 위반 시 최대 2회 재시도
RATE_LIMIT_RETRIES = 4
BACKOFF_BASE_SEC = 2.0
BACKOFF_MAX_SEC = 60.0
TIMEOUT_SEC = 60

SYSTEM_PROMPT = (
    "당신은 출근길 30초 브리핑 에디터입니다. 권역별 헤드라인을 읽고 권역당 이슈 최대 3개를 rank 순으로 고릅니다. "
    "각 이슈: keyword(핵심 단어), fact_one_line(팩트 한 문장, 40~55자), "
    "market_impact(내 지갑·일상 영향 1문장, 비단정 문체, 투자 권유 금지), watch_point(향후 관전 포인트 1줄), "
    "source_name·source_url(입력에 있는 출처만). 입력에 없는 사실·수치를 만들지 마세요."
)

# (url, headers, body) -> (status, response_text, response_headers)
Transport = Callable[[str, dict, bytes], "tuple[int, str, dict]"]


class GeminiError(RuntimeError):
    pass


class RateLimitError(GeminiError):
    pass


def kst_today(now: Optional[datetime] = None) -> str:
    """briefing_date에 쓰는 KST 기준 일자(YYYY-MM-DD)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(KST).date().isoformat()


def urllib_transport(url: str, headers: dict, body: bytes) -> tuple[int, str, dict]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC, context=_ssl_context()) as resp:
            return resp.status, resp.read().decode("utf-8"), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace"), dict(e.headers or {})


@dataclass
class SummaryResult:
    briefing_date: str
    regions: dict[str, list[dict]] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)  # region_code -> 사유

    @property
    def all_failed(self) -> bool:
        return not self.regions


class GeminiSummarizer:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 필요합니다")
        self._api_key = api_key
        self._model = model
        self._transport = transport
        self._sleep = sleep

    def summarize(
        self, items: Sequence[RawItem], now: Optional[datetime] = None
    ) -> SummaryResult:
        result = SummaryResult(briefing_date=kst_today(now))
        for batch in REGION_BATCHES:
            grouped = {
                c: [i for i in items if i.region_code == c][:MAX_ITEMS_PER_REGION] for c in batch
            }
            codes = tuple(c for c in batch if grouped[c])
            for c in batch:
                if not grouped[c]:
                    result.failures[c] = "입력 헤드라인 없음"
            if not codes:
                continue
            try:
                result.regions.update(self._summarize_batch(codes, grouped, result.briefing_date))
            except GeminiError as e:
                log.error("권역 %s 요약 실패: %s", ",".join(codes), e)
                for c in codes:
                    result.failures[c] = str(e)
        return result

    def _summarize_batch(
        self, codes: tuple[str, ...], grouped: dict[str, list[RawItem]], date: str
    ) -> dict[str, list[dict]]:
        prompt = _build_prompt(codes, grouped, date)
        last: Optional[SchemaError] = None
        for attempt in range(SCHEMA_RETRIES + 1):
            text = self._generate(prompt)
            try:
                return validate_regions(json.loads(text), codes)
            except (json.JSONDecodeError, SchemaError) as e:
                last = e if isinstance(e, SchemaError) else SchemaError(f"JSON 파싱 실패: {e}")
                log.warning("스키마 위반 (%d/%d): %s", attempt + 1, SCHEMA_RETRIES + 1, last)
        raise GeminiError(f"스키마 위반으로 재시도 소진: {last}")

    def _generate(self, prompt: str) -> str:
        body = json.dumps(
            {
                "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": RESPONSE_SCHEMA,
                    "temperature": 0.2,
                },
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._api_key}
        url = API_URL.format(model=self._model)

        for attempt in range(RATE_LIMIT_RETRIES + 1):
            status, text, resp_headers = self._transport(url, headers, body)
            if status == 200:
                return _extract_text(text)
            if not (status == 429 or 500 <= status < 600):
                raise GeminiError(f"Gemini API 오류 HTTP {status}")
            if attempt == RATE_LIMIT_RETRIES:
                cls = RateLimitError if status == 429 else GeminiError
                raise cls(f"Gemini API HTTP {status}: 재시도 소진")
            delay = _backoff_delay(attempt, resp_headers)
            log.warning(
                "HTTP %d, %.1fs 후 재시도 (%d/%d)", status, delay, attempt + 1, RATE_LIMIT_RETRIES
            )
            self._sleep(delay)
        raise GeminiError("unreachable")


def _backoff_delay(attempt: int, headers: dict) -> float:
    retry_after = {k.lower(): v for k, v in headers.items()}.get("retry-after")
    if retry_after:
        try:
            return min(max(float(retry_after), 0.0), BACKOFF_MAX_SEC)
        except ValueError:
            pass
    return min(BACKOFF_BASE_SEC * (2**attempt), BACKOFF_MAX_SEC)


def _extract_text(raw: str) -> str:
    try:
        return json.loads(raw)["candidates"][0]["content"]["parts"][0]["text"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as e:
        raise GeminiError(f"응답 형식 오류(차단·빈 응답 가능): {e!r}")


def _build_prompt(codes: tuple[str, ...], grouped: dict[str, list[RawItem]], date: str) -> str:
    lines = [f"기준일(KST): {date}", f"대상 권역: {', '.join(codes)}", ""]
    for code in codes:
        lines.append(f"## {code}")
        for n, it in enumerate(grouped[code], 1):
            src = it.related[0].source if it.related and it.related[0].source else ""
            extra = f" | {it.snippet}" if it.snippet else ""
            lines.append(f"{n}. {it.title}{extra} | 출처:{src} | {it.url}")
        lines.append("")
    return "\n".join(lines)
