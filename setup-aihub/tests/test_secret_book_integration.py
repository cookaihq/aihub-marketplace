"""Opt-in public CLI integration with a fixed Secret Book 2.5.1 source snapshot.

SETUP_AIHUB_TEST_SECRET_BOOK_ROOT points to an isolated export, never a user's
installed Skill. Its published test fixture replaces only the lark-cli process.
No Secret Book private task files are inspected or modified by these tests.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import tomllib
import unittest

MARKET = Path(__file__).resolve().parents[2]
SKILL = MARKET / "setup-aihub/skills/setup-api-key"
SETUP = SKILL / "scripts/setup_api_key.py"
SECRET_BOOK = os.environ.get("SETUP_AIHUB_TEST_SECRET_BOOK_ROOT")


@unittest.skipUnless(SECRET_BOOK, "requires an isolated Secret Book 2.5.1 export")
class SecretBookIntegrationTests(unittest.TestCase):
    secret_book_version = "2.5.1"

    def setUp(self):
        self.secret_book = Path(SECRET_BOOK).resolve()
        version = tomllib.loads((self.secret_book / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        self.assertEqual(version, self.secret_book_version)
        self.sb_python = self.secret_book / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        self.assertTrue(self.sb_python.is_file(), "sync the isolated snapshot's locked runtime first")
        self.support = self.secret_book / "tests/support"
        self.assertTrue((self.support / "sitecustomize.py").is_file())
        self.assertTrue((self.support / "fake_lark_cli.py").is_file())
        temporary = tempfile.TemporaryDirectory(prefix="Setup Secret Book 合成 ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cwd, self.user = self.root / "业务 项目", self.root / "用户"
        self.cwd.mkdir()
        self.user.mkdir()
        self.state_path, self.log_path = self.root / "fake-lark.json", self.root / "lark-calls.jsonl"
        self.marker = "setup-integration-synthetic-secret"
        self.fake = {
            "profiles": [{"name": "work-profile", "tokenStatus": "valid", "active": False,
                          "user": "Test User", "brand": "feishu", "appId": "cli_test_work"}],
            "auth": {"work-profile": {"identity": "user", "identities": {"user": {
                "status": "ready", "available": True, "tokenStatus": "valid", "openId": "ou_test_work"}}}},
            "resolved_url": {"base_token": "app_work", "block_id": "tbl_work"},
            "records": {"app_work": [{"_record_id": "rec_work", "id": "sec_setup", "name": "合成凭证",
                "service": "fixture", "account": "test", "purpose": "local integration", "visible_to": None,
                "secret": "AIHUB_API_KEY=" + self.marker + "\nTIKIN_API_KEY=" + self.marker}]},
        }
        self.write_fake()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith((
            "AIHUB_", "TIKIN_", "SECRET_BOOK_", "SETUP_AIHUB_", "GIT_", "UV_PROJECT_ENVIRONMENT",
            "CODEX_", "CLAUDE_", "WORKBUDDY_", "CODEBUDDY_", "FAKE_LARK_"))}
        self.env.update(HOME=str(self.user), USERPROFILE=str(self.user), PYTHONUTF8="1",
                        PYTHONPATH=str(self.support), FAKE_LARK_STATE=str(self.state_path),
                        FAKE_LARK_LOG=str(self.log_path), UV_PYTHON_DOWNLOADS="never")
        if os.name != "nt":
            binaries = self.root / "bin"
            binaries.mkdir()
            wrapper = binaries / "lark-cli"
            wrapper.write_text("#!/bin/sh\nexec " + shlex.quote(str(self.sb_python)) + " "
                               + shlex.quote(str(self.support / "fake_lark_cli.py")) + ' "$@"\n')
            wrapper.chmod(0o755)
            self.env["PATH"] = str(binaries) + os.pathsep + self.env.get("PATH", "")
        self.outputs = []

    def write_fake(self):
        self.state_path.write_text(json.dumps(self.fake, ensure_ascii=False), encoding="utf-8")

    def process(self, command, expected=0, extra_env=None):
        result = subprocess.run(list(map(str, command)), cwd=self.cwd,
                                env={**self.env, **(extra_env or {})}, capture_output=True,
                                text=True, encoding="utf-8", timeout=60)
        self.assertNotIn(self.marker, result.stdout + result.stderr)
        self.outputs.append(result.stdout)
        self.last_stderr = result.stderr
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout.strip().startswith("{") else result.stdout

    def setup(self, action, *args, expected=0):
        result = self.process([sys.executable, SETUP, action, "--host", "codex", "--cwd", self.cwd, *args], expected)
        return result["result"] if expected == 0 else result

    def sb(self, *args, expected=0, extra_env=None):
        return self.process([self.sb_python, self.secret_book / "scripts/secret_book.py", *args], expected, extra_env)

    def workflow(self):
        result = self.sb("workflow", "start", "--role", "consumer", "--basis", "inferred",
                         "--goal", "为业务 Plugin 配置合成凭证", "--agent", "codex")
        return result["task"]["id"]

    def flags(self, workflow):
        return ["--workflow", workflow, "--workflow-agent", "codex"]

    def status(self, workflow):
        return self.sb("workflow", "status", "--id", workflow, "--agent", "codex",
                       extra_env={"FAKE_LARK_FAIL_ON_CALL": "1"})["task"]

    def connect(self, workflow):
        if getattr(self, "connection_ready", False):
            self.sb("config", "list", *self.flags(workflow))
            return
        args = ["init-connect", "--url", "https://example.feishu.cn/base/test",
                "--lark-profile", "work-profile", *self.flags(workflow)]
        pending = self.sb(*args, expected=3)
        token = self.status(workflow)["pending"]["confirmation_token"]
        self.assertEqual(pending["confirmation_token"], token)
        connected = self.sb(*args, "--confirm-identity", token)
        self.assertEqual(connected["status"], "connected_read_only")
        # Parse the public CLI's own handoff as argv; never execute a shell string.
        save = shlex.split(connected["save_command"])[5:]
        save[save.index("<名称>")] = "合成连接"
        self.sb(*save)
        self.connection_ready = True

    def prepare(self, plugin, caller, *, global_enabled=True, operation="configure"):
        identity = ["--skill", caller] if caller else ["--plugin-only"]
        extra = [] if global_enabled else ["--no-global-config"]
        task = self.setup("start", "--plugin", plugin, "--plugin-root", MARKET / plugin, *identity,
                          "--operation", operation, "--source", "secret-book", "--submission", "submitted", *extra)
        handoff = self.setup("handoff", "--task", task["id"], "--availability", "available",
                             "--secret-book-root", self.secret_book)["handoff"]
        self.assertEqual(handoff["dependency"]["version"], self.secret_book_version)
        self.assertEqual(handoff["dependency"]["root"], str(self.secret_book))
        report = self.root / (task["id"] + ".json")
        report.write_text(json.dumps(handoff["inspection"]), encoding="utf-8")
        return task, handoff, report

    def only_remote_reads(self):
        calls = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(calls)
        self.assertTrue(all(call[1] in ("+url-resolve", "+field-list", "+record-list")
                            for call in calls if call[0] == "base"), calls)
        self.assertTrue(all("--profile" in call for call in calls if call[0] == "base"), calls)

    def assert_tikin_effective_endpoint(self, expected, caller=None, *, global_enabled=True):
        skill = MARKET / "tikin-social/skills/tikin-setup"
        identity = ["--skill", caller] if caller else ["--plugin-only"]
        global_flags = [] if global_enabled else ["--no-global-config"]
        # Exercise the real business execution path with a local, non-networking
        # probe. Only a boolean leaves the child; credential values stay hidden.
        probe = ("import json, os, sys; print(json.dumps({'endpoint_matches': "
                 "os.environ.get('TIKIN_BASE_URL') == sys.argv[1]}))")
        result = self.process(["uv", "run", "--locked", "--no-dev", "--offline", "--project", skill,
                               "python", skill / "scripts/tikin-config", *identity, *global_flags,
                               "run", "--", sys.executable, "-c", probe, expected])
        self.assertEqual(result, {"endpoint_matches": True})

    def test_real_callers_save_resume_and_recheck_through_public_clis(self):
        for plugin, caller, key in (("aihub-studio", "aihub-image", "AIHUB_API_KEY"),
                                   ("tikin-social", "tikin-douyin", "TIKIN_API_KEY")):
            with self.subTest(plugin=plugin):
                task, handoff, report = self.prepare(plugin, caller)
                workflow = self.workflow()
                self.setup("handoff-result", "--task", task["id"], "--status", "pending", "--reference", workflow)
                self.connect(workflow)
                target = self.user / ".config" / plugin / ".env"
                args = ["configure", "--requirements", handoff["declaration_path"], "--inspection", report,
                        "--agent", "codex", "--id", "sec_setup", "--key", key, "--use-global-config", *self.flags(workflow)]
                preview = self.sb(*args, expected=3)
                self.assertEqual(preview["status"], "confirmation_required")
                self.assertEqual(preview["review"]["changes"][0]["path"], str(target))
                self.assertFalse(target.exists())
                token = self.status(workflow)["pending"]["confirmation_token"]
                self.sb("configure-status", "--requirements", handoff["declaration_path"], *self.flags(workflow),
                        extra_env={"FAKE_LARK_FAIL_ON_CALL": "1"})
                self.assertEqual(self.status(workflow)["pending"]["confirmation_token"], token)
                self.assertEqual(self.sb(*args, "--confirm", token)["status"], "written")
                self.assertEqual(self.status(workflow)["stage"], "step_complete")
                self.sb("workflow", "finish", "--id", workflow, "--agent", "codex")
                done = self.setup("handoff-result", "--task", task["id"], "--status", "completed", "--reference", workflow)
                self.assertEqual(done["phase"], "completed")
                self.assertEqual(done["result"]["local"]["fields"][key]["source"], str(target))
                self.assertEqual(done["result"]["business_next_step"], "query_existing_result")
                self.assertEqual(done["result"]["online_authentication"], "not_performed")
                self.assertEqual(done["result"]["business_call"], "not_verified")
        self.only_remote_reads()

    def test_real_project_source_and_global_opt_out_are_preserved(self):
        target = self.cwd / ".env.local"
        target.write_text("# preserve\nAIHUB_API_KEY=synthetic-old\nUNRELATED=keep\n", encoding="utf-8")
        task, handoff, report = self.prepare("aihub-studio", "aihub-image", global_enabled=False, operation="repair")
        self.assertFalse(handoff["global_enabled"])
        workflow = self.workflow()
        self.connect(workflow)
        args = ["configure", "--requirements", handoff["declaration_path"], "--inspection", report,
                "--agent", "codex", "--id", "sec_setup", "--key", "AIHUB_API_KEY", "--scope", "global",
                "--use-global-config", *self.flags(workflow)]
        preview = self.sb(*args, expected=3)
        self.assertEqual(preview["review"]["changes"][0]["path"], str(target))
        token = self.status(workflow)["pending"]["confirmation_token"]
        self.sb(*args, "--confirm", token)
        done = self.setup("handoff-result", "--task", task["id"], "--status", "completed", "--reference", workflow)
        self.assertEqual(done["result"]["local"]["fields"]["AIHUB_API_KEY"]["source"], str(target))
        self.assertIn("UNRELATED=keep", target.read_text(encoding="utf-8"))
        self.assertFalse((self.user / ".config/aihub-studio/.env").exists())
        self.only_remote_reads()

    def shared_command(self, handoff, report, key, workflow):
        self.assertIsNone(handoff["skill"])
        self.assertIsNone(handoff["inspection"]["skill"])
        return ["configure", "--requirements", handoff["declaration_path"], "--inspection", report,
                "--agent", "codex", "--id", "sec_setup", "--key", key, "--use-global-config", *self.flags(workflow)]

    def complete_shared(self, task, command, workflow, target, key):
        self.setup("handoff-result", "--task", task["id"], "--status", "pending", "--reference", workflow)
        preview = self.sb(*command, expected=3)
        self.assertEqual(preview["status"], "confirmation_required")
        self.assertIsNone(preview["review"]["skill"])
        self.assertEqual(preview["review"]["changes"][0]["path"], str(target))
        token = self.status(workflow)["pending"]["confirmation_token"]
        self.sb("configure-status", "--requirements", command[2], *self.flags(workflow),
                extra_env={"FAKE_LARK_FAIL_ON_CALL": "1"})
        self.assertEqual(self.status(workflow)["pending"]["confirmation_token"], token)
        # A new Setup invocation retains the null caller and original writer.
        resumed = self.setup("continue", "--task", task["id"])
        self.assertEqual(resumed["phase"], "waiting_secret_book")
        self.assertIsNone(resumed["context"]["caller"])
        self.assertEqual(resumed["secret_book"]["reference"], workflow)
        self.assertEqual(self.sb(*command, "--confirm", token)["status"], "written")
        self.sb("workflow", "finish", "--id", workflow, "--agent", "codex")
        done = self.setup("handoff-result", "--task", task["id"], "--status", "completed", "--reference", workflow)
        self.assertEqual(done["phase"], "completed")
        self.assertIsNone(done["result"]["local"]["skill"])
        self.assertEqual(done["result"]["local"]["fields"][key]["source"], str(target))
        self.assertEqual(done["result"]["business_next_step"], "query_existing_result")
        self.assertEqual(done["result"]["online_authentication"], "not_performed")
        self.assertEqual(done["result"]["business_call"], "not_verified")

    def test_both_shared_saves_resume_and_recheck_without_skill_layers(self):
        for plugin, caller, key in (("aihub-studio", "aihub-image", "AIHUB_API_KEY"),
                                   ("tikin-social", "tikin-douyin", "TIKIN_API_KEY")):
            with self.subTest(plugin=plugin):
                excluded = [self.cwd / (".env." + caller), self.user / ".config" / plugin / caller / ".env",
                            self.user / ".config" / caller / ".env"]
                for path in excluded:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(key + "=synthetic-excluded\n", encoding="utf-8")
                task, handoff, report = self.prepare(plugin, None)
                self.assertFalse(handoff["inspection"]["fields"][key]["present"])
                self.assertTrue(all(layer["path"] not in {str(p) for p in excluded}
                                    for layer in handoff["inspection"]["layers"]))
                workflow = self.workflow()
                self.connect(workflow)
                target = self.user / ".config" / plugin / ".env"
                self.assertFalse(target.exists())
                self.complete_shared(task, self.shared_command(handoff, report, key, workflow), workflow, target, key)
                for path in excluded:
                    self.assertEqual(path.read_text(), key + "=synthetic-excluded\n")
        self.only_remote_reads()

    def test_both_shared_repairs_keep_project_source_and_global_opt_out(self):
        target = self.cwd / ".env.local"
        target.write_text("AIHUB_API_KEY=synthetic-old\nTIKIN_API_KEY=synthetic-old\nUNRELATED=keep\n", encoding="utf-8")
        for plugin, key in (("aihub-studio", "AIHUB_API_KEY"), ("tikin-social", "TIKIN_API_KEY")):
            with self.subTest(plugin=plugin):
                task, handoff, report = self.prepare(plugin, None, global_enabled=False, operation="repair")
                self.assertFalse(handoff["global_enabled"])
                workflow = self.workflow()
                self.connect(workflow)
                command = self.shared_command(handoff, report, key, workflow) + ["--scope", "global"]
                self.complete_shared(task, command, workflow, target, key)
                self.assertFalse((self.user / ".config" / plugin / ".env").exists())
        self.assertIn("UNRELATED=keep", target.read_text())
        self.only_remote_reads()

    def test_both_shared_global_opt_out_requires_explicit_project_for_new_save(self):
        for plugin, key in (("aihub-studio", "AIHUB_API_KEY"), ("tikin-social", "TIKIN_API_KEY")):
            with self.subTest(plugin=plugin):
                task, handoff, report = self.prepare(plugin, None, global_enabled=False)
                workflow = self.workflow()
                self.connect(workflow)
                command = self.shared_command(handoff, report, key, workflow)
                blocked = self.sb(*command, expected=3, extra_env={"FAKE_LARK_FAIL_ON_CALL": "1"})
                self.assertEqual(blocked["status"], "global_disabled")
                self.complete_shared(task, command + ["--scope", "project"], workflow, self.cwd / ".env.local", key)
                self.assertFalse((self.user / ".config" / plugin / ".env").exists())
        self.only_remote_reads()

    def test_tikin_key_only_keeps_default_service_without_persisting_optional_url(self):
        task, handoff, report = self.prepare("tikin-social", None, global_enabled=False)
        workflow = self.workflow()
        self.connect(workflow)
        target = self.cwd / ".env.local"
        command = self.shared_command(handoff, report, "TIKIN_API_KEY", workflow) + ["--scope", "project"]
        self.complete_shared(task, command, workflow, target, "TIKIN_API_KEY")
        saved_keys = [line.split("=", 1)[0] for line in target.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#")]
        self.assertEqual(saved_keys, ["TIKIN_API_KEY"])
        current = self.setup("inspect", "--plugin", "tikin-social", "--plugin-root", MARKET / "tikin-social",
                             "--plugin-only", "--no-global-config")["inspection"]
        self.assertEqual(current["fields"]["TIKIN_BASE_URL"]["source"], "built-in default")
        self.assert_tikin_effective_endpoint("https://console.tikin.net", global_enabled=False)
        self.assertFalse((self.user / ".config/tikin-social").exists())
        self.only_remote_reads()

    def test_tikin_custom_service_requires_explicit_selection_of_related_field(self):
        self.fake["records"]["app_work"][0]["secret"] = (
            "TIKIN_API_KEY=" + self.marker + "\nTIKIN_BASE_URL=https://tikin-test.example.invalid")
        self.write_fake()
        task, handoff, report = self.prepare("tikin-social", None)
        workflow = self.workflow()
        self.connect(workflow)
        target = self.user / ".config/tikin-social/.env"
        command = self.shared_command(handoff, report, "TIKIN_API_KEY", workflow)
        blocked = self.sb(*command, expected=3)
        self.assertEqual(blocked["status"], "related_fields_differ")
        self.assertEqual(blocked["keys"], ["TIKIN_BASE_URL"])
        self.assertEqual(blocked["sources"]["TIKIN_BASE_URL"], "built-in default")
        self.assertFalse(target.exists())
        self.assertFalse((self.cwd / ".env.local").exists())
        self.complete_shared(task, command + ["--key", "TIKIN_BASE_URL"], workflow, target, "TIKIN_API_KEY")
        current = self.setup("inspect", "--plugin", "tikin-social", "--plugin-root", MARKET / "tikin-social",
                             "--plugin-only")["inspection"]
        self.assertEqual(current["fields"]["TIKIN_BASE_URL"]["source"], str(target))
        self.assert_tikin_effective_endpoint("https://tikin-test.example.invalid")
        self.only_remote_reads()

    def test_tikin_related_fields_repair_their_distinct_original_sources(self):
        project_file = self.cwd / ".env.local"
        shared_file = self.user / ".config/tikin-social/.env"
        shared_file.parent.mkdir(parents=True)
        project_before = "TIKIN_API_KEY=synthetic-old\nPROJECT_KEEP=unchanged\n"
        shared_before = "TIKIN_BASE_URL=https://old-tikin.example.invalid\nSHARED_KEEP=unchanged\n"
        project_file.write_text(project_before, encoding="utf-8")
        shared_file.write_text(shared_before, encoding="utf-8")
        self.fake["records"]["app_work"][0]["secret"] = (
            "TIKIN_API_KEY=" + self.marker + "\nTIKIN_BASE_URL=https://new-tikin.example.invalid")
        self.write_fake()
        task, handoff, report = self.prepare("tikin-social", "tikin-douyin", operation="repair")
        workflow = self.workflow()
        self.setup("handoff-result", "--task", task["id"], "--status", "pending", "--reference", workflow)
        self.connect(workflow)
        command = ["configure", "--requirements", handoff["declaration_path"], "--inspection", report,
                   "--agent", "codex", "--id", "sec_setup", "--key", "TIKIN_API_KEY", "--scope", "project",
                   "--use-global-config", *self.flags(workflow)]
        blocked = self.sb(*command, expected=3)
        self.assertEqual(blocked["status"], "related_fields_differ")
        self.assertEqual(blocked["sources"]["TIKIN_BASE_URL"], str(shared_file))
        self.assertEqual(project_file.read_text(encoding="utf-8"), project_before)
        self.assertEqual(shared_file.read_text(encoding="utf-8"), shared_before)
        command += ["--key", "TIKIN_BASE_URL"]
        preview = self.sb(*command, expected=3)
        self.assertEqual(preview["status"], "confirmation_required")
        self.assertEqual({row["key"]: (row["path"], row["operation"]) for row in preview["review"]["changes"]}, {
            "TIKIN_API_KEY": (str(project_file), "replace"),
            "TIKIN_BASE_URL": (str(shared_file), "replace"),
        })
        token = self.status(workflow)["pending"]["confirmation_token"]
        self.sb("configure-status", "--requirements", handoff["declaration_path"], *self.flags(workflow),
                extra_env={"FAKE_LARK_FAIL_ON_CALL": "1"})
        self.assertEqual(self.status(workflow)["pending"]["confirmation_token"], token)
        self.assertEqual(self.setup("continue", "--task", task["id"])["phase"], "waiting_secret_book")
        written = self.sb(*command, "--confirm", token)
        self.assertEqual(written["status"], "written")
        self.assertEqual({row["path"] for row in written["written"]}, {str(project_file), str(shared_file)})
        self.sb("workflow", "finish", "--id", workflow, "--agent", "codex")
        done = self.setup("handoff-result", "--task", task["id"], "--status", "completed", "--reference", workflow)
        self.assertEqual(done["phase"], "completed")
        self.assertEqual(done["result"]["local"]["fields"]["TIKIN_API_KEY"]["source"], str(project_file))
        self.assertEqual(done["result"]["local"]["fields"]["TIKIN_BASE_URL"]["source"], str(shared_file))
        self.assert_tikin_effective_endpoint("https://new-tikin.example.invalid", "tikin-douyin")
        self.assertIn("PROJECT_KEEP=unchanged", project_file.read_text(encoding="utf-8"))
        self.assertNotIn("TIKIN_BASE_URL", project_file.read_text(encoding="utf-8"))
        self.assertIn("SHARED_KEEP=unchanged", shared_file.read_text(encoding="utf-8"))
        self.assertNotIn("TIKIN_API_KEY", shared_file.read_text(encoding="utf-8"))
        self.only_remote_reads()

    def test_consumer_missing_record_id_never_backfills_and_can_cancel(self):
        self.fake["records"]["app_work"][0]["id"] = ""
        self.write_fake()
        task, handoff, report = self.prepare("aihub-studio", "aihub-image")
        workflow = self.workflow()
        self.connect(workflow)
        missing = self.sb("get", "--name", "合成凭证", "--use-global-config", *self.flags(workflow), expected=3)
        self.assertEqual(missing["status"], "record_id_missing")
        self.sb("workflow", "finish", "--id", workflow, "--agent", "codex", "--outcome", "cancelled")
        cancelled = self.setup("handoff-result", "--task", task["id"], "--status", "cancelled", "--reference", workflow)
        self.assertEqual(cancelled["phase"], "cancelled")
        self.assertFalse((self.user / ".config/aihub-studio/.env").exists())
        self.only_remote_reads()


if __name__ == "__main__":
    unittest.main()
