from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.state import load_last_success_at, save_last_success_at


class StateTest(unittest.TestCase):
    def test_load_last_success_at_returns_none_when_file_is_missing(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "missing.json"

            self.assertIsNone(load_last_success_at(state_file))

    def test_save_and_load_last_success_at_round_trips_datetime(self):
        with TemporaryDirectory() as temp_dir:
            state_file = Path(temp_dir) / "state.json"
            value = datetime(2026, 6, 6, 9, 30, tzinfo=timezone.utc)

            save_last_success_at(state_file, value)

            self.assertEqual(load_last_success_at(state_file), value)


if __name__ == "__main__":
    unittest.main()
