import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest

from app.collectors.x_profiles import (
    XProfileCollectionError,
    XProfilePost,
    build_playwright_post_provider,
    build_snscrape_post_provider,
    build_twikit_post_provider,
    collect_x_profile_items,
    parse_x_datetime,
    _patch_twikit_client_transaction_compat,
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

    def test_twikit_provider_collects_profile_tweets_with_login(self):
        captured = {}
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)

        class FakeTwikitClient:
            async def login(self, **kwargs):
                captured["login"] = kwargs

            async def get_user_by_screen_name(self, screen_name):
                captured["screen_name"] = screen_name
                return SimpleNamespace(id="user-1")

            async def get_user_tweets(self, user_id, tweet_type, count):
                captured["user_id"] = user_id
                captured["tweet_type"] = tweet_type
                captured["count"] = count
                return [
                    SimpleNamespace(
                        id="123",
                        text="Liverpool are monitoring a transfer target.",
                        created_at_datetime=published_at,
                    )
                ]

        provider = build_twikit_post_provider(
            username="collector",
            email="collector@example.com",
            password="password",
            cookies_file="missing_x_cookies.json",
            max_posts=1,
            client_factory=FakeTwikitClient,
        )

        posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(captured["login"]["auth_info_1"], "collector")
        self.assertEqual(captured["login"]["auth_info_2"], "collector@example.com")
        self.assertEqual(captured["login"]["password"], "password")
        self.assertEqual(captured["login"]["cookies_file"], "missing_x_cookies.json")
        self.assertEqual(captured["screen_name"], "JamesPearceLFC")
        self.assertEqual(captured["user_id"], "user-1")
        self.assertEqual(captured["tweet_type"], "Tweets")
        self.assertEqual(captured["count"], 1)
        self.assertEqual(posts[0].post_id, "123")
        self.assertEqual(posts[0].text, "Liverpool are monitoring a transfer target.")
        self.assertEqual(posts[0].url, "https://x.com/JamesPearceLFC/status/123")
        self.assertEqual(posts[0].published_at, published_at)

    def test_twikit_provider_supports_legacy_login_signature(self):
        captured = {}
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)

        class FakeLegacyTwikitClient:
            async def login(self, *, auth_info_1, auth_info_2=None, password):
                captured["login"] = {
                    "auth_info_1": auth_info_1,
                    "auth_info_2": auth_info_2,
                    "password": password,
                }

            def save_cookies(self, path):
                captured["cookies_file"] = path

            async def get_user_by_screen_name(self, screen_name):
                return SimpleNamespace(id="user-1")

            async def get_user_tweets(self, user_id, tweet_type, count):
                return [
                    SimpleNamespace(
                        id="123",
                        text="Liverpool are monitoring a transfer target.",
                        created_at_datetime=published_at,
                    )
                ]

        provider = build_twikit_post_provider(
            username="collector",
            email="collector@example.com",
            password="password",
            cookies_file="missing_x_cookies.json",
            max_posts=1,
            client_factory=FakeLegacyTwikitClient,
        )

        posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(captured["login"]["auth_info_1"], "collector")
        self.assertEqual(captured["login"]["auth_info_2"], "collector@example.com")
        self.assertEqual(captured["login"]["password"], "password")
        self.assertEqual(captured["cookies_file"], "missing_x_cookies.json")
        self.assertEqual(posts[0].post_id, "123")

    def test_twikit_provider_can_bootstrap_cookie_file_from_tokens(self):
        captured = {}
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)

        class FakeCookieTwikitClient:
            def load_cookies(self, path):
                captured["loaded_cookies"] = json.loads(Path(path).read_text(encoding="utf-8"))

            async def login(self, **kwargs):
                raise AssertionError("login should not run when cookie tokens are provided")

            async def get_user_by_screen_name(self, screen_name):
                return SimpleNamespace(id="user-1")

            async def get_user_tweets(self, user_id, tweet_type, count):
                return [
                    SimpleNamespace(
                        id="123",
                        text="Liverpool are monitoring a transfer target.",
                        created_at_datetime=published_at,
                    )
                ]

        with TemporaryDirectory() as temp_dir:
            cookies_file = str(Path(temp_dir) / "x_cookies.json")
            provider = build_twikit_post_provider(
                auth_token="auth-token",
                ct0="csrf-token",
                cookies_file=cookies_file,
                max_posts=1,
                client_factory=FakeCookieTwikitClient,
            )

            posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(captured["loaded_cookies"]["auth_token"], "auth-token")
        self.assertEqual(captured["loaded_cookies"]["ct0"], "csrf-token")
        self.assertEqual(posts[0].post_id, "123")

    def test_twikit_provider_supports_sync_client_methods(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)

        class FakeSyncTwikitClient:
            def load_cookies(self, path):
                pass

            def get_user_by_screen_name(self, screen_name):
                return SimpleNamespace(id="user-1")

            def get_user_tweets(self, user_id, tweet_type, count):
                return [
                    SimpleNamespace(
                        id="123",
                        text="Liverpool are monitoring a transfer target.",
                        created_at_datetime=published_at,
                    )
                ]

        with TemporaryDirectory() as temp_dir:
            cookies_file = Path(temp_dir) / "x_cookies.json"
            cookies_file.write_text(json.dumps({"auth_token": "auth-token", "ct0": "csrf-token"}), encoding="utf-8")
            provider = build_twikit_post_provider(
                cookies_file=str(cookies_file),
                max_posts=1,
                client_factory=FakeSyncTwikitClient,
            )

            posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(posts[0].post_id, "123")

    def test_twikit_legacy_patch_adds_missing_user_url_fields(self):
        from app.collectors.x_profiles import _patch_twikit_legacy_defaults

        _patch_twikit_legacy_defaults()

        import twikit.user

        user = twikit.user.User(
            client=SimpleNamespace(),
            data={
                "rest_id": "user-1",
                "is_blue_verified": False,
                "legacy": {
                    "created_at": "Sat Jun 06 09:00:00 +0000 2026",
                    "name": "LFCTransferRoom",
                    "screen_name": "LFCTransferRoom",
                    "profile_image_url_https": "https://example.com/avatar.jpg",
                    "location": "",
                    "description": "Liverpool transfer news",
                    "entities": {},
                    "verified": False,
                    "followers_count": 1,
                    "friends_count": 1,
                    "favourites_count": 1,
                    "listed_count": 0,
                    "statuses_count": 1,
                },
            },
        )

        self.assertEqual(user.description_urls, [])
        self.assertEqual(user.urls, [])

    def test_twikit_transaction_patch_bypasses_key_byte_lookup(self):
        try:
            import twikit.x_client_transaction.transaction
        except ModuleNotFoundError:
            self.skipTest("twikit is not installed")

        _patch_twikit_client_transaction_compat()

        transaction = twikit.x_client_transaction.transaction.ClientTransaction()
        asyncio.run(transaction.init(session=SimpleNamespace(), headers={}))

        transaction_id = transaction.generate_transaction_id(method="GET", path="/i/api/graphql")

        self.assertTrue(transaction.home_page_response)
        self.assertIsInstance(transaction_id, str)
        self.assertGreater(len(transaction_id), 20)

    def test_twikit_provider_reads_created_at_from_raw_tweet_data(self):
        class FakeTwikitClient:
            def load_cookies(self, path):
                pass

            def get_user_by_screen_name(self, screen_name):
                return SimpleNamespace(id="user-1")

            def get_user_tweets(self, user_id, tweet_type, count):
                return [
                    SimpleNamespace(
                        id="123",
                        text="Liverpool are monitoring a transfer target.",
                        _data={
                            "legacy": {
                                "created_at": "Sat Jun 06 09:00:00 +0000 2026",
                            }
                        },
                    )
                ]

        with TemporaryDirectory() as temp_dir:
            cookies_file = Path(temp_dir) / "x_cookies.json"
            cookies_file.write_text(json.dumps({"auth_token": "auth-token", "ct0": "csrf-token"}), encoding="utf-8")
            provider = build_twikit_post_provider(
                cookies_file=str(cookies_file),
                max_posts=1,
                client_factory=FakeTwikitClient,
            )

            posts = provider(get_x_profile("james_pearce"))

        self.assertEqual(posts[0].published_at, datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
