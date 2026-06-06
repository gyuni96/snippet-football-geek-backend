from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.env import load_env_file


class EnvTest(unittest.TestCase):
    def test_load_env_file_reads_key_value_pairs_without_overwriting_existing_values(self):
        with TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "GROQ_API_KEY=from-file\n"
                "GROQ_MODEL=llama-test\n"
                "COMMENTED=value # keep inline text simple\n",
                encoding="utf-8",
            )
            environ = {"GROQ_API_KEY": "existing"}

            load_env_file(env_file, environ=environ)

        self.assertEqual(environ["GROQ_API_KEY"], "existing")
        self.assertEqual(environ["GROQ_MODEL"], "llama-test")
        self.assertEqual(environ["COMMENTED"], "value # keep inline text simple")
