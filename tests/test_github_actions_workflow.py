from pathlib import Path
import unittest


class GithubActionsWorkflowTest(unittest.TestCase):
    def test_briefing_workflow_runs_cli_with_schedule_and_manual_inputs(self):
        workflow = Path(".github/workflows/briefing.yml")

        self.assertTrue(workflow.exists(), "briefing workflow should exist")
        content = workflow.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", content)
        self.assertIn("schedule:", content)
        self.assertIn("30 22 * * *", content)
        self.assertIn("30 9 * * *", content)
        self.assertIn("python3 -m app.jobs.run_briefing", content)
        self.assertIn("--source", content)
        self.assertIn("--limit", content)
        self.assertIn("--use-groq", content)
        self.assertIn("GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}", content)
        self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", content)


if __name__ == "__main__":
    unittest.main()
