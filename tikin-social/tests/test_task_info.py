"""Task identity and final delivery survive independent local registration processes."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/tikin-setup/scripts'


class TaskInfoTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tikin-task-info-')
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(('TIKIN_', 'CODEX_', 'CLAUDE_', 'CODEBUDDY_'))}
        self.context = self.project / 'context.json'
        self.context.write_text(json.dumps({'host': 'WorkBuddy', 'conversation_id': 'creator', 'agent_id': 'writer'}))
        script = ('import sys;sys.path.insert(0,sys.argv[1]);'
                  'from tikin_request import create_record;'
                  'from task_info import create,execution_context;'
                  '\nwith execution_context(sys.argv[2]):\n'
                  ' record=create_record(__import__("pathlib").Path("data/tikin-social"),"评论分析");'
                  ' create(record,"评论分析","tikin-comments-analysis","2.0.2");'
                  ' print(record.resolve())')
        result = subprocess.run([sys.executable, '-c', script, str(SCRIPTS), str(self.context)],
                                cwd=self.project, env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.record = Path(result.stdout.strip())
        self.info = self.record.parent / 'task-info.json'

    def register(self, files, *options, cwd=None, ok=True):
        manifest = self.project / 'outputs.json'
        manifest.write_text(json.dumps([str(p) for p in files]))
        result = subprocess.run([sys.executable, str(SCRIPTS / 'tikin-config'), '--no-global-config',
                                 '--skill', 'tikin-comments-analysis', 'artifact-register', '--record', str(self.record),
                                 '--files-file', str(manifest), '--context-file', str(self.context), *options],
                                cwd=cwd or self.project, env=self.environment, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(self.info.read_text())

    def test_creator_and_outputs_survive_cross_session_reregistration(self):
        before = json.loads(self.info.read_text())
        self.assertRegex(self.record.parent.name, r'^\d{14}-评论分析-run-[a-f0-9]{8}$')
        report = self.project / 'analysis.md'
        report.write_text('# Findings\nSynthetic local report.\n')
        self.context.write_text(json.dumps({'host': 'Codex', 'conversation_id': 'continuation', 'agent_id': 'reviewer'}))
        first = self.register([report], '--delivery', 'completed', '--reason', 'Report saved')
        again = self.register([report])
        self.assertEqual(again['task_id'], before['task_id'])
        self.assertEqual(again['creator'], before['creator'])
        self.assertEqual(len(again['participants']), 2)
        self.assertEqual(len(again['registered_outputs']), 1)
        self.assertEqual(first['registered_outputs'][0]['id'], again['registered_outputs'][0]['id'])
        self.assertEqual(again['registered_outputs'][0]['sha256'], hashlib.sha256(report.read_bytes()).hexdigest())
        self.assertEqual(again['delivery']['status'], 'completed')
        self.assertEqual(Path(again['registered_outputs'][0]['path']), report)

    def test_wrong_project_and_supporting_files_cannot_change_delivery(self):
        report = self.project / 'report.csv'
        report.write_text('column\nvalue\n')
        saved = self.register([report], '--delivery', 'completed', '--reason', 'Export verified')
        other = self.project / 'another-project'
        other.mkdir()
        self.assertEqual(self.register([report], cwd=other, ok=False), saved)
        for name in ('run.json', 'error-report.md', 'unfinished.mp4.part'):
            auxiliary = self.record.parent / name
            auxiliary.write_text('supporting')
            self.assertEqual(self.register([auxiliary], ok=False), saved)
        self.assertEqual(self.register([self.project / 'missing.csv'], ok=False), saved)

    def test_unknown_schema_is_preserved(self):
        saved = json.loads(self.info.read_text())
        saved['schema_version'] = 900
        self.info.write_text(json.dumps(saved))
        self.assertEqual(self.register([], ok=False), saved)


if __name__ == '__main__':
    unittest.main()
