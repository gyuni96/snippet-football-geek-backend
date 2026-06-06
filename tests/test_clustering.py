from datetime import datetime, timezone
import unittest

from app.clustering import cluster_similar_articles
from app.models import Article


class ArticleClusteringTest(unittest.TestCase):
    def test_clusters_similar_articles_and_combines_sources(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        articles = [
            Article(
                team_slug="liverpool",
                source_name="Liverpool FC Official Website",
                external_id="official-1",
                canonical_url="https://www.liverpoolfc.com/news/iraola-appointed",
                title="Liverpool announce Iraola as head coach",
                body="Liverpool have appointed Andoni Iraola as head coach.",
                published_at=published_at,
            ),
            Article(
                team_slug="liverpool",
                source_name="Sky Sports - Liverpool",
                external_id="sky-1",
                canonical_url="https://www.skysports.com/football/news/iraola-liverpool",
                title="Liverpool appoint Andoni Iraola as new head coach",
                body="Sky Sports reports Liverpool have appointed Iraola.",
                published_at=datetime(2026, 6, 6, 10, 0, tzinfo=timezone.utc),
            ),
        ]

        clustered = cluster_similar_articles(articles)

        self.assertEqual(len(clustered), 1)
        self.assertEqual(clustered[0].source_names, ["Liverpool FC Official Website", "Sky Sports - Liverpool"])
        self.assertEqual(
            clustered[0].source_urls,
            [
                "https://www.liverpoolfc.com/news/iraola-appointed",
                "https://www.skysports.com/football/news/iraola-liverpool",
            ],
        )
        self.assertEqual(clustered[0].source_name, "Sky Sports - Liverpool")
        self.assertIn("관련 보도", clustered[0].body)

    def test_keeps_unrelated_articles_separate(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        articles = [
            Article(
                team_slug="liverpool",
                source_name="BBC Sport - Liverpool",
                external_id="article-1",
                canonical_url="https://www.bbc.com/sport/football/articles/1",
                title="Liverpool next manager latest",
                body="Liverpool manager news.",
                published_at=published_at,
            ),
            Article(
                team_slug="liverpool",
                source_name="This Is Anfield",
                external_id="article-2",
                canonical_url="https://www.thisisanfield.com/news/2",
                title="Rio Ngumoha not for sale amid Bayern interest",
                body="Liverpool do not plan to sell Rio Ngumoha.",
                published_at=published_at,
            ),
        ]

        self.assertEqual(len(cluster_similar_articles(articles)), 2)

    def test_keeps_same_series_articles_with_different_subjects_separate(self):
        published_at = datetime(2026, 6, 6, 9, 0, tzinfo=timezone.utc)
        articles = [
            Article(
                team_slug="liverpool",
                source_name="Liverpool FC Official Website",
                external_id="article-84",
                canonical_url="https://www.liverpoolfc.com/news/liverpools-greatest-no84-gerry-byrne",
                title="Liverpool's Greatest - No.84: Gerry Byrne",
                body="Gerry Byrne profile.",
                published_at=published_at,
            ),
            Article(
                team_slug="liverpool",
                source_name="Liverpool FC Official Website",
                external_id="article-85",
                canonical_url="https://www.liverpoolfc.com/news/liverpools-greatest-no85-phil-taylor",
                title="Liverpool's Greatest - No.85: Phil Taylor",
                body="Phil Taylor profile.",
                published_at=published_at,
            ),
        ]

        self.assertEqual(len(cluster_similar_articles(articles)), 2)


if __name__ == "__main__":
    unittest.main()
