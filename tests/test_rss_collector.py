from datetime import timezone
import unittest

from app.collectors.rss import collect_rss_items, parse_rss_items


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Liverpool Feed</title>
    <item>
      <guid>https://example.com/liverpool-alexis-mac-allister</guid>
      <title>Liverpool receive Alexis Mac Allister update</title>
      <link>https://example.com/liverpool-alexis-mac-allister</link>
      <description>Liverpool have received a fresh midfield fitness update.</description>
      <pubDate>Sat, 06 Jun 2026 08:30:00 GMT</pubDate>
      <author>reporter@example.com</author>
    </item>
    <item>
      <title>Premier League fixture list latest</title>
      <link>https://example.com/premier-league-fixtures</link>
      <description>General Premier League fixture news.</description>
    </item>
  </channel>
</rss>
"""


class RssCollectorTest(unittest.TestCase):
    def test_parse_rss_items_converts_feed_entries_to_raw_items(self):
        items = parse_rss_items(
            SAMPLE_RSS.encode("utf-8"),
            team_slug="liverpool",
            source_name="Sample Liverpool Feed",
            feed_url="https://example.com/rss",
        )

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].team_slug, "liverpool")
        self.assertEqual(items[0].source_type, "rss")
        self.assertEqual(items[0].source_name, "Sample Liverpool Feed")
        self.assertEqual(items[0].external_id, "https://example.com/liverpool-alexis-mac-allister")
        self.assertEqual(items[0].url, "https://example.com/liverpool-alexis-mac-allister")
        self.assertEqual(items[0].title, "Liverpool receive Alexis Mac Allister update")
        self.assertEqual(items[0].text, "Liverpool have received a fresh midfield fitness update.")
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)
        self.assertEqual(items[0].author, "reporter@example.com")

    def test_collect_rss_items_fetches_url_with_injected_fetcher(self):
        fetched_urls = []

        def fake_fetcher(url):
            fetched_urls.append(url)
            return SAMPLE_RSS.encode("utf-8")

        items = collect_rss_items(
            feed_url="https://example.com/rss",
            team_slug="liverpool",
            source_name="Sample Liverpool Feed",
            fetcher=fake_fetcher,
        )

        self.assertEqual(fetched_urls, ["https://example.com/rss"])
        self.assertEqual(len(items), 2)

    def test_collect_rss_items_uses_article_body_when_extractor_succeeds(self):
        fetched_urls = []

        def fake_fetcher(url):
            fetched_urls.append(url)
            return SAMPLE_RSS.encode("utf-8")

        def fake_article_extractor(url):
            if "alexis-mac-allister" in url:
                return "Full article paragraph one. Full article paragraph two with more Liverpool context."
            return ""

        items = collect_rss_items(
            feed_url="https://example.com/rss",
            team_slug="liverpool",
            source_name="Sample Liverpool Feed",
            fetcher=fake_fetcher,
            article_body_extractor=fake_article_extractor,
        )

        self.assertEqual(fetched_urls, ["https://example.com/rss"])
        self.assertEqual(
            items[0].text,
            "Full article paragraph one. Full article paragraph two with more Liverpool context.",
        )
        self.assertEqual(items[1].text, "General Premier League fixture news.")


if __name__ == "__main__":
    unittest.main()
