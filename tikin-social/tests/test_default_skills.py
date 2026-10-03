import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_tikin_config import _resolve_interpreter, SCRIPT, SKILL_DIR, ROOT


class DefaultSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python, reason = _resolve_interpreter()
        if not cls.python:
            raise RuntimeError(reason)

    def setUp(self):
        scratch = Path(os.environ.get("TMPDIR") or ROOT.parent / "tmp/default-skills")
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="tikin-defaults-", dir=scratch)
        self.root = Path(self.temporary.name)
        self.env = dict(os.environ, HOME=str(self.root), USERPROFILE=str(self.root), CODEX_HOME="", CLAUDE_CONFIG_DIR="", WORKBUDDY_CONFIG_DIR="", CODEBUDDY_CONFIG_DIR="", TIKIN_API_KEY="")
        self.settings = self.root / ".config/tikin-social/settings.json"

    def tearDown(self):
        self.temporary.cleanup()

    def call(self, agent="workbuddy", action="check", extra=(), global_flags=(), script=SCRIPT):
        process = subprocess.run([self.python, str(script), *global_flags, "default-skills", "--agent", agent, "--action", action, *extra], cwd=self.root, env=self.env, text=True, capture_output=True, timeout=15)
        return process

    def ok(self, **kwargs):
        process = self.call(**kwargs)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_offline_check_all_hosts_without_writes(self):
        for agent in ("codex", "claude-code", "workbuddy"):
            result = self.ok(agent=agent)
            self.assertEqual(result["status"], "review_required")
            self.assertEqual(result["session_loaded"], "not_verified")
            self.assertIn("tikin-douyin", result["proposed_rule"])
        self.assertFalse(self.settings.exists())

    def test_persistence_isolation_preservation_and_restore(self):
        self.settings.parent.mkdir(parents=True)
        routing = {"default": "confirm", "platforms": {"douyin": "auto"}}
        self.settings.write_text(json.dumps({"routing": routing, "other": 42}))
        self.assertEqual(self.ok(action="dismiss")["status"], "dismissed")
        self.assertEqual(self.ok()["status"], "dismissed")
        self.assertEqual(self.ok(agent="codex")["status"], "review_required")
        self.assertEqual(self.ok(extra=("--config-dir", str(self.root / "second-profile")))["status"], "review_required")
        self.ok(action="enable")
        self.ok(action="enable")
        value = json.loads(self.settings.read_text())
        self.assertEqual(value["routing"], routing)
        self.assertEqual(value["other"], 42)
        self.assertEqual(len(value["default_skill_reminders"]["agents"]), 1)
        self.assertFalse((self.root / ".workbuddy/CODEBUDDY.md").exists())
        self.assertFalse((self.root / ".config/aihub-studio").exists())

    def test_override_and_shared_symlinks_remain_intact(self):
        directory = self.root / ".codex"
        directory.mkdir()
        rule = self.root / "shared.md"
        rule.write_text("existing instructions")
        (directory / "AGENTS.md").symlink_to(rule)
        override = directory / "AGENTS.override.md"
        override.write_text(" ")
        self.assertEqual(self.ok(agent="codex")["primary_real_path"], str(rule))
        override.write_text("override")
        self.assertEqual(self.ok(agent="codex")["primary_rule"], str(override))
        alias = self.root / "alias"
        alias.symlink_to(directory)
        self.ok(agent="codex", action="dismiss", extra=("--config-dir", str(alias)))
        self.assertEqual(self.ok(agent="codex")["status"], "dismissed")
        self.assertEqual(rule.read_text(), "existing instructions")

    def test_skip_corruption_unknown_version_and_active_writer(self):
        self.settings.parent.mkdir(parents=True)
        for contents in ("broken", '{"default_skill_reminders":{"version":2,"agents":[]}}'):
            self.settings.write_text(contents)
            self.assertEqual(self.ok(global_flags=("--no-global-config",))["status"], "skipped")
            self.assertNotEqual(self.call(action="dismiss", global_flags=("--no-global-config",)).returncode, 0)
            self.assertNotEqual(self.call(action="dismiss").returncode, 0)
            self.assertEqual(self.settings.read_text(), contents)
        self.settings.write_text("{}")
        Path(str(self.settings) + ".default-skills.lock").write_text("")
        self.assertNotEqual(self.call(action="dismiss").returncode, 0)
        self.assertEqual(self.settings.read_text(), "{}")

    def test_reminder_initialization_keeps_routing_valid(self):
        self.ok(action="dismiss")
        process = subprocess.run([self.python, str(SCRIPT), "get-policy", "douyin"], cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(process.stdout.strip(), "auto")

    def test_dangling_settings_symlink_is_preserved(self):
        self.settings.parent.mkdir(parents=True)
        target = self.root / "preferences/tikin.json"
        self.settings.symlink_to(target)
        self.ok(action="dismiss")
        self.assertTrue(self.settings.is_symlink())
        self.assertFalse(json.loads(target.read_text())["default_skill_reminders"]["agents"][0]["enabled"])

    def test_routing_writer_uses_same_lock_and_preserves_reminders(self):
        self.ok(action="dismiss")
        before = self.settings.read_bytes()
        lock = Path(str(self.settings) + ".default-skills.lock")
        lock.write_text("")
        command = [self.python, str(SCRIPT), "set-routing", "--default", "confirm"]
        process = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, timeout=15)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(self.settings.read_bytes(), before)
        lock.unlink()
        process = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, timeout=15)
        self.assertEqual(process.returncode, 0, process.stderr)
        settings = json.loads(self.settings.read_text())
        self.assertEqual(settings["routing"]["default"], "confirm")
        self.assertFalse(settings["default_skill_reminders"]["agents"][0]["enabled"])

    def test_ambiguous_workbuddy_config_is_not_guessed(self):
        self.env["WORKBUDDY_CONFIG_DIR"] = str(self.root / "first")
        self.env["CODEBUDDY_CONFIG_DIR"] = str(self.root / "second")
        self.assertNotEqual(self.call(action="dismiss").returncode, 0)
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.ok(extra=("--config-dir", str(self.root / "first")))["config_dir"], str(self.root / "first"))

    def test_relocated_skill_and_all_workflow_links(self):
        destination = self.root / "installed-tikin-setup"
        shutil.copytree(SKILL_DIR, destination, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
        self.env["UV_PROJECT_ENVIRONMENT"] = str(SKILL_DIR / ".venv")
        result = self.ok(script=destination / "scripts/tikin-config")
        self.assertIn("tikin-endpoint-discovery", result["proposed_rule"])
        for entry in (ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn("默认 Skill 检查与提醒", entry.read_text())


if __name__ == "__main__":
    unittest.main()
