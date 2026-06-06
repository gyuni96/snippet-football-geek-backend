from pathlib import Path
import unittest


class CaptureXSessionCliTest(unittest.TestCase):
    def test_capture_x_session_entrypoint_exists(self):
        path = Path("app/jobs/capture_x_session.py")

        self.assertTrue(path.exists(), "capture_x_session CLI should exist")
        content = path.read_text(encoding="utf-8")
        self.assertIn("x_storage_state.json", content)
        self.assertIn("storage_state", content)
        self.assertIn("https://x.com/login", content)


if __name__ == "__main__":
    unittest.main()
