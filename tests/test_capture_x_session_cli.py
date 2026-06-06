from pathlib import Path
from io import StringIO
import unittest
from unittest.mock import patch

from app.jobs import capture_x_session


class CaptureXSessionCliTest(unittest.TestCase):
    def test_capture_x_session_entrypoint_exists(self):
        path = Path("app/jobs/capture_x_session.py")

        self.assertTrue(path.exists(), "capture_x_session CLI should exist")
        content = path.read_text(encoding="utf-8")
        self.assertIn("x_storage_state.json", content)
        self.assertIn("storage_state", content)
        self.assertIn("https://x.com/login", content)

    def test_cli_supports_browser_channel_option(self):
        help_output = StringIO()
        with patch("sys.argv", ["capture_x_session.py", "--help"]), patch("sys.stdout", help_output):
            with self.assertRaises(SystemExit) as exit_context:
                capture_x_session.main()

        self.assertEqual(exit_context.exception.code, 0)
        self.assertIn("--browser-channel", help_output.getvalue())


if __name__ == "__main__":
    unittest.main()
