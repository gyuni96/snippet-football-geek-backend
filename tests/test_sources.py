import unittest

from app.sources import LIVERPOOL_SOURCES, get_source, iter_collectable_sources


class SourcesTest(unittest.TestCase):
    def test_liverpool_sources_include_provided_three_sources(self):
        self.assertEqual(
            sorted(LIVERPOOL_SOURCES.keys()),
            ["bbc_sport", "liverpool_echo", "official_website"],
        )
        self.assertEqual(
            get_source("liverpool_echo").rss_url,
            "https://www.liverpoolecho.co.uk/all-about/liverpool%20fc?service=rss",
        )
        self.assertIsNone(get_source("official_website").rss_url)

    def test_iter_collectable_sources_skips_sources_without_rss_url(self):
        collectable_keys = [source.key for source in iter_collectable_sources(["all"])]

        self.assertEqual(collectable_keys, ["liverpool_echo", "bbc_sport"])


if __name__ == "__main__":
    unittest.main()
