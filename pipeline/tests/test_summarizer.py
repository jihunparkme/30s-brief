import json
import unittest
from datetime import datetime, timezone

from collector import RawItem
from summarizer import GeminiSummarizer, SchemaError, kst_today, validate_regions
from summarizer import client as client_mod


def issue(rank=1, **over):
    base = {
        "rank": rank,
        "keyword": "금리",
        "fact_one_line": "한국은행이 기준금리를 동결했다고 발표했다",
        "market_impact": "대출 이자 부담이 당분간 유지될 수 있다.",
        "watch_point": "다음 금통위 일정",
        "source_name": "Example",
        "source_url": "https://example.com/a",
    }
    base.update(over)
    return base


def ok_body(codes):
    payload = {"regions": [{"region_code": c, "issues": [issue()]} for c in codes]}
    text = json.dumps(payload, ensure_ascii=False)
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]})


def items(*codes):
    return [RawItem("s", c, f"{c} headline", f"https://x/{c}") for c in codes]


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body):
        self.calls.append(json.loads(body))
        return self.responses.pop(0)


class SummarizerTest(unittest.TestCase):
    def make(self, *responses):
        self.sleeps = []
        self.transport = FakeTransport(*responses)
        return GeminiSummarizer("k", transport=self.transport, sleep=self.sleeps.append)

    def test_kst_date_rolls_over_at_15_utc(self):
        self.assertEqual(kst_today(datetime(2026, 11, 18, 14, 59, tzinfo=timezone.utc)), "2026-11-18")
        self.assertEqual(kst_today(datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)), "2026-11-19")

    def test_batches_regions_into_two_calls_with_schema(self):
        s = self.make((200, ok_body(("KR", "US")), {}), (200, ok_body(("JP",)), {}))
        res = s.summarize(items("KR", "US", "JP"))
        self.assertEqual(len(self.transport.calls), 2)
        cfg = self.transport.calls[0]["generationConfig"]
        self.assertEqual(cfg["responseMimeType"], "application/json")
        self.assertIn("responseSchema", cfg)
        self.assertEqual(set(res.regions), {"KR", "US", "JP"})
        self.assertEqual(set(res.failures), {"CN", "EU", "ME"})

    def test_429_backoff_then_success(self):
        s = self.make((429, "", {"Retry-After": "7"}), (429, "", {}), (200, ok_body(("KR",)), {}))
        res = s.summarize(items("KR"))
        self.assertEqual(self.sleeps, [7.0, 4.0])
        self.assertIn("KR", res.regions)

    def test_429_exhausted_marks_batch_failed(self):
        n = client_mod.RATE_LIMIT_RETRIES + 1
        s = self.make(*[(429, "", {})] * n)
        res = s.summarize(items("KR"))
        self.assertTrue(res.all_failed)
        self.assertIn("429", res.failures["KR"])
        self.assertEqual(len(self.sleeps), client_mod.RATE_LIMIT_RETRIES)

    def test_schema_violation_retries_twice_then_succeeds(self):
        bad = json.dumps({"candidates": [{"content": {"parts": [{"text": "{\"regions\": []}"}]}}]})
        s = self.make((200, bad, {}), (200, bad, {}), (200, ok_body(("KR",)), {}))
        self.assertIn("KR", s.summarize(items("KR")).regions)

    def test_schema_violation_exhausted_excludes_region(self):
        bad = json.dumps({"candidates": [{"content": {"parts": [{"text": "not json"}]}}]})
        s = self.make(*[(200, bad, {})] * 3)
        res = s.summarize(items("KR"))
        self.assertTrue(res.all_failed)
        self.assertEqual(len(self.transport.calls), 3)

    def test_non_retryable_status_fails_fast(self):
        s = self.make((400, "", {}))
        res = s.summarize(items("KR"))
        self.assertIn("400", res.failures["KR"])
        self.assertEqual(self.sleeps, [])

    def test_validate_rejects_bad_issues(self):
        def regions(*issues):
            return {"regions": [{"region_code": "KR", "issues": list(issues)}]}

        for bad in (
            regions(),
            regions(issue(market_impact=" ")),
            regions(issue(rank=4)),
            regions(issue(1), issue(1)),
            regions(issue(1), issue(2), issue(3), issue(3)),
        ):
            with self.assertRaises(SchemaError):
                validate_regions(bad, ("KR",))
        out = validate_regions(regions(issue(2), issue(1)), ("KR",))
        self.assertEqual([i["rank"] for i in out["KR"]], [1, 2])

    def test_missing_api_key(self):
        with self.assertRaises(ValueError):
            GeminiSummarizer("")


if __name__ == "__main__":
    unittest.main()
