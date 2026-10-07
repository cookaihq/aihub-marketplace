"""Version metadata contracts; independent of business runtime dependencies."""
import json
import re
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
            self.assertEqual(re.search(r'^metadata:\s*\n  version: "([^"\s]+)"', text, re.M).group(1), version)
            self.assertIn("v" + version + "｜", text)
            if (skill.parent / "pyproject.toml").exists():
                for filename in ("pyproject.toml", "uv.lock"):
                    self.assertIn('version = "' + version + '"', (skill.parent / filename).read_text())


if __name__ == "__main__":
    unittest.main()
