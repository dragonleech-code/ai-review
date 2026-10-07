"""Exercise the workflow's actual eligibility shell with fixture GitHub responses."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/ai-review.yml'


def eligibility_script():
    step = WORKFLOW.read_text().split('      - name: Check review eligibility\n', 1)[1]
    body = step.split('        run: |\n', 1)[1].split('\n      # Dispatch', 1)[0]
    return '\n'.join(line[10:] for line in body.splitlines())


class EligibilityTests(unittest.TestCase):
    def check_case(self, expected, *, owner='Organization', association='MEMBER',
                   head='example/repo', draft=False, actor='member', event='pull_request',
                   failure=''):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            gh = root / 'gh'
            gh.write_text('''#!/usr/bin/env python3
import json, os, sys
path = sys.argv[2]
if os.environ['FAILURE'] in ('repository', 'pull') and (
    ('/pulls/' in path) == (os.environ['FAILURE'] == 'pull')
):
    sys.exit(1)
if '/pulls/' in path:
    print(os.environ['PR_FIXTURE'])
else:
    print(os.environ['OWNER_FIXTURE'])
''')
            gh.chmod(0o755)
            output = root / 'output'
            output.touch()
            env = {**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                   'GITHUB_REPOSITORY': 'example/repo', 'GITHUB_OUTPUT': str(output),
                   'PR_NUMBER': '29', 'EVENT_NAME': event, 'ACTOR': actor,
                   'FAILURE': failure, 'OWNER_FIXTURE': owner,
                   'PR_FIXTURE': json.dumps({'author_association': association,
                                            'head': {'repo': {'full_name': head}},
                                            'draft': draft})}
            run = subprocess.run(['bash', '-c', eligibility_script()], env=env,
                                 capture_output=True, text=True)
            if expected == 'error':
                self.assertNotEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertNotIn('eligible=true', output.read_text())
            else:
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(output.read_text().strip(), f'eligible={expected}')
                if expected == 'false':
                    self.assertIn('::notice::AI review skipped:', run.stdout)

    def test_member(self):
        self.check_case('true')

    def test_owner(self):
        self.check_case('true', association='OWNER')

    def test_outside_collaborator(self):
        self.check_case('false', association='COLLABORATOR')

    def test_fork(self):
        self.check_case('false', head='outsider/repo')

    def test_deleted_fork(self):
        self.check_case('false', head=None)

    def test_draft(self):
        self.check_case('false', draft=True)

    def test_dependabot(self):
        self.check_case('false', actor='dependabot[bot]')

    def test_personal_repository(self):
        self.check_case('error', owner='User')

    def test_repository_api_failure(self):
        self.check_case('error', failure='repository')

    def test_pr_api_failure(self):
        self.check_case('error', failure='pull')

    def test_manual_defers_to_membership_check(self):
        self.check_case('true', event='workflow_dispatch', failure='pull')


if __name__ == '__main__':
    unittest.main()
