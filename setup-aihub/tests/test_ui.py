"""Real loader/file/HTTP tests; all credentials and Feishu responses are synthetic."""
import contextlib
import hashlib
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request

from test_setup import MARKET, SKILL
from setup_core.errors import SetupError
from setup_core.consumers import fingerprint
from setup_core.local_platform import verify_private_permissions
from setup_core.ui_model import ConfigurationUI
from setup_core.ui_server import Server

RUN = subprocess.run


class UITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="credential-ui-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = self.root / "业务 空格"
        self.project.mkdir()
        self.user = self.root / "用户"
        self.user.mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("AIHUB_", "TIKIN_", "SECRET_BOOK_", "GIT_", "UV_PROJECT_ENVIRONMENT"))}
        env.update(HOME=str(self.user), USERPROFILE=str(self.user), UV_PYTHON=sys.executable, UV_PYTHON_DOWNLOADS="never")
        self.environment = patch.dict(os.environ, env, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        previous = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, previous)
        self.options = {"host": "codex", "cwd": str(self.project), "services": {
            name: {"root": str(MARKET / name), "caller": None, "installation": "unknown"} for name in ("aihub-studio", "tikin-social")},
            "global_enabled": True, "operation": "configure", "submission": "submitted", "business": {}, "plugin": "aihub-studio", "task": None}
        self.ui = ConfigurationUI(self.root / "runtime", self.options)
        self.marker = "synthetic-ui-never-log-" + "x" * 20

    def manual(self, **extra):
        return self.ui.action("manual", {"values": {"AIHUB_API_KEY": self.marker}, "scope": "global", **extra})

    def confirm(self, preview):
        return self.ui.action("save", {"id": preview["preview"]["id"]})

    def assert_private_state(self):
        self.assertNotIn(self.marker, json.dumps(self.ui.public()))
        for directory in (self.root / "runtime", self.user / ".config/setup-aihub"):
            for path in directory.rglob("*"):
                if path.is_file():
                    self.assertNotIn(self.marker.encode(), path.read_bytes(), str(path))

    def test_manual_real_save_rechecks_loader_preserves_other_lines_and_recovers(self):
        path = self.user / ".config/aihub-studio/.env"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xef\xbb\xbf# keep\r\nOTHER=hello\r\nAIHUB_API_KEY=old\r\nAIHUB_API_KEY=duplicate\r\n")
        preview = self.manual()
        self.assertNotIn(self.marker.encode(), path.read_bytes())
        done = self.confirm(preview)
        self.assertEqual(done["phase"], "done")
        self.assertEqual(done["receipt"]["fields"]["AIHUB_API_KEY"]["source"], str(path))
        self.assertEqual(done["receipt"]["business_next_step"], "query_existing_result")
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf# keep\r\nOTHER=hello\r\n"))
        self.assertEqual(path.read_text(encoding="utf-8-sig").count("AIHUB_API_KEY="), 1)
        verify_private_permissions(path)
        self.assert_private_state()
        restored = ConfigurationUI(self.root / "runtime", self.options)
        self.assertEqual(restored.public()["phase"], "done")
        self.assertEqual(restored.task()["result"]["default_settings"]["phase"], "pending_check")
        with self.assertRaises(SetupError):
            self.confirm(preview)

    def test_stale_confirmations_restart_cancel_and_environment_cannot_write(self):
        preview = self.manual()
        target = Path(preview["preview"]["targets"][0]["path"])
        target.parent.mkdir(parents=True)
        target.write_text("UNRELATED=concurrent\n")
        with self.assertRaises(SetupError):
            self.confirm(preview)
        self.assertEqual(target.read_text(), "UNRELATED=concurrent\n")
        restored = ConfigurationUI(self.root / "runtime", self.options)
        self.assertFalse(restored.public()["key_present"])
        with self.assertRaises(SetupError):
            restored.action("save", {"id": preview["preview"]["id"]})
        self.ui.action("cancel", {})
        self.assertFalse(self.ui.public()["key_present"])
        with patch.dict(os.environ, {"AIHUB_API_KEY": "synthetic-environment"}):
            with self.assertRaisesRegex(SetupError, "repair_environment_at_injection_source"):
                self.manual()
        self.assert_private_state()

    def test_project_requires_ignore_and_repairs_effective_file_even_when_scope_global(self):
        RUN(["git", "init", "-q", str(self.project)], check=True)
        with self.assertRaisesRegex(SetupError, "target_not_ignored"):
            self.manual(scope="project")
        (self.project / ".gitignore").write_text(".env.local*\n")
        preview = self.manual(scope="project")
        done = self.confirm(preview)
        target = self.project / ".env.local"
        self.assertEqual(done["receipt"]["fields"]["AIHUB_API_KEY"]["source"], str(target))
        self.ui.action("reset", {})
        preview = self.manual(scope="global")
        self.assertEqual(preview["preview"]["targets"][0]["path"], str(target))
        self.assertFalse((self.user / ".config/aihub-studio/.env").exists())

    def test_partial_save_reconciles_without_replaying(self):
        preview = self.manual()
        from setup_core.ui_model import replace_content
        def interrupted(*args):
            replace_content(*args)
            raise OSError("synthetic failure after replacement")
        with patch("setup_core.ui_model.replace_content", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.confirm(preview)
        target = Path(preview["preview"]["targets"][0]["path"])
        original = target.read_bytes()
        self.assertEqual(self.ui.task()["phase"], "result_unknown")
        restored = ConfigurationUI(self.root / "runtime", self.options)
        self.assertEqual(restored.public()["phase"], "uncertain")
        with self.assertRaisesRegex(SetupError, "reconcile_before_retry"):
            restored.action("cancel", {})
        result = restored.action("reconcile", {})
        self.assertTrue(result["receipt"]["reconciled"][0]["matches_saved_content"])
        self.assertEqual(target.read_bytes(), original)
        self.assert_private_state()

    def test_both_consumers_no_global_and_caller_are_real(self):
        self.options["global_enabled"] = False
        self.options["services"]["tikin-social"]["caller"] = "tikin-douyin"
        ui = ConfigurationUI(self.root / "different", self.options)
        ui.action("choose", {"service": "tikin-social", "source": "manual"})
        preview = ui.action("manual", {"values": {"TIKIN_API_KEY": self.marker, "TIKIN_BASE_URL": "https://example.invalid"}, "scope": "project"})
        done = ui.action("save", {"id": preview["preview"]["id"]})
        self.assertEqual(done["phase"], "done")
        self.assertEqual(ui.task()["result"]["local"]["skill"], "tikin-douyin")
        self.assertFalse(ui.task()["result"]["local"]["global_enabled"])
        self.assertEqual(ui.task()["result"]["default_settings"]["phase"], "skipped")

    def test_real_launcher_restart_status_and_stop(self):
        prefix = [sys.executable, str(SKILL / "scripts/setup_ui.py")]
        context = ["--host", "codex", "--cwd", str(self.project)]
        def command(verb, *args):
            proc = RUN([*prefix, verb, *context, *args], capture_output=True, text=True, timeout=25)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            return json.loads(proc.stdout)
        started = command("start", "--aihub-root", str(MARKET / "aihub-studio"))
        session = started["session"]
        try:
            self.assertEqual(command("status", "--session", session)["status"], "running")
            again = command("start", "--session", session)
            self.assertEqual(again["url"], started["url"])
            command("stop", "--session", session)
            self.assertEqual(command("status", "--session", session)["status"], "stopped")
            reopened = command("start", "--session", session)
            self.assertNotEqual(reopened["url"], started["url"])
        finally:
            command("stop", "--session", session)

    def test_quotes_round_trip_and_expired_session(self):
        self.marker = "synthetic-single'quote\\double\"dollar$hash#"
        done = self.confirm(self.manual())
        from setup_core.ui_model import effective_values
        self.assertEqual(effective_values(self.ui.consumer().inspect(), self.ui.consumer().declaration)["AIHUB_API_KEY"], self.marker)
        self.assertEqual(done["receipt"]["local_status"], "ok")
        server = Server(self.root / "expiry", self.options)
        try:
            server.last_use -= 3601
            with self.assertRaisesRegex(SetupError, "session_expired"):
                server.lifetime(renew=True)
        finally:
            server.server_close()

    def test_http_origin_csrf_cookie_secret_absence_and_host_validation(self):
        server = Server(self.root / "http", self.options)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        def call(path, data=None, **headers):
            request = Request(server.origin + path, data=json.dumps(data).encode() if data is not None else None,
                headers={"Origin": server.origin, "Content-Type": "application/json", **headers})
            with opener.open(request, timeout=10) as response:
                return json.load(response), response.headers
        with self.assertRaises(HTTPError):
            call("/api/state")
        token, headers = call("/api/session", {"token": server.launch_token})
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        second = Server(self.root / "http-second", self.options)
        threading.Thread(target=second.serve_forever, daemon=True).start()
        self.addCleanup(second.server_close)
        self.addCleanup(second.shutdown)
        request = Request(second.origin + "/api/session", data=json.dumps({"token": second.launch_token}).encode(),
                          headers={"Origin": second.origin, "Content-Type": "application/json"})
        with opener.open(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
        # Both ports share the browser cookie jar. The first session must still
        # be authenticated after opening the second configuration page.
        self.assertEqual(call("/api/state")[0]["state"]["phase"], "manual")
        with opener.open(second.origin + "/api/state", timeout=10) as response:
            self.assertEqual(response.status, 200)
        with self.assertRaises(HTTPError):
            call("/api/action/manual", {"values": {"AIHUB_API_KEY": self.marker}, "scope": "global"})
        with self.assertRaises(HTTPError):
            call("/api/action/manual", {}, **{"Origin": "https://example.invalid", "X-Setup-CSRF": token["csrf"]})
        result, _ = call("/api/action/manual", {"values": {"AIHUB_API_KEY": self.marker}, "scope": "global"}, **{"X-Setup-CSRF": token["csrf"]})
        self.assertNotIn(self.marker, json.dumps(result))
        report, headers = call("/api/state")
        self.assertNotIn(self.marker, json.dumps(report))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        with self.assertRaises(HTTPError):
            call("/api/state", **{"Host": "attacker.invalid"})

    def fake_lark(self, argv, **kwargs):
        if argv[0] != "lark-cli":
            return RUN(argv, **kwargs)
        self.calls.append(argv)
        output = None
        if argv[1:3] == ["profile", "list"]:
            output = [{"name": "test", "appId": "cli_synthetic", "user": "Synthetic User", "tokenStatus": "valid"}]
        elif argv[1:3] == ["auth", "status"]:
            output = {"identity": "user", "identities": {"user": {"available": True, "status": "ready", "tokenStatus": "valid", "openId": self.open_id}}}
        elif argv[1:3] == ["base", "+url-resolve"]:
            output = {"data": {"base_token": "app_synthetic", "table_id": "tbl_synthetic"}}
        elif argv[1:3] == ["base", "+field-list"]:
            from setup_core.ui_book import load_core
            output = {"data": {"fields": [dict(row) for row in load_core().FIELD_SCHEMA]}}
        elif argv[1:3] == ["base", "+record-list"]:
            fields = [argv[i+1] for i, v in enumerate(argv[:-1]) if v == "--field-id"]
            record = {"id": "sec_synthetic", "name": "Synthetic credential", "service": "AIhub", "account": "test", "purpose": "test", "visible_to": None,
                      "secret": "AIHUB_API_KEY=" + self.book_key + "\nTIKIN_API_KEY=" + self.book_key}
            output = {"data": {"fields": fields, "data": [[record.get(k) for k in fields]], "record_id_list": ["rec_synthetic"], "has_more": False}}
        if output is None:
            raise AssertionError("unexpected remote call " + str(argv[:3]))
        return subprocess.CompletedProcess(argv, 0, json.dumps(output), "")

    def connected_book(self):
        self.calls = []
        self.open_id = "ou_synthetic"
        self.book_key = self.marker
        self.lark_patch = patch("setup_core.ui_book.subprocess.run", side_effect=self.fake_lark)
        self.lark_patch.start()
        self.addCleanup(self.lark_patch.stop)
        from setup_core.ui_book import Book
        self.prepare_patch = patch.object(Book, "prepare", return_value={"ready": True})
        self.prepare_patch.start()
        self.addCleanup(self.prepare_patch.stop)
        self.ui.action("choose", {"service": "aihub-studio", "source": "secret-book"})
        identity = self.ui.action("use-account", {"profile": "test"})["identity"]
        self.ui.action("confirm-identity", {"id": fingerprint(identity)})
        preview = self.ui.action("connect", {"url": "https://example.feishu.cn/base/app_synthetic?table=tbl_synthetic", "name": "Synthetic connection"})
        self.assertFalse((self.user / ".config/secret-book/.env").exists())
        self.ui.action("save-connection", {"id": preview["connection_preview"]["id"]})
        self.ui.action("select-record", {"id": "sec_synthetic"})
        self.ui.action("mapping", {"mapping": {"AIHUB_API_KEY": "AIHUB_API_KEY"}})

    def test_bundled_book_connection_mapping_real_save_and_no_remote_writes(self):
        self.connected_book()
        preview = self.ui.action("preview", {"scope": "global"})
        done = self.confirm(preview)
        self.assertEqual(done["phase"], "done")
        self.assertEqual(done["receipt"]["local_status"], "ok")
        self.assertTrue(self.calls)
        self.assertTrue(all(argv[2] in ("list", "status", "+url-resolve", "+record-list", "+field-list") for argv in self.calls))
        self.assertTrue(all("--profile" in argv for argv in self.calls if argv[1] != "profile"))
        self.assert_private_state()

    def test_book_rotation_or_identity_change_invalidates_confirmation(self):
        self.connected_book()
        preview = self.ui.action("preview", {"scope": "global"})
        self.book_key = "synthetic-rotated-value"
        with self.assertRaisesRegex(SetupError, "sources_changed"):
            self.confirm(preview)
        self.assertFalse((self.user / ".config/aihub-studio/.env").exists())
        self.open_id = "ou_different"
        with self.assertRaisesRegex(SetupError, "identity_changed"):
            self.ui.action("preview", {"scope": "global"})

    def test_rebind_original_connection_and_cancel_login(self):
        self.connected_book()
        cid = self.ui.state["book"]["connection"]
        self.open_id = "ou_new_user"
        self.ui.action("repair-connection", {"id": cid})
        identity = self.ui.action("use-account", {"profile": "test"})["identity"]
        preview = self.ui.action("confirm-identity", {"id": fingerprint(identity)})["connection_preview"]
        self.assertEqual(preview["previous_identity"]["feishu_user_open_id"], "ou_synthetic")
        self.ui.action("save-connection", {"id": preview["id"]})
        self.assertEqual(self.ui.book.connections()[0]["id"], cid)
        self.assertEqual(len(self.ui.book.connections()), 1)
        self.ui.book.login = {"code": "synthetic-device-code"}
        self.ui.action("cancel-login", {})
        self.assertIsNone(self.ui.book.login)

    def test_login_contract_and_restart_discards_pending_authorization(self):
        self.calls = []
        self.open_id = "ou_synthetic"
        from setup_core.ui_book import Book, READ_SCOPES
        def auth(argv, **kwargs):
            if argv[1:3] == ["auth", "login"]:
                self.calls.append(argv)
                if "--no-wait" in argv:
                    value = {"device_code": "synthetic-code", "verification_url": "https://accounts.feishu.cn/synthetic", "expires_in": 600}
                else:
                    value = {"ok": True}
                return subprocess.CompletedProcess(argv, 0, json.dumps(value), "")
            return self.fake_lark(argv, **kwargs)
        with patch("setup_core.ui_book.subprocess.run", side_effect=auth), patch.object(Book, "prepare", return_value={"ready": True}):
            self.ui.action("choose", {"service": "aihub-studio", "source": "secret-book"})
            pending = self.ui.action("start-login", {"profile": "test"})
            self.assertEqual(pending["phase"], "authorizing")
            self.assertNotIn("synthetic-code", json.dumps(pending))
            self.assertNotIn("synthetic-code", (self.root / "runtime/progress.json").read_text())
            restored = ConfigurationUI(self.root / "runtime", self.options)
            with self.assertRaisesRegex(SetupError, "login_expired"):
                restored.action("finish-login", {})
            result = self.ui.action("finish-login", {})
            self.assertEqual(result["identity"]["open_id"], self.open_id)
            login = next(call for call in self.calls if "--no-wait" in call)
            self.assertEqual(login[login.index("--scope")+1], READ_SCOPES)

    def test_artifact_upgrade_requires_new_preview_before_save(self):
        from setup_core.consumers import Consumer
        actual = Consumer.context
        revision = ["before"]
        def context(consumer, host):
            value = actual(consumer, host)
            value["version"] = revision[0]
            return value
        with patch.object(Consumer, "context", context):
            preview = self.manual()
            revision[0] = "after"
            with self.assertRaisesRegex(SetupError, "sources_changed"):
                self.confirm(preview)
            self.assertFalse((self.user / ".config/aihub-studio/.env").exists())
            revised = self.manual()
            self.assertEqual(self.ui.task()["context"]["version"], "after")
            self.assertNotEqual(revised["preview"]["id"], preview["preview"]["id"])

    def test_rate_limit_cooldown_survives_and_does_not_retry_early(self):
        from setup_core.ui_book import Book
        book = Book({})
        calls = []
        def limited(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 1, "", json.dumps({"ok": False, "error": {"type": "api", "subtype": "rate_limit", "retry_after": 600}}))
        with patch("setup_core.ui_book.subprocess.run", side_effect=limited):
            with book.operation(), self.assertRaisesRegex(SetupError, "rate_limited"):
                book.execute(["lark-cli", "profile", "list"])
            with book.operation(), self.assertRaisesRegex(SetupError, "rate_limited"):
                book.execute(["lark-cli", "profile", "list"])
        self.assertEqual(len(calls), 1)
        self.assertGreater(book.metadata["retry_at"], 0)


if __name__ == "__main__":
    unittest.main()
