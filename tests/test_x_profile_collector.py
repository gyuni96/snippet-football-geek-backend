from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from app.collectors.x_profiles import (
    XProfileCollectionError,
    XProfilePost,
    build_playwright_post_provider,
    build_snscrape_post_provider,
    collect_x_profile_items,
    parse_x_datetime,
)
from app.sources import get_x_profile


class XProfileCollectorTest(unittest.TestCase):
    def test_collect_x_profile_items_converts_posts_to_raw_items(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)

        items = collect_x_profile_items(
            profile=get_x_profile("james_pearce"),
            team_slug="liverpool",
            post_provider=lambda profile: [
                XProfilePost(
                    post_id="post-1",
                    text="Liverpool are not planning to sell the player this summer.",
                    url="https://x.com/JamesPearceLFC/status/post-1",
                    published_at=published_at,
                )
            ],
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].team_slug, "liverpool")
        self.assertEqual(items[0].source_type, "x_profile")
        self.assertEqual(items[0].source_name, "James Pearce")
        self.assertEqual(items[0].external_id, "post-1")
        self.assertEqual(items[0].author, "JamesPearceLFC")
        self.assertEqual(items[0].url, "https://x.com/JamesPearceLFC/status/post-1")

    def test_snscrape_provider_converts_scraper_tweets_to_posts(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        captured_handles = []

        class FakeScraper:
            def __init__(self, handle):
                captured_handles.append(handle)

            def get_items(self):
                return iter(
                    [
                        SimpleNamespace(
                            id=123,
                            rawContent="Liverpool are monitoring a transfer target.",
                            url="https://x.com/JamesPearceLFC/status/123",
                            date=published_at,
                        ),
                        SimpleNamespace(
                            id=124,
                            content="Liverpool injury update expected today.",
                            url="https://x.com/JamesPearceLFC/status/124",
                            date=published_at,
                        ),
                    ]
                )

        provider = build_snscrape_post_provider(max_posts=1, scraper_factory=FakeScraper)

        posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(captured_handles, ["JamesPearceLFC"])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].post_id, "123")
        self.assertEqual(posts[0].text, "Liverpool are monitoring a transfer target.")
        self.assertEqual(posts[0].url, "https://x.com/JamesPearceLFC/status/123")
        self.assertEqual(posts[0].published_at, published_at)

    def test_snscrape_provider_wraps_scraper_failures(self):
        class FailingScraper:
            def __init__(self, handle):
                pass

            def get_items(self):
                raise RuntimeError("blocked (404)")

        provider = build_snscrape_post_provider(max_posts=1, scraper_factory=FailingScraper)

        with self.assertRaises(XProfileCollectionError) as context:
            provider(get_x_profile("james_pearce"))

        self.assertIn("JamesPearceLFC", str(context.exception))
        self.assertIn("blocked (404)", str(context.exception))

    def test_parse_x_datetime_accepts_z_suffix(self):
        parsed = parse_x_datetime("2026-06-06T09:00:00.000Z")

        self.assertEqual(parsed, datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc))

    def test_playwright_provider_collects_profile_articles(self):
        captured = {}
        published_at = "2026-06-06T09:00:00.000Z"

        class FakeElement:
            def __init__(self, text, attributes=None):
                self.text = text
                self.attributes = attributes or {}

            def text_content(self):
                return self.text

            def get_attribute(self, name):
                return self.attributes.get(name)

        class FakeArticle:
            def query_selector(self, selector):
                if selector == "[data-testid='tweetText']":
                    return FakeElement("Liverpool are monitoring a transfer target.")
                if selector == "time":
                    return FakeElement("", {"datetime": published_at})
                return None

            def get_attribute(self, name):
                if name == "datetime":
                    return published_at
                return None

            def query_selector_all(self, selector):
                if selector == "a[href*='/status/']":
                    return [SimpleNamespace(get_attribute=lambda name: "/JamesPearceLFC/status/123")]
                return []

        class FakePage:
            def goto(self, url, wait_until, timeout):
                captured["url"] = url
                captured["wait_until"] = wait_until
                captured["timeout"] = timeout

            def wait_for_selector(self, selector, timeout):
                captured["selector"] = selector

            def query_selector_all(self, selector):
                return [FakeArticle()]

        class FakeContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

            def new_page(self):
                return FakePage()

        class FakeBrowser:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                pass

            def new_context(self, storage_state):
                captured["storage_state"] = storage_state
                return FakeContext()

        class FakeChromium:
            def launch(self, headless):
                captured["headless"] = headless
                return FakeBrowser()

        class FakePlaywright:
            chromium = FakeChromium()

        provider = build_playwright_post_provider(
            storage_state_path="x_storage_state.json",
            max_posts=1,
            playwright_factory=lambda: FakePlaywright(),
        )

        posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(captured["url"], "https://x.com/JamesPearceLFC")
        self.assertEqual(captured["storage_state"], "x_storage_state.json")
        self.assertTrue(captured["headless"])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].post_id, "123")
        self.assertEqual(posts[0].text, "Liverpool are monitoring a transfer target.")
        self.assertEqual(posts[0].url, "https://x.com/JamesPearceLFC/status/123")
        self.assertEqual(posts[0].published_at, datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
