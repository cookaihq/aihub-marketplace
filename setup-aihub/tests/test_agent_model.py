"""Synthetic credentials exercise the actual native writers and recovery states."""
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SKILL = Path(__file__).resolve().parents[1] / "skills/setup-agent-model"
sys.path.insert(0, str(SKILL / "scripts"))
from model_setup import catalog, clients, plans, workflow
from model_setup.common import SetupError


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="setup models 中文 ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.user = self.root / "user"
        self.user.mkdir()
        self.cwd = self.root / "project"
        self.cwd.mkdir()
        self.patchers = [patch("pathlib.Path.home", return_value=self.user),
                         patch.dict(os.environ, {"LOCALAPPDATA": str(self.user / "AppData/Local"),
                                                 "CODEX_HOME": str(self.user / ".codex"),
                                                 "HERMES_HOME": str(self.user / ".hermes"),
                                                 "CLAUDE_CONFIG_DIR": str(self.user / ".claude")}),
                         patch("model_setup.clients._policy_keys", return_value=[])]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        self.catalog = json.loads((SKILL / "data/models.json").read_bytes())
        self.manifest = catalog.manifest((SKILL / "data/models.json").read_bytes())

    def file(self, client, content=None):
        if client == "claude-desktop":
            p = clients.desktop_root() / "test.json"
        else:
            p = clients.files(client, self.cwd)[0]
        p.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            p.write_bytes(content.encode())
        return p

    def request(self, client="workbuddy", content=None, models=None, **options):
        path = self.file(client, content)
        protocol = next(iter(clients.PROTOCOLS[client])) if client != "hermes" else "openai-chat-completions"
        request = {"client": client, "config": str(path), "selector": "example", "new": content is None,
                   "name": "Example", "models": models or ["gpt-6.1-sol"], "protocol": protocol, "key_mode": "replace"}
        if client in ("codex", "chatgpt"):
            request["route_evidence"] = [{"model": "gpt-6.1-sol", "protocol": protocol, "source": "https://example.test/verified-route"}]
        if client == "claude-code":
            request.update(selector="$settings", models=models or ["claude-sonnet-5-5"])
        if client == "claude-desktop":
            request.update(selector="$configuration", models=models or ["claude-sonnet-5-5"])
        if content is not None:
            record = clients.entries(clients.load(path, client)[0], client)[0]
            request.update(selector=record["selector"], identity=record["identity"])
        request.update(options)
        return request

    def plan(self, request, models=None):
        return plans.build(request, self.cwd, models or self.catalog, self.manifest)

    def test_workbuddy_duplicate_ids_preserve_unselected_and_unknown_fields(self):
        old = [{"id": "gpt-6.1-sol", "name": "one", "apiKey": "synthetic-old", "unknown": [1, 2]},
               {"id": "gpt-6.1-sol", "name": "two", "apiKey": "synthetic-other"}]
        req = self.request(content=json.dumps(old), models=["gemini-4-argon"])
        plan = self.plan(req)
        output = workflow.write(plan, "synthetic-new")
        data = json.loads(Path(req["config"]).read_bytes())
        self.assertEqual(data[1], old[1])
        self.assertEqual(data[0]["unknown"], [1, 2])
        self.assertEqual(data[0]["apiKey"], "synthetic-new")
        self.assertNotIn("synthetic", json.dumps(plan) + json.dumps(output))

    def test_workbuddy_multiple_additions_do_not_choose_default_or_claim_capabilities(self):
        req = self.request(models=["gpt-6.1-sol", "gemini-4-argon"])
        workflow.write(self.plan(req), "synthetic-multiple")
        data = json.loads(Path(req["config"]).read_bytes())
        self.assertEqual(len(data), 2)
        self.assertNotIn("supportsToolCall", data[0])
        self.assertEqual({x["apiKey"] for x in data}, {"synthetic-multiple"})

    def test_yaml_roundtrip_retains_comments_unknown_fields_and_default(self):
        raw = '# retain comment\nmodel:\n  default: old\n  provider: other\nproviders:\n  example:\n    api: https://old.example/v1\n    api_key: synthetic-old\n    extra_body:\n      custom: yes\n'
        req = self.request("hermes", raw)
        workflow.write(self.plan(req), "synthetic-yaml")
        text = Path(req["config"]).read_text()
        self.assertIn("# retain comment", text)
        data = clients.load(req["config"], "hermes")[0]
        self.assertEqual(data["model"]["default"], "old")
        self.assertEqual(data["providers"]["example"]["extra_body"]["custom"], "yes")

    def test_codex_and_chatgpt_independent_identities_share_native_provider_field(self):
        for client in ("codex", "chatgpt"):
            with self.subTest(client=client):
                content = '# keep\nmodel = "gpt-6.1-sol"\n[model_providers.example]\nname="Example"\nexperimental_bearer_token="synthetic-old"\n'
                req = self.request(client, content)
                plan = self.plan(req)
                workflow.write(plan, "synthetic-toml")
                data = clients.load(req["config"], client)[0]
                self.assertEqual(data["model"], "gpt-6.1-sol")
                self.assertEqual(data["model_providers"]["example"]["experimental_bearer_token"], "synthetic-toml")
                self.assertIn("# keep", Path(req["config"]).read_text())
                self.assertEqual(plan["request"]["client"], client)

    def test_claude_code_multiple_aliases_preserve_model_and_allowlist(self):
        req = self.request("claude-code", '{"model":"old","availableModels":["keep"],"env":{"OTHER":"yes"}}',
                           models=["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"])
        workflow.write(self.plan(req), "synthetic-claude")
        data = json.loads(Path(req["config"]).read_bytes())
        self.assertEqual(data["model"], "old")
        self.assertEqual(data["availableModels"], ["keep"])
        self.assertEqual(data["env"]["ANTHROPIC_DEFAULT_FABLE_MODEL"], "claude-fable-5-1")
        self.assertEqual(data["env"]["ANTHROPIC_AUTH_TOKEN"], "synthetic-claude")

    def test_desktop_existing_native_entry_uses_distinct_gateway_file(self):
        # Synthetic service metadata tests the writer; production Claude-Max remains blocked.
        fixture = copy.deepcopy(self.catalog)
        fixture["models"][2]["key_groups"] = ["Official"]
        req = self.request("claude-desktop", '{"inferenceProvider":"gateway","inferenceModels":["existing"],"unknown":42}',
                           default_model="claude-sonnet-5-5")
        workflow.write(self.plan(req, fixture), "synthetic-desktop")
        data = json.loads(Path(req["config"]).read_bytes())
        self.assertEqual(data["inferenceModels"], ["claude-sonnet-5-5", "existing"])
        self.assertEqual(data["unknown"], 42)
        self.assertEqual(data["inferenceGatewayApiKey"], "synthetic-desktop")
        self.assertFalse((Path(req["config"]).parent / "_meta.json").exists())

    def test_catalog_does_not_infer_gpt_responses(self):
        req = self.request("codex")
        req.pop("route_evidence")
        with self.assertRaisesRegex(SetupError, "model_protocol_needs_evidence"):
            self.plan(req)

    def test_profile_model_change_requires_explicit_default_and_preserves_base(self):
        req = self.request("codex")
        with self.assertRaisesRegex(SetupError, "client_profile_model_choice_required"):
            self.plan(req)
        req.update(config=str(self.user / ".codex/example.config.toml"), default_model="gpt-6.1-sol")
        workflow.write(self.plan(req), "synthetic-profile")
        self.assertFalse((self.user / ".codex/config.toml").exists())
        self.assertEqual(clients.load(req["config"], "codex")[0]["model"], "gpt-6.1-sol")

    def test_inherited_provider_auth_and_project_model_override_block_repair(self):
        req = self.request("codex", default_model="gpt-6.1-sol")
        req["config"] = str(self.user / ".codex/example.config.toml")
        base = self.user / ".codex/config.toml"
        base.write_text('[model_providers.example]\nenv_key="OVERRIDING_KEY"\n')
        with self.assertRaisesRegex(SetupError, "higher_priority_source"):
            self.plan(req)
        base.write_text('model="unchanged"\n')
        project = self.cwd / ".codex/config.toml"
        project.parent.mkdir()
        project.write_text('model="project-model"\n')
        with self.assertRaisesRegex(SetupError, "higher_priority_source"):
            self.plan(req)

    def test_model_change_clears_old_unknown_capabilities_and_redacts_url_auth(self):
        req = self.request(content='[{"id":"old","apiKey":"synthetic-old","supportsToolCall":true,"supportsImages":true,"url":"https://example.test/?key=synthetic-private"}]')
        plan = self.plan(req)
        self.assertNotIn("synthetic", json.dumps(plan))
        self.assertEqual(len([c for c in plan["changes"] if c.get("operation") == "remove"]), 2)
        workflow.write(plan, "synthetic-new")
        data = json.loads(Path(req["config"]).read_bytes())[0]
        self.assertNotIn("supportsToolCall", data)
        self.assertTrue(plans.verify(plan)["saved"])

    def test_claude_higher_model_setting_blocks_lower_file_repair(self):
        req = self.request("claude-code")
        higher = self.cwd / ".claude/settings.local.json"
        higher.parent.mkdir()
        higher.write_text('{"model":"another-model"}')
        with self.assertRaisesRegex(SetupError, "higher_priority_source"):
            self.plan(req)

    def test_changed_hermes_display_name_cannot_activate_hidden_credential_pool(self):
        req = self.request("hermes", name="Display Name")
        (Path(req["config"]).parent / "auth.json").write_text('{"credential_pool":{"custom:display-name":[{"api_key":"synthetic-pool"}]}}')
        with self.assertRaisesRegex(SetupError, "planned_source_requires_repair"):
            self.plan(req)

    def test_hermes_explicit_activation_enables_only_selected_provider(self):
        req = self.request("hermes", 'providers:\n  example:\n    enabled: false\n  other:\n    enabled: false\n', default_model="gpt-6.1-sol")
        workflow.write(self.plan(req), "synthetic-enabled")
        data = clients.load(req["config"], "hermes")[0]
        self.assertTrue(data["providers"]["example"]["enabled"])
        self.assertFalse(data["providers"]["other"]["enabled"])

    def test_local_input_keeps_value_out_of_command_and_cancel_does_not_write(self):
        from model_setup.local_input import read_key
        with patch("model_setup.local_input.subprocess.run", return_value=subprocess.CompletedProcess([], 0, b"synthetic-input", b"")) as run:
            self.assertEqual(read_key("dialog", "C:/chosen/config.json"), "synthetic-input")
            self.assertNotIn("synthetic", repr(run.call_args))
        with patch("model_setup.local_input.subprocess.run", return_value=subprocess.CompletedProcess([], 3, b"", b"")):
            with self.assertRaisesRegex(SetupError, "local_input_cancelled"):
                read_key("dialog", "C:/chosen/config.json")

    def test_claude_max_is_restricted_by_service_policy_outside_catalog(self):
        req = self.request(models=["claude-sonnet-5-5"])
        with self.assertRaisesRegex(SetupError, "catalog_group_restricted"):
            self.plan(req)

    def test_concurrent_file_change_invalidates_plan_without_writing(self):
        req = self.request()
        plan = self.plan(req)
        path = Path(req["config"])
        path.write_text('[{"name":"concurrent"}]')
        with self.assertRaises(SetupError):
            workflow.write(plan, "synthetic-not-written")
        self.assertEqual(json.loads(path.read_text()), [{"name": "concurrent"}])

    def test_new_override_after_preview_invalidates_confirmation(self):
        req = self.request("hermes")
        plan = self.plan(req)
        auth = Path(req["config"]).parent / "auth.json"
        auth.write_text('{"credential_pool":{"example":[{"api_key":"synthetic-pool"}]}}')
        with self.assertRaisesRegex(SetupError, "higher_priority_source"):
            workflow.write(plan, "synthetic-not-written")

    def test_yaml_alias_and_duplicate_json_refused_without_corruption(self):
        for client, content in (("hermes", 'providers:\n  a: &x {api_key: synthetic}\n  b: *x\n'),
                                ("workbuddy", '[{"apiKey":"one","apiKey":"two"}]')):
            path = self.file(client, content)
            with self.assertRaises(SetupError):
                clients.load(path, client)
            self.assertEqual(path.read_text(), content)

    def test_exact_selection_required_even_for_duplicate_model_id(self):
        req = self.request(content='[{"id":"gpt-6.1-sol","apiKey":"synthetic"}]', identity="wrong")
        with self.assertRaisesRegex(SetupError, "inspect_and_select"):
            self.plan(req)

    def test_tasks_cross_turn_confirmation_cancellation_and_single_write(self):
        req = self.request()
        tasks = workflow.Tasks()
        current = workflow.context("chatgpt", self.cwd)
        state = tasks.start(self.plan(req), current, "manual")
        reopened = tasks.load(state["id"], current)
        with self.assertRaisesRegex(SetupError, "confirmation_required"):
            workflow.apply(tasks, reopened, "wrong", "synthetic")
        done = workflow.apply(tasks, reopened, reopened["confirmation_token"], "synthetic-confirmed")
        self.assertEqual(done["phase"], "saved")
        with self.assertRaisesRegex(SetupError, "readback_before_retry"):
            workflow.apply(tasks, done, "old", "synthetic")
        self.assertNotIn("synthetic", tasks.path(state["id"]).read_text(encoding="utf-8"))
        with self.assertRaisesRegex(SetupError, "task_context_changed"):
            tasks.load(state["id"], workflow.context("codex", self.cwd))

    def test_unknown_write_outcome_is_readback_not_replay(self):
        req = self.request()
        tasks = workflow.Tasks()
        state = tasks.start(self.plan(req), workflow.context("hermes", self.cwd), "manual")
        with patch("model_setup.workflow.write", side_effect=OSError("synthetic-hidden")):
            with self.assertRaises(OSError):
                workflow.apply(tasks, state, state["confirmation_token"], "synthetic")
        persisted = tasks.load(state["id"], state["context"])
        self.assertEqual(persisted["phase"], "result_unknown")
        self.assertEqual(workflow.recheck(tasks, persisted)["phase"], "needs_review")

    def test_secret_book_receipt_independently_reads_file_and_never_writes_twice(self):
        req = self.request()
        tasks = workflow.Tasks()
        state = tasks.start(self.plan(req), workflow.context("workbuddy", self.cwd), "secret-book")
        with self.assertRaisesRegex(SetupError, "secret_book_is_the_only_writer"):
            workflow.apply(tasks, state, state["confirmation_token"], "synthetic")
        receipt = workflow.write(state["plan"], "synthetic-secret-book")
        with patch("model_setup.workflow.write", side_effect=AssertionError("second writer")):
            checked = workflow.accept_secret_book(tasks, state, receipt, "task_synthetic")
        self.assertEqual(checked["phase"], "saved")

    def test_git_tracked_or_unignored_secret_target_is_refused(self):
        from model_setup.common import git_safe
        if subprocess.run(["git", "-C", str(SKILL), "rev-parse", "--is-inside-work-tree"], capture_output=True).returncode:
            self.skipTest("source archive has no Git checkout; verify Git safety in a checkout")
        with self.assertRaisesRegex(SetupError, "target_not_ignored"):
            git_safe(SKILL / "synthetic-unignored.json")
        git_safe(SKILL / ".venv/synthetic-ignored.json")

    def test_native_hermes_windows_root_and_profiles_are_enumerated(self):
        with patch.dict(os.environ, {"HERMES_HOME": "", "HERMES_DATA_DIR_SUFFIX": ""}):
            expected = self.user / ("AppData/Local/hermes" if sys.platform == "win32" else ".hermes")
            self.assertEqual(clients.hermes_root(), expected)
            profile = expected / "profiles/selected/config.yaml"
            profile.parent.mkdir(parents=True)
            profile.write_text("{}")
            with patch.dict(os.environ, {"HERMES_HOME": str(profile.parent)}):
                self.assertIn(expected / "config.yaml", clients.files("hermes", self.cwd))
                self.assertIn(profile, clients.files("hermes", self.cwd))


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.base = SKILL / "data"
        self.raw = (self.base / "models.json").read_bytes()
        self.data = json.loads(self.raw)

    def fetch(self, data):
        raw = (json.dumps(data) + "\n").encode()
        return lambda name: raw if name == "models.json" else json.dumps(catalog.manifest(raw)).encode()

    def test_catalog_integrity_survives_windows_git_checkout(self):
        market = SKILL.parents[2]
        if not (market / ".git").exists():
            self.skipTest("source archive has no Git checkout; verify checkout filters in a checkout")
        relative = (SKILL / "data/models.json").relative_to(market).as_posix()
        # Exercise Git's real checkout filter without creating a repository or branch.
        body = subprocess.run(["git", "-C", str(market), "-c", "core.autocrlf=true",
                               "cat-file", "--filters", ":" + relative], capture_output=True, check=True).stdout
        index = subprocess.run(["git", "-C", str(market), "show",
                                ":" + relative.replace("models.json", "models.manifest.json")],
                               capture_output=True, check=True).stdout
        self.assertEqual(catalog.manifest(body), json.loads(index))

    def test_update_validates_hash_and_same_version_does_not_download_body(self):
        newer = {**self.data, "catalog_version": 2}
        first = catalog.load(cache=self.cache, fetch=self.fetch(newer))
        self.assertEqual(first["refresh_status"], "refreshed")
        calls = []
        def index_only(name):
            calls.append(name)
            self.assertEqual(name, "models.manifest.json")
            return self.fetch(newer)(name)
        second = catalog.load(cache=self.cache, fetch=index_only)
        self.assertEqual(second["source"], "cache")
        self.assertEqual(len(calls), 1)

    def test_network_failure_corrupt_cache_and_unknown_schema_fall_back(self):
        for bad in (OSError("network"), SetupError("catalog_network_unavailable")):
            with self.subTest(bad=type(bad).__name__):
                result = catalog.load(cache=self.cache, fetch=lambda _: (_ for _ in ()).throw(bad))
                self.assertEqual(result["source"], "packaged")
                self.assertEqual(result["refresh_status"], "fallback")
        index = {"schema_version": 9, "catalog_version": 2, "sha256": "0" * 64}
        result = catalog.load(cache=self.cache, fetch=lambda _: json.dumps(index).encode())
        self.assertEqual(result["refresh_status"], "fallback")

    def test_same_version_mutation_rejected_and_newer_packaged_catalog_wins(self):
        mutated = copy.deepcopy(self.data)
        mutated["models"][0]["description"] = "changed"
        result = catalog.load(cache=self.cache, fetch=self.fetch(mutated))
        self.assertEqual(result["reason"], "catalog_same_version_changed")
        self.assertFalse((self.cache / "models.json").exists())

    def test_publication_race_rechecks_index_once_and_never_accepts_wrong_hash(self):
        newer = {**self.data, "catalog_version": 2}
        fetched = self.fetch(newer)
        calls = []
        def race(name):
            calls.append(name)
            if len(calls) == 1:
                index = json.loads(fetched(name))
                index["sha256"] = "0" * 64
                return json.dumps(index).encode()
            return fetched(name)
        result = catalog.load(cache=self.cache, fetch=race)
        self.assertEqual(result["refresh_status"], "refreshed")
        self.assertEqual(calls, ["models.manifest.json", "models.json", "models.manifest.json"])

    def test_clients_and_invented_capability_types_are_rejected(self):
        for mutate in (lambda m: m.update(clients=["codex"]), lambda m: m["routes"][0]["capabilities"].update(tool_calling="yes")):
            data = copy.deepcopy(self.data)
            mutate(data["models"][0])
            with self.assertRaises(SetupError):
                catalog.validate(data)

    def test_interrupted_publication_falls_back_to_last_valid_newer_cache(self):
        catalog.load(cache=self.cache, fetch=self.fetch({**self.data, "catalog_version": 2}))
        atomic = catalog._atomic
        def interrupted(path, raw):
            if path == self.cache / "models.manifest.json":
                raise OSError("interrupted")
            return atomic(path, raw)
        with patch("model_setup.catalog._atomic", side_effect=interrupted):
            catalog.load(cache=self.cache, fetch=self.fetch({**self.data, "catalog_version": 3}))
        recovered = catalog.load(refresh=False, cache=self.cache)
        self.assertEqual(recovered["manifest"]["catalog_version"], 2)

    def test_http_failure_classification_and_retry_after_budget(self):
        for error, calls in (({"error":"catalog_http_error","status":403,"transient":False}, 1),
                             ({"error":"catalog_http_error","status":429,"transient":True,"retry_after":"120"}, 1),
                             ({"error":"catalog_network_error","transient":True}, 3)):
            with patch("model_setup.catalog.subprocess.run", return_value=subprocess.CompletedProcess([], 0, json.dumps(error).encode(), b"")) as run, patch("model_setup.catalog.time.sleep"):
                with self.assertRaises(SetupError):
                    catalog.PublicFetch()("models.manifest.json")
                self.assertEqual(run.call_count, calls)

    def test_killable_worker_bounds_slow_response_by_wall_clock(self):
        actual_run = subprocess.run
        def slow_worker(command, **kwargs):
            return actual_run([sys.executable, "-c", "import time; time.sleep(5)"], **kwargs)
        start = time.monotonic()
        with patch("model_setup.catalog.REFRESH_BUDGET", .4), patch("model_setup.catalog.REQUEST_TIMEOUT", .2), patch("model_setup.catalog.subprocess.run", side_effect=slow_worker):
            with self.assertRaisesRegex(SetupError, "catalog_network_unavailable"):
                catalog.PublicFetch()("models.json")
        self.assertLess(time.monotonic() - start, 2)


if __name__ == "__main__":
    unittest.main()
