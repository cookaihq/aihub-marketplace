"""Synthetic local workflows; host arguments are not native-client acceptance."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_setup import MARKET, PLUGIN, SCRIPT, SKILL
from setup_core import default_settings as defaults
from setup_core.errors import SetupError
from setup_core.progress import Tasks


class DefaultSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Setup defaults 中文 ", dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.user = self.root / "用户"
        self.cwd = self.root / "业务"
        self.user.mkdir()
        self.cwd.mkdir()
        self.rule = self.user / "AGENTS.md"
        self.project_rule = self.cwd / "AGENTS.md"
        self.rule.write_text("# Existing user instructions\n", encoding="utf-8")
        self.project_rule.write_text("Project instructions\n", encoding="utf-8")
        self.state = {"id": "a" * 32, "schema": "setup-aihub.task/v1", "phase": "completed", "operation": "configure",
                      "source": "manual", "result": {"default_settings": {"schema_version": 1, "phase": "pending_check"}},
                      "context": {"host": "codex", "cwd": str(self.cwd), "home": str(self.user), "platform": os.name,
                                  "plugin": "aihub-studio", "global_enabled": True}}
        self.report = {"targets": [self.row(item) for item in defaults.catalog("codex")["targets"]]}

    def row(self, item):
        return {"id": item["id"], "installation": "installed", "evidence": "synthetic host inventory; source cookaihq/aihub-marketplace",
                "root": str(MARKET / item["name"]), "status": "missing", "reason": "synthetic reviewed rules have no defaults",
                "config_dir": str(self.user), "global_rule_file": str(self.rule),
                "rule_files": [str(self.rule), str(self.project_rule)], "session_loaded": "not_verified",
                "reminder_enabled": True, "already_prompted": False}

    def environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AIHUB_", "TIKIN_", "SETUP_AIHUB_", "UV_PROJECT_ENVIRONMENT"))}
        return {**env, "HOME": str(self.user), "USERPROFILE": str(self.user), "PYTHONUTF8": "1",
                "UV_PYTHON": sys.executable, "UV_PYTHON_DOWNLOADS": "never"}

    def call(self, *args, host="codex", ok=True):
        run = subprocess.run([sys.executable, str(SCRIPT), *map(str, args), "--host", host, "--cwd", str(self.cwd)],
                             env=self.environment(), capture_output=True, text=True, encoding="utf-8", timeout=45)
        data = json.loads(run.stdout)
        self.assertEqual(run.returncode == 0, ok, data)
        return data.get("result", data)

    def test_catalog_all_host_labels_read_only_and_packaged_references(self):
        for host, label in defaults.AGENT_NAMES.items():
            result = self.call("defaults", "--action", "catalog", host=host)
            self.assertEqual(result["agent_name"], label)
            self.assertEqual(len(result["targets"]), 2)
            for item in result["targets"]:
                self.assertIn(label, item["default_message"])
                self.assertNotIn("{agent}", item["default_message"])
                defaults.artifacts(item, MARKET / item["name"])
        self.assertFalse((self.user / ".config").exists())

    def test_relocated_complete_plugin_loads_its_own_catalog(self):
        target = self.root / "完整套件"
        shutil.copytree(PLUGIN, target, ignore=shutil.ignore_patterns(".venv", "__pycache__", "tests"))
        file = target / "references/default-settings-targets.json"
        data = json.loads(file.read_text())
        data["targets"] = []
        file.write_text(json.dumps(data))
        command = ["uv", "run", "--locked", "--no-dev", "--project", str(target / "skills/setup-api-key"), "python",
                   str(target / "skills/setup-api-key/scripts/setup_api_key.py"), "defaults", "--action", "catalog",
                   "--host", "workbuddy", "--cwd", str(self.cwd)]
        result = subprocess.run(command, env=self.environment(), capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["result"]["targets"], [])

    def test_entire_catalog_required_not_just_configured_plugin(self):
        for change in (lambda r: r["targets"].pop(), lambda r: r["targets"].append(copy.deepcopy(r["targets"][0]))):
            report = copy.deepcopy(self.report)
            change(report)
            with self.assertRaises(SetupError):
                defaults.record(self.state, report)
        result = defaults.record(self.state, self.report)
        self.assertEqual(result["eligible"], ["plugin:aihub-studio", "plugin:tikin-social"])
        self.assertEqual(self.state["phase"], "completed")

    def test_filter_existing_uninstalled_unknown_conflict_dismissed_and_prompted(self):
        cases = [({"status": "configured_global"}, False), ({"status": "configured_project"}, False),
                 ({"status": "conflict"}, False), ({"status": "unknown"}, False),
                 ({"installation": "not_installed", "status": "skipped"}, False),
                 ({"installation": "unknown", "status": "unknown"}, False),
                 ({"installation": "source_conflict", "status": "unknown"}, False),
                 ({"reminder_enabled": False}, False), ({"already_prompted": True}, False),
                 ({"installation": "disabled"}, True), ({"installation": "unloaded"}, True)]
        for fields, eligible in cases:
            report = copy.deepcopy(self.report)
            report["targets"][0].update(fields)
            result = defaults.record(self.state, report)
            self.assertEqual("plugin:aihub-studio" in result["eligible"], eligible, fields)
            self.assertEqual(len(result["targets"]), 2)
        report["targets"][0].update(installation="not_installed", status="missing")
        with self.assertRaises(SetupError):
            defaults.record(self.state, report)

    def test_independent_skill_and_catalog_invalidity(self):
        data = json.loads(defaults.CATALOG.read_text())
        skill = copy.deepcopy(data["targets"][0])
        skill.update(kind="skill", name="example-skill", setup_guide="guide.md", rule_template="rule.md")
        data["targets"] = [skill]
        catalog_file = self.root / "catalog.json"
        root = self.root / "skill"
        root.mkdir()
        (root / "guide.md").write_text("Synthetic independent Skill guide")
        (root / "rule.md").write_text("Synthetic independent Skill rule")
        catalog_file.write_text(json.dumps(data))
        with patch.object(defaults, "CATALOG", catalog_file):
            item, = defaults.catalog("codex")["targets"]
            row = self.row(item)
            row["root"] = str(root)
            self.assertEqual(defaults.record(self.state, {"targets": [row]})["eligible"], ["skill:example-skill"])
            for bad in ("../escape.md", "/absolute.md", "C:/absolute.md"):
                data["targets"][0]["setup_guide"] = bad
                catalog_file.write_text(json.dumps(data))
                with self.assertRaises(SetupError):
                    defaults.catalog("codex")

    def test_read_only_catalog_and_disabled_globals_do_not_read_rule_files(self):
        self.state["context"]["global_enabled"] = False
        with patch.object(defaults, "revision", side_effect=AssertionError("must not read rules")):
            with self.assertRaisesRegex(SetupError, "default_settings_global_disabled"):
                defaults.record(self.state, self.report)
        self.assertFalse((self.user / ".config").exists())

    def test_duplicate_unknown_schema_and_changed_catalog_are_rejected(self):
        path = self.root / "catalog.json"
        original = json.loads(defaults.CATALOG.read_text())
        path.write_text(json.dumps(original))
        with patch.object(defaults, "CATALOG", path):
            defaults.record(self.state, self.report)
            defaults.choose(self.state, "1")
            plan = defaults.preview(self.state, {"shared_with": []})["preview"]
            changed = copy.deepcopy(original)
            changed["targets"][0]["default_message"] += "Changed"
            path.write_text(json.dumps(changed))
            with self.assertRaises(SetupError):
                defaults.verify(self.state, plan["confirmation"])
            for data in ('{"schema_version":1,"schema_version":2,"targets":[]}',
                         '{"schema_version":2,"targets":[]}',
                         json.dumps({"schema_version":1,"targets":[original["targets"][0]] * 2})):
                path.write_text(data)
                with self.assertRaises(SetupError):
                    defaults.catalog("codex")

    def test_unknown_saved_schema_is_preserved_without_consuming_choice(self):
        defaults.record(self.state, self.report)
        self.state["result"]["default_settings"]["schema_version"] = 2
        before = copy.deepcopy(self.state)
        for action in (lambda: defaults.choose(self.state, "2"), lambda: defaults.record(self.state, self.report),
                       lambda: defaults.pending(self.state)):
            with self.assertRaisesRegex(SetupError, "unsupported_default_settings_schema"):
                action()
            self.assertEqual(self.state, before)

    def test_dismiss_partial_failure_closes_only_the_selected_workflow(self):
        defaults.record(self.state, self.report)
        defaults.choose(self.state, "3")
        outcomes = {"outcomes": [
            {"id":"plugin:aihub-studio", "status":"dismissed", "session_loaded":"not_verified", "evidence":"synthetic native reminder readback false"},
            {"id":"plugin:tikin-social", "status":"failed", "session_loaded":"not_verified", "evidence":"synthetic native preference permission failure"}]}
        with self.assertRaises(SetupError):
            defaults.finish(self.state, {"outcomes": outcomes["outcomes"][:1]})
        result = defaults.finish(self.state, outcomes)
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(self.state["phase"], "completed")
        self.assertEqual(result["outcomes"][1]["status"], "failed")
        self.assertEqual(result["eligible"], [])
        self.assertFalse(result["targets"][0]["reminder_enabled"])
        self.assertTrue(result["targets"][1]["reminder_enabled"])
        self.assertEqual(self.rule.read_text(), "# Existing user instructions\n")

    def test_numeric_choice_persists_across_cli_processes_without_reopening_credentials(self):
        with patch("pathlib.Path.home", return_value=self.user):
            tasks = Tasks()
            tasks.save(self.state)
        report_file = self.root / "report.json"
        report_file.write_text(json.dumps(self.report))
        self.call("defaults", "--action", "record", "--task", self.state["id"], "--input", report_file)
        listed = self.call("list")["tasks"]
        self.assertEqual(listed[0]["phase"], "default_settings:waiting_choice")
        state = self.call("defaults", "--action", "choose", "--task", self.state["id"], "--choice", "1")
        self.assertEqual(state["credential_phase"], "completed")
        resumed = self.call("defaults", "--action", "status", "--task", self.state["id"])
        self.assertEqual(resumed["default_settings"]["selected"], ["plugin:aihub-studio", "plugin:tikin-social"])
        wrong = self.call("defaults", "--action", "status", "--task", self.state["id"], host="workbuddy", ok=False)
        self.assertEqual(wrong["reason"], "task_context_mismatch")
        self.assertFalse((self.user / ".config/aihub-studio/settings.json").exists())
        cancelled = self.call("cancel", "--task", self.state["id"])
        self.assertEqual(cancelled["phase"], "completed")
        self.assertEqual(cancelled["result"]["default_settings"]["phase"], "skipped")
        self.assertEqual(self.call("list")["tasks"], [])

    def test_skip_and_explicit_subset_do_not_change_rules_or_preferences(self):
        for choice in ("2", "本次跳过"):
            defaults.record(self.state, self.report)
            result = defaults.choose(self.state, choice)
            self.assertEqual(result["phase"], "skipped")
            self.assertFalse(defaults.pending(self.state))
        defaults.record(self.state, self.report)
        result = defaults.choose(self.state, "不再提醒", ["plugin:tikin-social"])
        self.assertEqual(result["selected"], ["plugin:tikin-social"])
        self.assertEqual(self.rule.read_text(), "# Existing user instructions\n")
        self.assertFalse((self.user / ".config").exists())

    def test_preview_confirmation_change_detection_and_combined_rule_readback(self):
        defaults.record(self.state, self.report)
        with self.assertRaises(SetupError):
            defaults.verify(self.state, "1")
        defaults.choose(self.state, "设为默认")
        preview = defaults.preview(self.state, {"shared_with": ["ChatGPT/Codex", "Claude Code"]})["preview"]
        self.assertEqual(len(preview["writes"]), 2)
        self.assertEqual(self.rule.read_text(), "# Existing user instructions\n")
        with self.assertRaises(SetupError):
            defaults.verify(self.state, "wrong")
        self.project_rule.write_text("New project override")
        with self.assertRaisesRegex(SetupError, "default_settings_changed_recheck"):
            defaults.verify(self.state, preview["confirmation"])
        defaults.record(self.state, self.report)
        defaults.choose(self.state, "1")
        preview = defaults.preview(self.state, {"shared_with": []})["preview"]
        defaults.verify(self.state, preview["confirmation"])
        outcomes = {"outcomes": [{"id": w["id"], "status": "written", "session_loaded": "not_verified", "evidence": "synthetic file readback"} for w in preview["writes"]]}
        with self.assertRaises(SetupError):
            defaults.finish(self.state, outcomes)
        # Simulate the host edit after explicit full-preview approval, one edit per entity.
        self.rule.write_text(self.rule.read_text() + "\n".join(w["rule"] for w in preview["writes"]))
        result = defaults.finish(self.state, outcomes)
        self.assertEqual(result["phase"], "completed")
        self.assertEqual(result["eligible"], [])
        self.assertTrue(all(row["status"] == "configured_global" for row in result["targets"]))
        self.assertTrue(self.rule.read_text().startswith("# Existing user instructions\n"))
        self.assertEqual(result["outcomes"][0]["session_loaded"], "not_verified")

    @unittest.skipIf(os.name == "nt", "symlink creation may need native privilege")
    def test_shared_rule_symlink_is_preserved_and_retarget_invalidates_preview(self):
        alias = self.user / "CLAUDE.md"
        alias.symlink_to(self.rule)
        for row in self.report["targets"]:
            row["global_rule_file"] = str(alias)
        defaults.record(self.state, self.report)
        defaults.choose(self.state, "1")
        plan = defaults.preview(self.state, {"shared_with": ["Claude Code"]})["preview"]
        self.assertTrue(alias.is_symlink())
        alias.unlink()
        alias.symlink_to(self.project_rule)
        with self.assertRaises(SetupError):
            defaults.verify(self.state, plan["confirmation"])

    def test_native_target_reminder_commands_are_offline_and_isolated_for_three_host_arguments(self):
        for host in defaults.AGENT_NAMES:
            profile = str(self.user / ("profile-" + host))
            commands = [
                ["node", str(MARKET / "aihub-studio/scripts/aihub.mjs"), "default-skills", "--skill", "aihub-image"],
                ["uv", "run", "--locked", "--no-dev", "--project", str(MARKET / "tikin-social/skills/tikin-setup"), "python",
                 str(MARKET / "tikin-social/skills/tikin-setup/scripts/tikin-config"), "--skill", "tikin-setup", "default-skills"]]
            for command in commands:
                base = command + ["--agent", host, "--config-dir", profile]
                for action in ("check", "dismiss", "check"):
                    run = subprocess.run(base + ["--action", action], env=self.environment(), capture_output=True, timeout=45)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    result = json.loads(run.stdout)
                    if result["status"] == "review_required":
                        self.assertEqual(result["session_loaded"], "not_verified")
                    else:
                        self.assertNotEqual(result.get("session_loaded"), "verified")
                    if action == "dismiss":
                        self.assertFalse(result["reminder_enabled"])
                self.assertEqual(result["status"], "dismissed")
        self.assertEqual(self.rule.read_text(), "# Existing user instructions\n")


if __name__ == "__main__":
    unittest.main()
