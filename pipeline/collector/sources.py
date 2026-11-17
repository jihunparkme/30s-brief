from __future__ import annotations

from .models import SourceConfig

_TRENDS = "https://trends.google.com/trending/rss?geo={geo}"
_NEWS_SEARCH = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def _news(q: str, hl: str, gl: str, ceid: str) -> str:
    return _NEWS_SEARCH.format(q=q, hl=hl, gl=gl, ceid=ceid)


SOURCES: tuple[SourceConfig, ...] = (
    SourceConfig("trends_kr", "KR", "google_trends", _TRENDS.format(geo="KR")),
    SourceConfig(
        "news_kr_business",
        "KR",
        "google_news",
        "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko",
    ),
    SourceConfig("trends_us", "US", "google_trends", _TRENDS.format(geo="US")),
    SourceConfig(
        "news_us_bloomberg",
        "US",
        "google_news",
        _news("site:bloomberg.com+when:1d", "en-US", "US", "US:en"),
    ),
    SourceConfig("trends_jp", "JP", "google_trends", _TRENDS.format(geo="JP")),
    SourceConfig("trends_gb", "EU", "google_trends", _TRENDS.format(geo="GB")),
    SourceConfig("trends_de", "EU", "google_trends", _TRENDS.format(geo="DE")),
    SourceConfig(
        "news_eu_bbc",
        "EU",
        "google_news",
        _news("site:bbc.com+world+when:1d", "en-GB", "GB", "GB:en"),
    ),
    SourceConfig(
        "news_cn_scmp",
        "CN",
        "google_news",
        _news("site:scmp.com+when:1d", "en-US", "US", "US:en"),
    ),
    SourceConfig(
        "news_cn_kr_economy",
        "CN",
        "google_news",
        _news("중국+경제+when:1d", "ko", "KR", "KR:ko"),
    ),
    SourceConfig(
        "news_me_aljazeera",
        "ME",
        "google_news",
        _news("site:aljazeera.com+when:1d", "en-US", "US", "US:en"),
    ),
    SourceConfig(
        "news_me_reuters",
        "ME",
        "google_news",
        _news("site:reuters.com+middle+east+when:1d", "en-US", "US", "US:en"),
    ),
)
