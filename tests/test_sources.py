import unittest

from app.sources import (
    LIVERPOOL_SOURCES,
    LIVERPOOL_X_PROFILES,
    get_source,
    get_x_profile,
    iter_collectable_sources,
    iter_collectable_x_profiles,
)


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

    def test_liverpool_x_profiles_include_reporter_sources(self):
        self.assertIn("james_pearce", LIVERPOOL_X_PROFILES)
        self.assertEqual(get_x_profile("james_pearce").handle, "JamesPearceLFC")

    def test_iter_collectable_x_profiles_supports_group_key(self):
        profile_keys = [profile.key for profile in iter_collectable_x_profiles(["x_reporters"])]

        self.assertIn("james_pearce", profile_keys)


if __name__ == "__main__":
    unittest.main()
