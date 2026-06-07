from pathlib import Path
import unittest

from app.team_config import load_liverpool_team_config


class TeamConfigTest(unittest.TestCase):
    def test_loads_liverpool_filter_rules_from_config_file(self):
        config_path = Path("config/liverpool.json")

        config = load_liverpool_team_config(config_path)

        self.assertIn("women", config.official_website_excluded_terms)
        self.assertIn("lfc-women", config.official_website_excluded_terms)
        self.assertIn("rio ngumoha", config.liverpool_subject_terms)
        self.assertIn("lfc women", config.womens_team_terms)


if __name__ == "__main__":
    unittest.main()
