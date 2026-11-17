from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from collections import Counter

from .collector import collect_all
from .sources import SOURCES


def _serialize(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    raise TypeError(type(obj).__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="collector", description="RSS 수집기")
    parser.add_argument("--source", action="append", help="수집할 소스 ID (반복 가능, 기본: 전체)")
    parser.add_argument("--region", action="append", help="수집할 권역 코드 (반복 가능)")
    parser.add_argument("--list", action="store_true", help="등록된 소스 목록 출력 후 종료")
    parser.add_argument("--json", action="store_true", help="수집 결과 전체를 JSON으로 출력")
    parser.add_argument("--limit", type=int, default=5, help="요약 출력 시 권역당 미리보기 건수")
    args = parser.parse_args(argv)

    if args.list:
        for s in SOURCES:
            print(f"{s.id}\t{s.region_code}\t{s.kind}\t{s.url}")
        return 0

    sources = [
        s
        for s in SOURCES
        if (not args.source or s.id in args.source)
        and (not args.region or s.region_code in args.region)
    ]
    unknown = set(args.source or []) - {s.id for s in SOURCES}
    if unknown:
        parser.error(f"알 수 없는 소스: {', '.join(sorted(unknown))}")
    if not sources:
        parser.error("조건에 맞는 소스가 없습니다")

    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    result = collect_all(sources)

    if args.json:
        payload = {
            "items": [dataclasses.asdict(i) for i in result.items],
            "failures": [dataclasses.asdict(f) for f in result.failures],
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=_serialize)
        print()
    else:
        print(f"수집 {len(result.items)}건 / 실패 소스 {len(result.failures)}개")
        for sid, n in Counter(i.source_id for i in result.items).items():
            print(f"  {sid}: {n}")
        for f in result.failures:
            print(f"  [실패] {f.source_id}: {f.error}")
        shown: Counter = Counter()
        for it in result.items:
            if shown[it.region_code] < args.limit:
                shown[it.region_code] += 1
                print(f"[{it.region_code}] {it.title} | {it.url}")

    return 1 if result.all_failed else 0


if __name__ == "__main__":
    sys.exit(main())
