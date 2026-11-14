"""Run the review script up to its diff fetch with a stub gh, offline."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/ai-review.sh'

# gh pr diff's stderr for a pull request past GitHub's diff limits.
TOO_LARGE = ('could not find pull request diff: HTTP 406: Sorry, the diff exceeded '
             'the maximum number of files (300).\nPullRequest.diff too_large\n')


class DiffFetchTests(unittest.TestCase):
    def run_script(self, stderr, exit_code):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gh = root / 'gh'
            gh.write_text(f'#!/bin/sh\nprintf %s "$GH_STDERR" >&2\nexit {exit_code}\n')
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                   'GH_STDERR': stderr, 'PR_NUMBER': '186',
                   'GITHUB_REPOSITORY': 'example/repo',
                   'AI_REVIEW_API_KEY': 'sk-or-test'}
            return subprocess.run(['bash', str(SCRIPT)], env=env,
                                  capture_output=True, text=True)

    def test_too_large_diff_skips_review(self):
        run = self.run_script(TOO_LARGE, 1)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('skipping AI review', run.stdout)

    def test_other_diff_failure_fails(self):
        run = self.run_script('HTTP 404: Not Found\n', 1)
        self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn('HTTP 404', run.stderr)


if __name__ == '__main__':
    unittest.main()
