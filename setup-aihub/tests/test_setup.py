"""Synthetic credentials only. Public CLI tests do not install any host Plugin."""
import contextlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
MARKET = PLUGIN.parent
SKILL = PLUGIN / "skills/setup-api-key"
SCRIPT = SKILL / "scripts/setup_api_key.py"
sys.path.insert(0, str(SKILL / "scripts"))
from setup_core import local_config
from setup_core.consumers import Consumer
from setup_core.errors import SetupError
from setup_core.local_platform import verify_private_permissions
from setup_core.progress import Tasks, apply_plan, make_plan


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="Setup 合成测试 ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "项目 空格"
        self.project.mkdir()
        self.user = self.root / "用户"
        self.user.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("AIHUB_", "TIKIN_", "SETUP_AIHUB_", "UV_PROJECT_ENVIRONMENT", "GIT_"))}
        self.env.update(HOME=str(self.user), USERPROFILE=str(self.user), PYTHONUTF8="1",
                        UV_PYTHON_DOWNLOADS="never", UV_PYTHON=sys.executable)
        self.marker = "synthetic-sensitive-never-log"

    def call(self, command, *args, ok=True, environment=None):
        proc = subprocess.run([sys.executable, str(SCRIPT), command, "--host", "codex", "--cwd", str(self.project), *map(str, args)],
                              env=environment or self.env, capture_output=True, text=True, encoding="utf-8", timeout=40)
        self.assertNotIn(self.marker, proc.stdout + proc.stderr)
        output = json.loads(proc.stdout)
        if ok:
            self.assertEqual(proc.returncode, 0, output)
            return output["result"]
        self.assertNotEqual(proc.returncode, 0, output)
        return output

    def start(self, plugin="aihub-studio", operation="configure", source="manual", caller=None, submission="unknown"):
        identity = ["--skill", caller] if caller else ["--plugin-only"]
        return self.call("start", "--plugin", plugin, "--plugin-root", MARKET / plugin,
                         *identity, "--operation", operation, "--source", source, "--submission", submission)

    def inspect(self, plugin="aihub-studio", caller=None, *flags):
        identity = ["--skill", caller] if caller else ["--plugin-only"]
        return self.call("inspect", "--plugin", plugin, "--plugin-root", MARKET / plugin, *identity, *flags)["inspection"]

    def global_file(self, plugin):
        path = self.user / ".config" / plugin / ".env"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def plan(self, task, target, fields):
        return self.call("plan", "--task", task["id"], "--target", target, "--fields", fields)

    def apply(self, planned, **kwargs):
        return self.call("apply", "--task", planned["id"], "--confirm", planned["plan"]["confirmation"], **kwargs)

    def dependency(self, version="2.5.1"):
        """Metadata fixture only; the opt-in suite exercises the real release."""
        root = self.root / ("Secret Book " + version)
        root.mkdir(exist_ok=True)
        (root / "pyproject.toml").write_text('[project]\nname = "secret-book"\nversion = "' + version + '"\n')
        (root / "SKILL.md").write_text("---\nname: secret-book\nversion: " + version + "\n---\n")
        for name in ("scripts/secret_book.py", "references/roles.md", "references/consumer-setup.md",
                     ".python-version", "uv.lock"):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic metadata fixture\n")
        return root

    def handoff(self, task, root=None, **kwargs):
        return self.call("handoff", "--task", task["id"], "--availability", "available",
                         "--secret-book-root", root or self.dependency(), **kwargs)

    def test_read_only_shared_inspection_does_not_create_progress(self):
        for plugin in ("aihub-studio", "tikin-social"):
            report = self.inspect(plugin)
            self.assertIsNone(report["skill"])
            self.assertEqual(report["cwd"], str(self.project))
            self.assertEqual(len(report["layers"]), 4)
            self.assertEqual(report["status"], "configuration_required")
        self.assertFalse((self.user / ".config").exists())
        self.assertEqual(list(self.project.iterdir()), [])

    def test_manual_prepare_and_continue_reloads_the_real_business_source(self):
        task = self.start(submission="not_submitted")
        target = self.user / ".config/aihub-studio/.env"
        planned = self.plan(task, target, "AIHUB_API_KEY")
        self.assertFalse(target.exists())
        self.assertEqual(self.call("continue", "--task", task["id"])["phase"], "waiting_confirmation")
        prepared = self.apply(planned)
        self.assertEqual(prepared["phase"], "waiting_manual")
        verify_private_permissions(target)
        self.assertIn("# AIHUB_API_KEY=", target.read_text(encoding="utf-8"))
        unchanged = self.call("continue", "--task", task["id"])
        self.assertEqual(unchanged["phase"], "waiting_manual")
        self.assertEqual(unchanged["last_reason"], "manual_change_not_observed")
        # Simulate the human editing locally; no value ever enters helper argv.
        target.write_text("AIHUB_API_KEY=" + self.marker + "\n", encoding="utf-8")
        done = self.call("continue", "--task", task["id"])
        self.assertEqual(done["phase"], "completed")
        self.assertEqual(done["result"]["local"]["fields"]["AIHUB_API_KEY"]["source"], str(target))
        self.assertEqual(done["result"]["business_next_step"], "return_and_check_original_authorization")
        self.assertEqual(done["result"]["online_authentication"], "not_performed")
        self.assertEqual(done["result"]["business_call"], "not_verified")
        self.assertNotIn(self.marker, (self.user / ".config/setup-aihub/tasks" / (task["id"] + ".json")).read_text())
        self.assertEqual(self.call("list")["tasks"], [])
        self.assertEqual(self.call("continue", "--task", task["id"])["phase"], "completed")

    def test_clear_projects_fallback_and_removes_all_duplicates_preserving_bytes(self):
        for plugin, key in (("aihub-studio", "AIHUB_API_KEY"), ("tikin-social", "TIKIN_API_KEY")):
            with self.subTest(plugin=plugin):
                target = self.project / ".env.local"
                raw = ("# 注释\r\n" + key + "=old\r\nOTHER=unchanged\r\n  " + key + " = '" + self.marker + "'\r\n").encode()
                target.write_bytes(b"\xef\xbb\xbf" + raw)
                fallback = self.global_file(plugin)
                fallback.write_text(key + "=synthetic-fallback", encoding="utf-8")
                task = self.start(plugin, "clear", submission="submitted")
                planned = self.plan(task, target, key)
                preview = planned["plan"]["projection"]
                self.assertEqual(preview["after"]["fields"][key]["source"], str(fallback))
                self.assertEqual(target.read_bytes(), b"\xef\xbb\xbf" + raw)
                done = self.apply(planned)
                self.assertEqual(done["phase"], "completed")
                self.assertEqual(target.read_bytes(), b"\xef\xbb\xbf" + "# 注释\r\nOTHER=unchanged\r\n".encode())
                self.assertEqual(done["result"]["business_next_step"], "query_existing_result")
                self.assertTrue(done["result"]["deletion_effect_matches_preview"])
                verify_private_permissions(target)
                self.assertEqual(list(self.project.glob("*.tmp")), [])

    def test_project_repair_preserves_actual_source_and_environment_is_not_masked(self):
        target = self.project / ".env.local"
        target.write_text("AIHUB_API_KEY=" + self.marker)
        wrong = self.global_file("aihub-studio")
        task = self.start(operation="repair")
        rejected = self.call("plan", "--task", task["id"], "--target", wrong, "--fields", "AIHUB_API_KEY", ok=False)
        self.assertEqual(rejected["reason"], "repair_actual_source")
        plan = self.plan(task, target, "AIHUB_API_KEY")
        result = self.apply(plan)
        self.assertFalse(result["result"]["changed"])
        self.assertEqual(target.read_text(), "AIHUB_API_KEY=" + self.marker)
        self.assertFalse(wrong.exists())
        env = {**self.env, "AIHUB_API_KEY": self.marker}
        rejected = self.call("plan", "--task", task["id"], "--target", target, "--fields", "AIHUB_API_KEY", environment=env, ok=False)
        self.assertEqual(rejected["reason"], "repair_environment_at_injection_source")

    def test_file_or_environment_change_invalidates_confirmation_without_overwriting(self):
        target = self.global_file("aihub-studio")
        target.write_text("AIHUB_API_KEY=" + self.marker)
        task = self.start(operation="clear")
        planned = self.plan(task, target, "AIHUB_API_KEY")
        target.write_text("AIHUB_API_KEY=concurrent\nOTHER=keep")
        rejected = self.apply(planned, ok=False)
        self.assertEqual(rejected["reason"], "sources_changed")
        self.assertIn("concurrent", target.read_text())
        planned = self.plan(task, target, "AIHUB_API_KEY")
        rejected = self.apply(planned, environment={**self.env, "AIHUB_API_KEY": "process-override"}, ok=False)
        self.assertEqual(rejected["reason"], "sources_changed")

    def test_caller_specific_sources_and_global_opt_out_survive_adapter(self):
        for plugin, caller, key in (("aihub-studio", "aihub-image", "AIHUB_API_KEY"), ("tikin-social", "tikin-douyin", "TIKIN_API_KEY")):
            fallback = self.user / ".config" / caller / ".env"
            fallback.parent.mkdir(parents=True)
            fallback.write_text(key + "=" + self.marker)
            self.assertEqual(self.inspect(plugin, caller)["fields"][key]["source"], str(fallback))
            self.assertEqual(self.inspect(plugin)["fields"][key]["source"], "missing")
            self.assertEqual(self.inspect(plugin, caller, "--no-global-config")["fields"][key]["source"], "missing")
            specific = self.project / (".env." + caller)
            specific.write_text(key + "=synthetic-project")
            self.assertEqual(self.inspect(plugin, caller)["fields"][key]["source"], str(specific))
            self.assertEqual(self.inspect(plugin)["fields"][key]["source"], "missing")

    def test_tikin_url_projection_retains_key_and_default_service_relationship(self):
        target = self.global_file("tikin-social")
        target.write_text("TIKIN_API_KEY=" + self.marker + "\nTIKIN_BASE_URL=https://custom.invalid")
        task = self.start("tikin-social", "clear")
        plan = self.plan(task, target, "TIKIN_BASE_URL")
        after = plan["plan"]["projection"]["after"]
        self.assertEqual(after["fields"]["TIKIN_BASE_URL"]["source"], "built-in default")
        self.assertEqual(after["fields"]["TIKIN_API_KEY"]["source"], str(target))
        self.apply(plan)
        self.assertIn(self.marker, target.read_text())
        self.assertFalse((target.parent / "settings.json").exists())

    def test_deletion_projection_keeps_higher_sources_and_unrelated_read_errors(self):
        for plugin, key in (("aihub-studio", "AIHUB_API_KEY"), ("tikin-social", "TIKIN_API_KEY")):
            target = self.global_file(plugin)
            target.write_text(key + "=" + self.marker)
            raw = target.read_bytes()
            unreadable = target.parent / ".env.local"
            unreadable.mkdir()
            with patch.dict(os.environ, {**self.env, key: "synthetic-environment"}, clear=True):
                consumer = Consumer(plugin, MARKET / plugin, None, self.project)
                projection = consumer.inspect({"target": str(target), "fields": [key]})
            self.assertEqual(projection["after"]["fields"][key]["source"], "environment")
            self.assertIn({"source": str(unreadable), "reason": "unreadable"}, projection["after"]["problems"])
            self.assertEqual(target.read_bytes(), raw)

    def test_secret_book_missing_and_mock_handoff_have_one_writer(self):
        task = self.start(source="secret-book", caller="aihub-image")
        missing = self.call("handoff", "--task", task["id"], "--availability", "missing")
        self.assertEqual(len(missing["options"]), 3)
        self.assertEqual(missing["minimum_verified_release"], "2.5.0")
        handoff = self.handoff(task)
        self.assertEqual(handoff["handoff"]["writer"], "secret-book")
        self.assertEqual(handoff["handoff"]["remote_access"], "read_only")
        target = self.user / ".config/aihub-studio/.env"
        denied = self.call("plan", "--task", task["id"], "--target", target, "--fields", "AIHUB_API_KEY", ok=False)
        self.assertEqual(denied["reason"], "secret_book_owns_write")
        # A delegated success without a real saved field cannot finish Setup.
        false_success = self.call("handoff-result", "--task", task["id"], "--status", "completed", "--reference", "mock-public-ref")
        self.assertEqual(false_success["phase"], "inspection")
        self.assertFalse(target.exists())
        self.handoff(task)
        self.global_file("aihub-studio").write_text("AIHUB_API_KEY=" + self.marker)
        done = self.call("handoff-result", "--task", task["id"], "--status", "completed")
        self.assertEqual(done["phase"], "completed")
        self.assertEqual(done["result"]["online_authentication"], "not_performed")

    def test_cross_host_and_corrupt_progress_are_read_only_errors(self):
        task = self.start()
        proc = subprocess.run([sys.executable, str(SCRIPT), "status", "--host", "workbuddy", "--cwd", str(self.project), "--task", task["id"]],
                              env=self.env, capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(json.loads(proc.stdout)["reason"], "task_context_mismatch")
        path = self.user / ".config/setup-aihub/tasks" / (task["id"] + ".json")
        path.write_text('{"schema":"future"}')
        before = path.read_bytes()
        self.assertEqual(self.call("status", "--task", task["id"], ok=False)["reason"], "unsupported_progress_schema")
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_write_result_cannot_be_replayed_after_process_restart(self):
        target = self.global_file("aihub-studio")
        target.write_text("AIHUB_API_KEY=" + self.marker)
        task = self.start(operation="clear")
        self.plan(task, target, "AIHUB_API_KEY")
        actual_replace = os.replace

        def fail_target(source, destination):
            if Path(destination) == target:
                raise PermissionError("synthetic sharing violation")
            return actual_replace(source, destination)

        with patch.dict(os.environ, self.env, clear=True):
            tasks = Tasks()
            state = tasks.load(task["id"])
            with patch("setup_core.local_config.os.replace", side_effect=fail_target):
                with self.assertRaises(PermissionError):
                    apply_plan(tasks, state, state["plan"]["confirmation"])
        status = self.call("status", "--task", task["id"])
        self.assertEqual(status["phase"], "result_unknown")
        denied = self.call("continue", "--task", task["id"], ok=False)
        self.assertEqual(denied["reason"], "reconcile_before_retry")
        self.assertEqual(target.read_text(), "AIHUB_API_KEY=" + self.marker)
        self.assertEqual(list(target.parent.glob("*.tmp")), [])
        reconciled = self.call("reconcile", "--task", task["id"])
        self.assertEqual(reconciled["phase"], "inspection")
        self.assertNotIn("plan", reconciled)

    def test_git_guard_uses_actual_tracked_and_ignored_paths_without_creating_branches(self):
        # Use existing repository facts; no temporary branch or repository is made.
        with self.assertRaisesRegex(SetupError, "target_tracked"):
            local_config.git_safe(MARKET / "README.md")
        with self.assertRaisesRegex(SetupError, "target_not_ignored"):
            local_config.git_safe(MARKET / "setup-aihub-untracked-probe.txt")
        local_config.git_safe(MARKET / "tmp/setup-aihub-test/.env.local")
        with patch.dict(os.environ, {"GIT_DIR": str(self.root / "absent"), "GIT_WORK_TREE": str(self.project),
                                    "GIT_INDEX_FILE": str(self.root / "index")}):
            with self.assertRaisesRegex(SetupError, "target_tracked"):
                local_config.git_safe(MARKET / "README.md")
        ignore = self.root / "git-ignore"
        ignore.write_text("setup-aihub-untracked-probe.txt\n")
        config = self.root / "git-config"
        config.write_text('[core]\n  excludesFile = "' + ignore.as_posix() + '"\n', encoding="utf-8")
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"}):
            local_config.git_safe(MARKET / "setup-aihub-untracked-probe.txt")

    def test_path_redirect_and_unsupported_encoding_stop_before_writing(self):
        task = self.start(operation="clear")
        target = self.project / ".env.local"
        target.write_text("AIHUB_API_KEY=" + self.marker)
        plan = self.plan(task, target, "AIHUB_API_KEY")
        other = self.root / "unrelated"
        other.write_text("OTHER=preserve")
        target.unlink()
        try:
            target.symlink_to(other)
        except OSError:
            self.skipTest("OS account cannot create symlinks")
        rejected = self.apply(plan, ok=False)
        self.assertIn(rejected["reason"], ("linked_path_refused", "sources_changed"))
        self.assertEqual(other.read_text(), "OTHER=preserve")
        target.unlink()
        target.write_bytes("AIHUB_API_KEY=x".encode("utf-16"))
        denied = self.call("plan", "--task", task["id"], "--target", target, "--fields", "AIHUB_API_KEY", ok=False)
        self.assertIn(denied["reason"], ("unsupported_encoding", "unreadable_configuration"))

    def test_cancellation_and_multi_plugin_progress_do_not_repeat_completed_work(self):
        one = self.start()
        two = self.start("tikin-social")
        self.assertEqual(len(self.call("list")["tasks"]), 2)
        self.call("cancel", "--task", one["id"])
        listing = self.call("list")["tasks"]
        self.assertEqual([item["id"] for item in listing], [two["id"]])
        self.assertFalse((self.user / ".config/aihub-studio").exists())

    def test_invalid_argv_does_not_echo_accidental_key(self):
        result = self.call("list", "--unknown", self.marker, ok=False)
        self.assertEqual(result["reason"], "invalid_arguments")

    def test_delegated_unknown_outcome_must_be_resolved_by_original_writer(self):
        task = self.start(source="secret-book", caller="aihub-image")
        self.handoff(task)
        self.call("handoff-result", "--task", task["id"], "--status", "pending", "--reference", "mock-resume-id")
        unknown = self.call("handoff-result", "--task", task["id"], "--status", "unknown")
        self.assertEqual(unknown["secret_book"]["reference"], "mock-resume-id")
        self.assertEqual(unknown["secret_book"]["dependency"]["version"], "2.5.1")
        for command, args in (("source", ["--source", "manual"]), ("reconcile", []), ("cancel", []),
                              ("handoff", ["--availability", "available"])):
            denied = self.call(command, "--task", task["id"], *args, ok=False)
            self.assertEqual(denied["reason"], "secret_book_owns_write")
        self.assertEqual(self.call("continue", "--task", task["id"])["phase"], "waiting_secret_book")
        cancelled = self.call("handoff-result", "--task", task["id"], "--status", "cancelled")
        self.assertEqual(cancelled["phase"], "cancelled")
        self.assertFalse((self.user / ".config/aihub-studio").exists())

    def test_business_reference_and_secret_book_selection_survive_resumption(self):
        record = self.project / "business.json"
        record.write_text('{"request":"synthetic-sensitive-never-log"}')
        task = self.call("start", "--plugin", "aihub-studio", "--plugin-root", MARKET / "aihub-studio",
                         "--skill", "aihub-image", "--operation", "repair", "--source", "secret-book",
                         "--submission", "submitted", "--business-record", record, "--business-task-id", "job_123")
        target = self.global_file("aihub-studio")
        self.call("select", "--task", task["id"], "--target", target, "--fields", "AIHUB_API_KEY")
        handoff = self.handoff(task)
        self.assertEqual(handoff["handoff"]["selection"], {"target": str(target), "fields": ["AIHUB_API_KEY"]})
        self.assertEqual(handoff["handoff"]["skill"], "aihub-image")
        state = self.call("status", "--task", task["id"])
        self.assertEqual(state["business"], {"record": str(record), "task_id": "job_123"})
        self.assertFalse(target.exists())

    def test_unplanned_clear_is_read_only_on_continue(self):
        task = self.start(operation="clear")
        current = self.call("continue", "--task", task["id"])
        self.assertEqual(current["phase"], "inspection")
        self.assertEqual(current["result"]["business_next_step"], "reconcile_submission")

    def test_shared_caller_requires_251_and_preserves_null(self):
        for plugin in ("aihub-studio", "tikin-social"):
            task = self.start(plugin, source="secret-book")
            denied = self.handoff(task, self.dependency("2.5.0"), ok=False)
            self.assertEqual(denied["reason"], "secret_book_version_incompatible")
            self.assertEqual(denied["compatibility"]["minimum_verified_release"], "2.5.1")
            current = self.call("status", "--task", task["id"])
            self.assertEqual(current, task)
            accepted = self.handoff(task)["handoff"]
            self.assertIsNone(accepted["skill"])
            self.assertIsNone(accepted["inspection"]["skill"])
            self.assertEqual(accepted["caller_mode"], "plugin_shared")
            self.assertEqual(accepted["dependency"]["version"], "2.5.1")
            self.assertEqual(accepted["cwd"], str(self.project))

    def test_real_caller_keeps_250_compatibility_but_check_cannot_delegate(self):
        task = self.start(source="secret-book", caller="aihub-image")
        accepted = self.handoff(task, self.dependency("2.5.0"))["handoff"]
        self.assertEqual(accepted["minimum_verified_release"], "2.5.0")
        self.assertEqual(accepted["dependency"]["version"], "2.5.0")
        check = self.start(source="secret-book", operation="check", caller="aihub-image")
        denied = self.handoff(check, ok=False)
        self.assertEqual(denied["reason"], "invalid_secret_book_operation")

    def test_dependency_errors_leave_task_available_for_manual_fallback(self):
        task = self.start(source="secret-book")
        missing = self.call("handoff", "--task", task["id"], "--availability", "available", ok=False)
        self.assertEqual(missing["reason"], "secret_book_location_required")
        for problem in ("inconsistent", "unreadable", "incomplete", "unstable"):
            with self.subTest(problem=problem):
                root = self.dependency("2.5.1rc1" if problem == "unstable" else "2.5.1")
                if problem == "inconsistent":
                    (root / "SKILL.md").write_text("---\nname: secret-book\nversion: 2.5.0\n---\n")
                elif problem == "unreadable":
                    (root / "pyproject.toml").write_text(self.marker)
                elif problem == "incomplete":
                    (root / "references/roles.md").unlink()
                denied = self.handoff(task, root, ok=False)
                self.assertEqual(denied["reason"], "secret_book_artifact_invalid")
                self.assertEqual(self.call("status", "--task", task["id"]), task)
        self.call("source", "--task", task["id"], "--source", "manual")
        self.assertFalse((self.user / ".config/aihub-studio").exists())

    def test_dependency_accepts_published_metadata_version_and_legacy_format(self):
        root = self.dependency("2.5.4")
        for fields in (
            'metadata:\n  version: "2.5.4"\n',
            'metadata: # public artifact metadata\n  version: "2.5.4" # stable\n',
            "version: 2.5.4\n",
            'version: 2.5.4\nmetadata:\n  version: "2.5.4"\n',
        ):
            with self.subTest(fields=fields):
                (root / "SKILL.md").write_text("---\nname: secret-book\n" + fields
                                               + "description: >-\n  v2.5.4｜public artifact\n---\n", encoding="utf-8")
                task = self.start("tikin-social", source="secret-book")
                accepted = self.handoff(task, root)["handoff"]
                self.assertEqual(accepted["dependency"]["version"], "2.5.4")
                self.assertIsNone(accepted["skill"])
                self.assertEqual(accepted["cwd"], str(self.project))

    def test_invalid_metadata_versions_do_not_fall_back_or_change_task(self):
        root = self.dependency("2.5.4")
        task = self.start("tikin-social", source="secret-book")
        for fields in (
            "metadata:\n  author: fixture\n",
            'metadata:\n  version: "2.5.3"\n',
            'metadata:\n  version: "2.5.4"\n  version: "2.5.4"\n',
            'metadata:\n  version: "2.5.4"\nmetadata:\n  version: "2.5.4"\n',
            "version: 2.5.4\nversion: 2.5.4\n",
            'version: 2.5.4\nmetadata:\n  version: "2.5.3"\n',
            'version: 2.5.4\nmetadata:\n  version: "invalid"\n',
            'version: invalid\nmetadata:\n  version: "2.5.4"\n',
            "version: 2.5.4\nmetadata:\n  version:\n",
            'metadata:\n  version: "2.5.4" trailing\n',
            'metadata:\n  nested:\n    version: "2.5.4"\n',
        ):
            with self.subTest(fields=fields):
                (root / "SKILL.md").write_text("---\nname: secret-book\n" + fields + "---\n")
                denied = self.handoff(task, root, ok=False)
                self.assertEqual(denied["reason"], "secret_book_artifact_invalid")
                self.assertEqual(self.call("status", "--task", task["id"]), task)
        self.assertFalse((self.user / ".config/tikin-social").exists())


if __name__ == "__main__":
    unittest.main()
