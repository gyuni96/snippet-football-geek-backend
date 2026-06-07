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
    def test_liverpool_sources_include_configured_sources(self):
        self.assertEqual(
            sorted(LIVERPOOL_SOURCES.keys()),
            [
                "bbc_sport_liverpool",
                "liverpool_echo",
                "official_website",
                "sky_sports_liverpool",
                "this_is_anfield",
            ],
        )
        self.assertEqual(
            get_source("liverpool_echo").rss_url,
            "https://www.liverpoolecho.co.uk/all-about/liverpool%20fc?service=rss",
        )
        self.assertEqual(
            get_source("this_is_anfield").rss_url,
            "https://www.thisisanfield.com/feed/",
        )
        self.assertEqual(
            get_source("official_website").listing_url,
            "https://www.liverpoolfc.com/news",
        )
        self.assertIn("greatest", get_source("official_website").listing_excluded_terms)
        self.assertIn("competition", get_source("official_website").listing_excluded_terms)
        self.assertIn("women", get_source("official_website").listing_excluded_terms)
        self.assertIn("lfc-women", get_source("official_website").listing_excluded_terms)
        self.assertEqual(
            get_source("sky_sports_liverpool").listing_url,
            "https://www.skysports.com/liverpool",
        )
        self.assertEqual(
            get_source("bbc_sport_liverpool").listing_url,
            "https://www.bbc.com/sport/football/teams/liverpool",
        )
        self.assertIsNone(get_source("official_website").rss_url)

    def test_iter_collectable_sources_includes_rss_and_listing_sources(self):
        collectable_keys = [source.key for source in iter_collectable_sources(["all"])]

        self.assertEqual(
            collectable_keys,
            [
                "official_website",
                "liverpool_echo",
                "this_is_anfield",
                "sky_sports_liverpool",
                "bbc_sport_liverpool",
            ],
        )

    def test_liverpool_x_profiles_include_reporter_sources(self):
        self.assertIn("paul_joyce", LIVERPOOL_X_PROFILES)
        self.assertIn("david_ornstein", LIVERPOOL_X_PROFILES)
        self.assertIn("james_pearce", LIVERPOOL_X_PROFILES)
        self.assertIn("fabrizio_romano", LIVERPOOL_X_PROFILES)
        self.assertIn("i_an_doyle", LIVERPOOL_X_PROFILES)
        self.assertIn("lfc_transfer_room", LIVERPOOL_X_PROFILES)
        self.assertEqual(get_x_profile("paul_joyce").handle, "_pauljoyce")
        self.assertEqual(get_x_profile("david_ornstein").handle, "David_Ornstein")
        self.assertEqual(get_x_profile("james_pearce").handle, "JamesPearceLFC")
        self.assertEqual(get_x_profile("fabrizio_romano").handle, "FabrizioRomano")
        self.assertEqual(get_x_profile("i_an_doyle").handle, "IanDoyleSport")
        self.assertEqual(get_x_profile("lfc_transfer_room").handle, "LFCTransferRoom")

    def test_iter_collectable_x_profiles_supports_group_key(self):
        profile_keys = [profile.key for profile in iter_collectable_x_profiles(["x_reporters"])]

        self.assertIn("paul_joyce", profile_keys)
        self.assertIn("david_ornstein", profile_keys)
        self.assertIn("james_pearce", profile_keys)
        self.assertIn("fabrizio_romano", profile_keys)
        self.assertIn("i_an_doyle", profile_keys)
        self.assertIn("lfc_transfer_room", profile_keys)


if __name__ == "__main__":
    unittest.main()
