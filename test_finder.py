import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("finder", Path(__file__).parents[1] / "scripts" / "finder.py")
finder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finder)

class FinderTests(unittest.TestCase):
    def test_canonical_strips_tracking(self):
        self.assertEqual(finder.canonical("https://Example.org/x?utm_source=a&room=2#x"), "https://example.org/x?room=2")

    def test_rss_preserves_publisher_and_date(self):
        xml = b'<rss><channel><item><title>Hotel offer in Istria</title><link>https://news.google.com/rss/articles/xyz</link><description>Family hotel deal</description><pubDate>Tue, 20 Oct 2026 09:00:00 GMT</pubDate><source url="https://publisher.example/">Travel Desk</source></item></channel></rss>'
        rows = finder.parse_feed(xml, "Google News RSS")
        self.assertEqual(rows[0]["title"], "Hotel offer in Istria")
        self.assertEqual(rows[0]["publisher"], "Travel Desk")
        self.assertEqual(rows[0]["publisher_url"], "https://publisher.example/")
        self.assertTrue(rows[0]["published_at"].startswith("2026-10-20"))

    def test_atom_uses_alternate_link(self):
        xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Family stay</title><link rel="self" href="https://example.org/feed"/><link rel="alternate" href="https://example.org/story"/><summary>Hotel package</summary><updated>2026-10-20T10:00:00Z</updated></entry></feed>'
        row = finder.parse_feed(xml, "Atom")
        self.assertEqual(row[0]["url"], "https://example.org/story")
        self.assertEqual(row[0]["snippet"], "Hotel package")

    def test_price_localized_thousands(self):
        self.assertEqual(finder.price_mention("Family stay 1.299 €", "EUR"), 1299)
        self.assertEqual(finder.price_mention("Price EUR 1.299,50", "EUR"), 1299.5)
        self.assertIsNone(finder.price_mention("Good summer", "EUR"))

    def test_localized_queries(self):
        result = finder.queries({"destinations": ["Istria"], "countries": ["Hrvatska"]})
        locale, query = result[0]
        self.assertIn("Istria", query)
        self.assertEqual(locale["gl"], "HR")
        self.assertIn("ponuda", query)

    def test_cross_feed_merge_prefers_publisher_article_link(self):
        published = (datetime.now(timezone.utc)-timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        prefix = '<rss><channel><item><title>Family hotel deal in Istria</title>'
        middle = '<description>Hotel offer in Istria</description><pubDate>' + published + '</pubDate><source url="https://publisher.example/">Travel Desk</source></item></channel></rss>'
        google = (prefix + '<link>https://news.google.com/rss/articles/opaque</link>' + middle).encode()
        bing = (prefix + '<link>https://publisher.example/story</link>' + middle).encode()
        class Response:
            status_code = 200
            headers = {}
            def __init__(self, content): self.content = content
            def raise_for_status(self): return None
        responses = [Response(google), Response(bing), Response(google), Response(bing)]
        filters = {"destinations": ["Istria"], "countries": ["Hrvatska"], "accommodation": "hotel", "currency": "EUR"}
        with patch.object(finder.SESSION, "get", side_effect=responses), patch.object(finder.time, "sleep"), patch.object(finder, "public_deal_offers", return_value=[]):
            rows = finder.find(filters)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["url"], "https://publisher.example/story")
        self.assertEqual(set(rows[0]["sources"]), {"Google News RSS", "Bing News RSS"})
        self.assertEqual(rows[0]["evidence_grade"], "jači trag")

    def test_same_rss_query_is_cached_within_process(self):
        class Response:
            status_code = 200
            headers = {}
            content = b"<rss><channel></channel></rss>"
            def raise_for_status(self): return None
        with patch.object(finder.SESSION, "get", return_value=Response()) as getter:
            finder.fetch_feed("https://cache-test.example/rss", {"q": "unique-test-query"})
            finder.fetch_feed("https://cache-test.example/rss", {"q": "unique-test-query"})
        self.assertEqual(getter.call_count, 1)

    def test_public_deal_feed_requires_place_and_stay_match(self):
        lead = {"title": "Hotel package in Istria", "snippet": "Family stay", "publisher": "Travelzoo"}
        self.assertTrue(finder.relevant_public_deal(lead, {"destinations": ["Istria"], "countries": ["Hrvatska"]}))
        self.assertFalse(finder.relevant_public_deal(lead, {"destinations": ["Tuscany"], "countries": ["Italy"]}))
        self.assertFalse(finder.relevant_public_deal({"title": "Flight deal to Istria", "snippet": "cheap flights"}, {"destinations": ["Istria"], "countries": []}))

    def test_stale_result_does_not_score_as_fresh(self):
        reference = datetime(2026, 10, 23, tzinfo=timezone.utc)
        offer = {"title": "Hotel deal in Istria", "snippet": "Family package", "publisher": "Publisher", "published_at": (reference-timedelta(days=5)).isoformat(), "sources": ["Google", "Bing"]}
        result = finder.rank(offer, {"destinations": ["Istria"], "countries": [], "currency": "EUR"}, reference)
        self.assertEqual(result[3]["freshness"], "objavljeno prije 5 dana")
        self.assertEqual(result[3]["evidence_grade"], "jači trag")

    def test_feature_match_is_not_mistaken_for_destination_match(self):
        reference = datetime.now(timezone.utc)
        offer = {"title": "Hotel with pool offer", "snippet": "Fresh family package", "publisher": "Publisher", "published_at": reference.isoformat(), "sources": ["Google"]}
        result = finder.rank(offer, {"destinations": ["Istria"], "countries": [], "features": ["pool"], "currency": "EUR"}, reference)
        self.assertIn("pool", result[1])
        self.assertIn("destinacija nije potvrđena", "; ".join(result[3]["evidence"]))
        self.assertNotEqual(result[3]["evidence_grade"], "jači trag")

    def test_management_token_secret_dependent(self):
        os.environ["MANAGE_TOKEN_SECRET"] = "first-secret"
        first = finder.management_token("subscription-id")
        self.assertEqual(first, finder.management_token("subscription-id"))
        os.environ["MANAGE_TOKEN_SECRET"] = "second-secret"
        self.assertNotEqual(first, finder.management_token("subscription-id"))

if __name__ == "__main__":
    unittest.main()
