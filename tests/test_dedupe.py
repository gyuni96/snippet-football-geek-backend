from datetime import datetime, timezone
import unittest

from app.dedupe import dedupe_articles, dedupe_social_posts
from app.models import Article, SocialPost


class DedupeTest(unittest.TestCase):
    def test_dedupes_articles_by_canonical_url(self):
        published_at = datetime(2026, 6, 6, 8, 0, tzinfo=timezone.utc)
        first = Article(
            team_slug="liverpool",
            source_name="Source A",
            external_id="a1",
            canonical_url="https://example.com/story",
            title="Liverpool story",
            body="First body",
            published_at=published_at,
        )
        duplicate = Article(
            team_slug="liverpool",
            source_name="Source B",
            external_id="b1",
            canonical_url="https://example.com/story",
            title="Liverpool story copied",
            body="Second body",
            published_at=published_at,
        )

        self.assertEqual(dedupe_articles([first, duplicate]), [first])

    def test_dedupes_social_posts_by_external_post_id(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        first = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="Reporter",
            external_post_id="post-1",
            author_handle="reporter",
            text="Liverpool update.",
            url="https://x.com/reporter/status/post-1",
            published_at=published_at,
        )
        duplicate = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="Reporter",
            external_post_id="post-1",
            author_handle="reporter",
            text="Liverpool update.",
            url="https://x.com/reporter/status/post-1",
            published_at=published_at,
        )

        self.assertEqual(dedupe_social_posts([first, duplicate]), [first])


if __name__ == "__main__":
    unittest.main()
