from __future__ import annotations

REGIONS = ("KR", "US", "CN", "JP", "EU", "ME")
MAX_ISSUES_PER_REGION = 3

_ISSUE_FIELDS = (
    "rank",
    "keyword",
    "fact_one_line",
    "market_impact",
    "watch_point",
    "source_name",
    "source_url",
)

_ISSUE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        name: {"type": "INTEGER" if name == "rank" else "STRING"} for name in _ISSUE_FIELDS
    },
    "required": list(_ISSUE_FIELDS),
    "propertyOrdering": list(_ISSUE_FIELDS),
}

# Gemini responseSchema (OpenAPI 서브셋). 필드는 issues 테이블 컬럼과 맞춘다.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "regions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "region_code": {"type": "STRING", "enum": list(REGIONS)},
                    "issues": {
                        "type": "ARRAY",
                        "items": _ISSUE_SCHEMA,
                        "maxItems": MAX_ISSUES_PER_REGION,
                    },
                },
                "required": ["region_code", "issues"],
            },
        }
    },
    "required": ["regions"],
}

_ISSUE_TEXT_FIELDS = ("keyword", "fact_one_line", "market_impact", "source_name", "source_url")


class SchemaError(ValueError):
    """모델 출력이 JSON Schema(또는 업무 규칙)를 위반했을 때."""


def validate_regions(payload: object, expected: tuple[str, ...]) -> dict[str, list[dict]]:
    """파싱된 응답을 검증하고 {region_code: [issue, ...]} (rank 오름차순)로 반환한다."""
    if not isinstance(payload, dict) or not isinstance(payload.get("regions"), list):
        raise SchemaError("최상위 'regions' 배열이 없습니다")

    out: dict[str, list[dict]] = {}
    for region in payload["regions"]:
        if not isinstance(region, dict):
            raise SchemaError("regions 항목이 객체가 아닙니다")
        code = region.get("region_code")
        if code not in expected:
            raise SchemaError(f"요청하지 않은 region_code: {code!r}")
        if code in out:
            raise SchemaError(f"region_code 중복: {code}")
        issues = region.get("issues")
        if not isinstance(issues, list) or not 1 <= len(issues) <= MAX_ISSUES_PER_REGION:
            raise SchemaError(f"{code}: issues는 1~{MAX_ISSUES_PER_REGION}개여야 합니다")
        out[code] = _validate_issues(code, issues)

    missing = [c for c in expected if c not in out]
    if missing:
        raise SchemaError(f"응답에 없는 권역: {', '.join(missing)}")
    return out


def _validate_issues(code: str, issues: list) -> list[dict]:
    ranks: set[int] = set()
    for issue in issues:
        if not isinstance(issue, dict):
            raise SchemaError(f"{code}: issue가 객체가 아닙니다")
        rank = issue.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or not 1 <= rank <= MAX_ISSUES_PER_REGION:
            raise SchemaError(f"{code}: rank는 1~{MAX_ISSUES_PER_REGION} 정수여야 합니다")
        if rank in ranks:
            raise SchemaError(f"{code}: rank 중복 {rank}")
        ranks.add(rank)
        for name in _ISSUE_TEXT_FIELDS:
            value = issue.get(name)
            if not isinstance(value, str) or not value.strip():
                raise SchemaError(f"{code}#{rank}: '{name}'이 비어 있습니다")
        if len(issue["keyword"]) > 100 or len(issue["source_name"]) > 100:
            raise SchemaError(f"{code}#{rank}: keyword/source_name은 100자 이하여야 합니다")
        if not isinstance(issue.get("watch_point"), str):
            raise SchemaError(f"{code}#{rank}: watch_point는 문자열이어야 합니다")
    return sorted(issues, key=lambda i: i["rank"])
