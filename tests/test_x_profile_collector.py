from datetime import datetime, timezone
import unittest

from app.collectors.x_profiles import XProfilePost, collect_x_profile_items
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


if __name__ == "__main__":
    unittest.main()
