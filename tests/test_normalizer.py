from datetime import datetime, timezone
import unittest

from app.models import Article, RawItem, SocialPost
from app.normalizer import normalize_raw_item


class NormalizerTest(unittest.TestCase):
    def test_normalizes_rss_raw_item_to_article(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        raw_item = RawItem(
            team_slug="liverpool",
            source_type="rss",
            source_name="Liverpool Echo",
            external_id="article-1",
            url="https://example.com/liverpool-transfer",
            title="Liverpool watch midfield target",
            text="Liverpool are monitoring a midfield target before the window opens.",
            published_at=published_at,
            author="Reporter",
        )

        normalized = normalize_raw_item(raw_item)

        self.assertEqual(
            normalized,
            Article(
                team_slug="liverpool",
                source_name="Liverpool Echo",
                external_id="article-1",
                canonical_url="https://example.com/liverpool-transfer",
                title="Liverpool watch midfield target",
                body="Liverpool are monitoring a midfield target before the window opens.",
                published_at=published_at,
                author="Reporter",
            ),
        )

    def test_normalizes_x_profile_raw_item_to_social_post(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        raw_item = RawItem(
            team_slug="liverpool",
            source_type="x_profile",
            source_name="James Pearce",
            external_id="1900000000000000000",
            url="https://x.com/JamesPearceLFC/status/1900000000000000000",
            title="",
            text="Liverpool have no plans to sell the player this summer.",
            published_at=published_at,
            author="JamesPearceLFC",
        )

        normalized = normalize_raw_item(raw_item)

        self.assertEqual(
            normalized,
            SocialPost(
                team_slug="liverpool",
                platform="x",
                source_name="James Pearce",
                external_post_id="1900000000000000000",
                author_handle="JamesPearceLFC",
                text="Liverpool have no plans to sell the player this summer.",
                url="https://x.com/JamesPearceLFC/status/1900000000000000000",
                published_at=published_at,
            ),
        )


if __name__ == "__main__":
    unittest.main()
