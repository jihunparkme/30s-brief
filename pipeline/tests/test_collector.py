import unittest

from collector import SOURCES, SourceConfig, collect_all
from collector.adapters import parse_google_news, parse_google_trends

TRENDS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:ht="https://trends.google.com/trending/rss">
<channel><item>
  <title>금리 인하</title>
  <ht:approx_traffic>2000+</ht:approx_traffic>
  <pubDate>Mon, 17 Nov 2026 03:00:00 -0800</pubDate>
  <ht:news_item>
    <ht:news_item_title>&lt;b&gt;한은&lt;/b&gt; 기준금리 동결</ht:news_item_title>
    <ht:news_item_url>https://example.com/a</ht:news_item_url>
    <ht:news_item_source>Example</ht:news_item_source>
  </ht:news_item>
</item><item><title></title></item></channel></rss>"""

NEWS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>Oil jumps on supply fears - Reuters</title>
<link>https://news.google.com/x1</link>
<pubDate>Mon, 17 Nov 2026 10:00:00 GMT</pubDate>
<source url="https://reuters.com">Reuters</source></item>
<item><title>no link</title></item>
</channel></rss>"""

TRENDS_SRC = SourceConfig("t", "KR", "google_trends", "u1")
NEWS_SRC = SourceConfig("n", "ME", "google_news", "u2")


class AdapterTests(unittest.TestCase):
    def test_trends(self):
        items = parse_google_trends(TRENDS_XML, TRENDS_SRC)
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it.title, "금리 인하")
        self.assertEqual(it.url, "https://example.com/a")
        self.assertEqual(it.related[0].source, "Example")
        self.assertEqual(it.related[0].title, "한은 기준금리 동결")
        self.assertIsNotNone(it.published_at.tzinfo)

    def test_news_strips_outlet(self):
        items = parse_google_news(NEWS_XML, NEWS_SRC)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Oil jumps on supply fears")
        self.assertEqual(items[0].related[0].source, "Reuters")


class CollectAllTests(unittest.TestCase):
    def test_partial_failure_keeps_successes(self):
        def fetch(url):
            if url == "u2":
                raise OSError("boom")
            return TRENDS_XML

        res = collect_all([TRENDS_SRC, NEWS_SRC], fetch)
        self.assertEqual(len(res.items), 1)
        self.assertEqual([f.source_id for f in res.failures], ["n"])
        self.assertFalse(res.all_failed)

    def test_all_failed(self):
        def fetch(url):
            raise OSError("down")

        res = collect_all([TRENDS_SRC], fetch)
        self.assertTrue(res.all_failed)

    def test_malformed_xml_isolated(self):
        res = collect_all([TRENDS_SRC], lambda u: "<not xml")
        self.assertEqual(res.failures[0].source_id, "t")

    def test_dedupe_same_url_in_region(self):
        res = collect_all([TRENDS_SRC, SourceConfig("t2", "KR", "google_trends", "u3")], lambda u: TRENDS_XML)
        self.assertEqual(len(res.items), 1)

    def test_registry_valid(self):
        regions = {s.region_code for s in SOURCES}
        self.assertEqual(regions, {"KR", "US", "CN", "JP", "EU", "ME"})
        self.assertEqual(len({s.id for s in SOURCES}), len(SOURCES))


if __name__ == "__main__":
    unittest.main()
