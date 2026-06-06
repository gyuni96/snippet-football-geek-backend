from pathlib import Path
import unittest


class GithubActionsWorkflowTest(unittest.TestCase):
    def test_briefing_workflow_runs_cli_with_schedule_and_manual_inputs(self):
        workflow = Path(".github/workflows/briefing.yml")

        self.assertTrue(workflow.exists(), "briefing workflow should exist")
        content = workflow.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", content)
        self.assertIn("schedule:", content)
        self.assertIn("0 20 * * *", content)
        self.assertIn("0 7 * * *", content)
        self.assertIn("0 13 * * *", content)
        self.assertIn("BRIEFING_TYPE=\"afternoon\"", content)
        self.assertIn("BRIEFING_TYPE=\"evening\"", content)
        self.assertIn("python3 -m app.jobs.run_briefing", content)
        self.assertIn("--source", content)
        self.assertIn("--limit", content)
        self.assertIn("--use-groq", content)
        self.assertIn("GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}", content)
        self.assertIn("SUPABASE_URL: ${{ secrets.SUPABASE_URL }}", content)
        self.assertIn("SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}", content)
        self.assertIn("--save-supabase", content)
        self.assertIn("X_AUTH_TOKEN: ${{ secrets.X_AUTH_TOKEN }}", content)
        self.assertIn("X_CT0: ${{ secrets.X_CT0 }}", content)
        self.assertIn("X_COOKIES_FILE: ${{ secrets.X_COOKIES_FILE }}", content)
        self.assertIn("DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}", content)
        self.assertIn("python3 -m pip install \".[x-twikit]\"", content)
        self.assertLess(
            content.index("python3 -m pip install \".[x-twikit]\""),
            content.index("python3 -m unittest discover -s tests -v"),
        )
        self.assertIn("default: all", content)
        self.assertIn("default: \"5\"", content)
        self.assertIn("--x-provider", content)
        self.assertIn("twikit", content)
        self.assertIn("--save-monitoring", content)
        self.assertIn("--notify-discord", content)


if __name__ == "__main__":
    unittest.main()
