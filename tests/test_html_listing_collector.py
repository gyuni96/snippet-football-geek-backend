from datetime import timezone
import unittest

from app.collectors.html_listing import collect_html_listing_items, parse_listing_links


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

        def fetcher(url):
            self.assertEqual(url, "https://example.com/liverpool")
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
        self.assertEqual(items[0].source_type, "html_listing")
        self.assertEqual(items[0].source_name, "Example Liverpool")
        self.assertEqual(items[0].url, "https://example.com/news/liverpool-transfer-update")
        self.assertEqual(items[0].title, "Liverpool transfer update latest")
        self.assertEqual(items[0].text, "본문: https://example.com/news/liverpool-transfer-update")
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
