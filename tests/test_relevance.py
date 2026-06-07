from datetime import datetime, timezone
import unittest

from app.models import Article, SocialPost
from app.relevance import score_liverpool_relevance


class RelevanceTest(unittest.TestCase):
    def test_scores_liverpool_article_as_high_relevance(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool Echo",
            external_id="a1",
            canonical_url="https://example.com/story",
            title="Liverpool monitor transfer target",
            body="The Reds are watching a midfielder before the summer window.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(score_liverpool_relevance(article), "high")

    def test_scores_unrelated_social_post_as_low_relevance(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="Reporter",
            external_post_id="p1",
            author_handle="reporter",
            text="Chelsea are preparing a new contract offer.",
            url="https://x.com/reporter/status/p1",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(score_liverpool_relevance(post), "low")

    def test_scores_lfctransferroom_off_topic_post_as_low_relevance(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="p2",
            author_handle="LFCTransferRoom",
            text="Enrique Riquelme promises to bring Erling Haaland to Real Madrid if elected.",
            url="https://x.com/LFCTransferRoom/status/p2",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(score_liverpool_relevance(post), "low")

    def test_scores_known_liverpool_subject_social_post_as_high_relevance(self):
        post = SocialPost(
            team_slug="liverpool",
            platform="x",
            source_name="LFCTransferRoom",
            external_post_id="p3",
            author_handle="LFCTransferRoom",
            text="Rio Ngumoha has been named England U18 star boy after another strong performance.",
            url="https://x.com/LFCTransferRoom/status/p3",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(score_liverpool_relevance(post), "high")

    def test_scores_womens_team_article_as_low_relevance(self):
        article = Article(
            team_slug="liverpool",
            source_name="Liverpool FC Official Website",
            external_id="a2",
            canonical_url="https://www.liverpoolfc.com/news/fuka-nagano-assists-japan-win",
            title="Fuka Nagano assists Japan win against South Africa",
            body="Liverpool FC Women midfielder Fuka Nagano assisted Japan's latest international win.",
            published_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        )

        self.assertEqual(score_liverpool_relevance(article), "low")


if __name__ == "__main__":
    unittest.main()
