"""Version metadata contracts; independent of business runtime dependencies."""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VersionMetadataTests(unittest.TestCase):
    def test_plugin_skill_and_runtime_versions_are_consistent(self):
        version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
        for directory in (".claude-plugin", ".codex-plugin", ".codebuddy-plugin"):
            manifest = json.loads((ROOT / directory / "plugin.json").read_text())
            self.assertEqual(manifest["version"], version)
            self.assertEqual(manifest["name"], "tikin-social")
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            text = skill.read_text()
            skill_version = re.search(r'^metadata:\s*\n  version: "([^"\s]+)"', text, re.M).group(1)
            self.assertRegex(skill_version, r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$')
            self.assertIn("description: v" + skill_version + "｜", text)
            if (skill.parent / "pyproject.toml").exists():
                project = tomllib.loads((skill.parent / 'pyproject.toml').read_text())['project']
                self.assertEqual(project['version'], skill_version)
                lock = tomllib.loads((skill.parent / 'uv.lock').read_text())
                self.assertEqual(next(p['version'] for p in lock['package'] if p['name'] == project['name']), skill_version)


if __name__ == "__main__":
    unittest.main()
