from datetime import datetime, timezone
import unittest

from app.collectors.html_listing import (
    collect_html_listing_items,
    parse_article_published_at_from_html,
    parse_future_fixture_datetime_from_html,
    parse_listing_links,
)


class HtmlListingCollectorTest(unittest.TestCase):
    def test_parse_listing_links_keeps_article_like_links_on_same_host(self):
        html = """
        <main>
            <a href="/news/liverpool-transfer-update">Liverpool transfer update latest</a>
            <a href="https://example.com/sport/football/articles/slot-interview">Arne Slot interview reaction</a>
            <a href="https://other.example.com/news/liverpool">External Liverpool link</a>
            <a href="/contact">Contact</a>
        </main>
        """

        links = parse_listing_links(html, listing_url="https://example.com/football/liverpool")

        self.assertEqual(
            links,
            [
                ("Liverpool transfer update latest", "https://example.com/news/liverpool-transfer-update"),
                ("Arne Slot interview reaction", "https://example.com/sport/football/articles/slot-interview"),
            ],
        )

    def test_parse_listing_links_applies_required_terms_and_skips_navigation_links(self):
        html = """
        <a href="/sport/football/world-cup">Football 2026</a>
        <a href="/sport/football/teams/liverpool/scores-fixtures">Scores & Fixtures</a>
        <a href="/liverpool-women">Liverpool Women</a>
        <a href="/sport/football/articles/c4gv1ydm4yro">Liverpool next manager</a>
        """

        links = parse_listing_links(
            html,
            listing_url="https://www.bbc.com/sport/football/teams/liverpool",
            required_terms=("liverpool",),
        )

        self.assertEqual(
            links,
            [("Liverpool next manager", "https://www.bbc.com/sport/football/articles/c4gv1ydm4yro")],
        )

    def test_parse_listing_links_applies_excluded_terms(self):
        html = """
        <a href="/news/liverpools-greatest-no83-vladimir-smicer">Liverpool's greatest No.83: Vladimir Smicer</a>
        <a href="/news/liverpool-transfer-update">Liverpool transfer update latest</a>
        """

        links = parse_listing_links(
            html,
            listing_url="https://www.liverpoolfc.com/news",
            excluded_terms=("greatest",),
        )

        self.assertEqual(
            links,
            [("Liverpool transfer update latest", "https://www.liverpoolfc.com/news/liverpool-transfer-update")],
        )

    def test_collect_html_listing_items_fetches_body_for_links(self):
        listing_html = """
        <a href="/news/liverpool-transfer-update">Liverpool transfer update latest</a>
        """
        article_html = """
        <html><head>
            <meta property="article:published_time" content="2026-06-06T09:30:00Z">
        </head></html>
        """

        def fetcher(url):
            if url == "https://example.com/liverpool":
                return listing_html.encode("utf-8")
            if url == "https://example.com/news/liverpool-transfer-update":
                return article_html.encode("utf-8")
            raise AssertionError(f"Unexpected URL: {url}")

        items = collect_html_listing_items(
            listing_url="https://example.com/liverpool",
            team_slug="liverpool",
            source_name="Example Liverpool",
            fetcher=fetcher,
            article_body_extractor=lambda url: f"본문: {url}",
            required_terms=("liverpool",),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_type, "html_listing")
        self.assertEqual(items[0].source_name, "Example Liverpool")
        self.assertEqual(items[0].url, "https://example.com/news/liverpool-transfer-update")
        self.assertEqual(items[0].title, "Liverpool transfer update latest")
        self.assertEqual(items[0].text, "본문: https://example.com/news/liverpool-transfer-update")
        self.assertEqual(items[0].published_at, datetime(2026, 6, 6, 9, 30, tzinfo=timezone.utc))

    def test_collect_html_listing_items_falls_back_to_collection_time_without_article_date(self):
        listing_html = """
        <a href="/news/liverpool-transfer-update">Liverpool transfer update latest</a>
        """

        def fetcher(url):
            return listing_html.encode("utf-8")

        items = collect_html_listing_items(
            listing_url="https://example.com/liverpool",
            team_slug="liverpool",
            source_name="Example Liverpool",
            fetcher=fetcher,
            article_body_extractor=lambda url: f"본문: {url}",
            required_terms=("liverpool",),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)

    def test_collect_html_listing_items_uses_future_fixture_datetime(self):
        published_at = datetime(2026, 6, 7, 3, 0, tzinfo=timezone.utc)
        listing_html = """
        <a href="/football/liverpool-vs-leeds-united/554987">Liverpool vs Leeds United</a>
        """
        article_html = """
        <main>
            Liverpool vs Leeds United. Friendly Match.
            9:00pm, Sunday 2nd August 2026.
            Soldier Field.
        </main>
        """

        def fetcher(url):
            if url == "https://www.skysports.com/liverpool":
                return listing_html.encode("utf-8")
            if url == "https://www.skysports.com/football/liverpool-vs-leeds-united/554987":
                return article_html.encode("utf-8")
            raise AssertionError(f"Unexpected URL: {url}")

        items = collect_html_listing_items(
            listing_url="https://www.skysports.com/liverpool",
            team_slug="liverpool",
            source_name="Sky Sports - Liverpool",
            fetcher=fetcher,
            article_body_extractor=lambda url: "Liverpool vs Leeds United. Friendly Match.",
            article_published_at_extractor=lambda url: published_at,
            required_terms=("liverpool",),
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].published_at, published_at)
        self.assertEqual(items[0].event_at, datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc))

    def test_parse_article_published_at_from_meta_tags(self):
        page_html = """
        <meta property="article:published_time" content="2026-06-06T09:30:00Z">
        """

        published_at = parse_article_published_at_from_html(page_html)

        self.assertEqual(published_at, datetime(2026, 6, 6, 9, 30, tzinfo=timezone.utc))

    def test_parse_article_published_at_from_time_tag(self):
        page_html = """
        <time datetime="2026-06-06T18:45:00+09:00">6 June 2026</time>
        """

        published_at = parse_article_published_at_from_html(page_html)

        self.assertEqual(published_at, datetime(2026, 6, 6, 9, 45, tzinfo=timezone.utc))

    def test_parse_future_fixture_datetime_from_sky_match_text(self):
        page_html = """
        Liverpool vs Leeds United. Friendly Match.
        9:00pm, Sunday 2nd August 2026.
        Soldier Field.
        """

        fixture_at = parse_future_fixture_datetime_from_html(
            page_html,
            collected_at=datetime(2026, 6, 7, 3, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(fixture_at, datetime(2026, 8, 2, 20, 0, tzinfo=timezone.utc))

    def test_parse_future_fixture_datetime_ignores_past_match_text(self):
        page_html = """
        Liverpool vs Brentford. Premier League.
        9:00pm, Sunday 2nd August 2025.
        Anfield.
        """

        fixture_at = parse_future_fixture_datetime_from_html(
            page_html,
            collected_at=datetime(2026, 6, 7, 3, 0, tzinfo=timezone.utc),
        )

        self.assertIsNone(fixture_at)


if __name__ == "__main__":
    unittest.main()
