import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "tikin-setup"
SCRIPT = SKILL_DIR / "scripts" / "tikin-config"
VENV_DIR = SKILL_DIR / ".venv"
VENV_PY = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

BUILD_HINT = f"uv sync --no-dev --project {SKILL_DIR}"


def _venv_is_valid():
    # Mirrors the bootstrap check inside tikin-config: bin/python alone is not
    # enough, an interrupted sync leaves an interpreter without a real venv.
    return VENV_PY.exists() and (VENV_DIR / "pyvenv.cfg").exists()


def _resolve_interpreter():
    """Pick the interpreter the tests launch tikin-config with.

    Never `sys.executable`: that is whatever ran the test runner, so the script's
    own bootstrap would fire, shell out to `uv`, and on a cold checkout do a
    network `uv sync` in the middle of the test — turning an offline unit test
    into an online one, and failing outright on a machine without uv.

    Order: use the already-built .venv; else build it once if uv is present;
    else skip with the exact command to run.
    """
    if _venv_is_valid():
        return str(VENV_PY), None

    if shutil.which("uv") is None:
        return None, (
            f"tikin-setup runtime not built and uv is not installed.\n"
            f"Install uv (https://docs.astral.sh/uv/) then run: {BUILD_HINT}"
        )

    # First build needs network; every later run is offline.
    result = subprocess.run(
        ["uv", "sync", "--no-dev", "--project", str(SKILL_DIR)],
        capture_output=True,
        text=True,
        timeout=600,  # every network call needs a budget (ADR 0006)
    )
    if result.returncode != 0 or not _venv_is_valid():
        return None, (
            f"could not build the tikin-setup runtime (run manually: {BUILD_HINT}):\n"
            f"{result.stdout}{result.stderr}"
        )
    return str(VENV_PY), None


INTERPRETER, SKIP_REASON = _resolve_interpreter()

if SKIP_REASON:
    # unittest only shows a skip reason at -v, so the default run would print a
    # row of "s" and no way to act on it. Say it once on stderr instead.
    sys.stderr.write(
        "\n[tests] SKIPPING TikinConfigTests -- " + SKIP_REASON + "\n\n"
    )


@unittest.skipIf(INTERPRETER is None, SKIP_REASON or "tikin-setup runtime unavailable")
class TikinConfigTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.user_home = Path(self.tempdir.name) / "home"
        self.config_home = self.user_home / ".config"
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.user_home)
        self.env["USERPROFILE"] = str(self.user_home)
        self.env["PYTHONUTF8"] = "1"
        self.env["XDG_CONFIG_HOME"] = str(Path(self.tempdir.name) / "ignored-xdg")
        self.env.pop("TIKIN_API_KEY", None)
        self.env.pop("TIKIN_BASE_URL", None)

    def run_config(self, *args, input_text=None, env=None, check=True):
        result = subprocess.run(
            [INTERPRETER, str(SCRIPT), *args],
            input=input_text,
            text=True,
            capture_output=True,
            cwd=self.tempdir.name,
            env=env or self.env,
            check=False,
        )
        if check and result.returncode != 0:
            self.fail(
                f"command failed ({result.returncode}): {result.stderr or result.stdout}"
            )
        return result

    def test_each_skill_reads_its_own_file_before_shared_and_home_values(self):
        project = Path(self.tempdir.name)
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        (config_dir / ".env").write_text("TIKIN_API_KEY=home-value\n")
        (project / ".env.local").write_text("TIKIN_API_KEY=local-value\n")
        (project / ".env").write_text("TIKIN_API_KEY=shared-value\n")
        names = [path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")]
        for name in names:
            (project / (".env." + name)).write_text("TIKIN_API_KEY=for-" + name + "\n")
        for name in names:
            with self.subTest(skill=name):
                result = self.run_config("--skill", name, "status")
                self.assertEqual(json.loads(result.stdout)["key_source"], str(project / (".env." + name)))
                child = self.run_config(
                    "--skill", name, "run", "--", INTERPRETER, "-c",
                    "import os,sys; sys.exit(os.environ['TIKIN_API_KEY'] != sys.argv[1])",
                    "for-" + name,
                )
                self.assertEqual(child.stdout, "")
                self.assertNotIn("for-" + name, child.stderr)

    def test_process_wins_and_empty_layers_fall_through_without_shell_expansion(self):
        project = Path(self.tempdir.name)
        skill_file = project / ".env.tikin-douyin"
        skill_file.write_text("TIKIN_API_KEY=skill-value\n")
        local = project / ".env.local"
        local.write_text("TIKIN_API_KEY=local-value\n")
        (project / ".env").write_text("TIKIN_API_KEY=shared-value\n")
        env = self.env.copy()
        env["TIKIN_API_KEY"] = "process-value"
        self.assertEqual(
            json.loads(self.run_config("--skill", "tikin-douyin", "status", env=env).stdout)["key_source"],
            "environment",
        )
        env["TIKIN_API_KEY"] = ""
        skill_file.write_text('TIKIN_API_KEY=first\nTIKIN_API_KEY=""\n')
        self.assertEqual(
            json.loads(self.run_config("--skill", "tikin-douyin", "status", env=env).stdout)["key_source"],
            str(project / ".env.local"),
        )
        local.write_text("TIKIN_API_KEY=\n")
        self.assertEqual(
            json.loads(self.run_config("--skill", "tikin-douyin", "status", env=env).stdout)["key_source"],
            str(project / ".env"),
        )
        literal = "${MISSING}/$(touch should-not-exist)`touch neither`"
        skill_file.write_text('TIKIN_API_KEY = "' + literal + '"\nUNSUPPORTED=ignored\n')
        child = self.run_config(
            "--skill", "tikin-douyin", "run", "--", INTERPRETER, "-c",
            "import os,sys; assert os.environ['TIKIN_API_KEY'] == sys.argv[1]; "
            "assert 'UNSUPPORTED' not in os.environ", literal,
        )
        self.assertEqual(child.stdout, "")
        self.assertFalse((project / "should-not-exist").exists())
        self.assertFalse((project / "neither").exists())

    def test_project_lookup_does_not_read_parent_or_other_skill_file(self):
        project = Path(self.tempdir.name)
        (project / ".env.tikin-tiktok").write_text("TIKIN_API_KEY=other-skill\n")
        result = self.run_config("--skill", "tikin-douyin", "status")
        self.assertEqual(json.loads(result.stdout)["key_source"], "missing")
        for name in (".env.tikin-douyin", ".env.local", ".env"):
            (project / name).write_text("TIKIN_API_KEY=parent-value\n")
        child_dir = project / "child"
        child_dir.mkdir()
        result = subprocess.run(
            [INTERPRETER, str(SCRIPT), "--skill", "tikin-douyin", "status"],
            cwd=child_dir, env=self.env, text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["key_source"], "missing")

    def test_run_uses_independent_values_and_does_not_initialize_home(self):
        project = Path(self.tempdir.name)
        (project / ".env.tikin-setup").write_text("TIKIN_API_KEY=project-value\n")
        (project / ".env.local").write_text("TIKIN_BASE_URL=https://selected.example\n")
        result = self.run_config(
            "run", "--", INTERPRETER, "-c",
            "import os; assert os.environ['TIKIN_API_KEY'] == 'project-value'; "
            "assert os.environ['TIKIN_BASE_URL'] == 'https://selected.example'",
        )
        self.assertEqual(result.stdout, "")
        self.assertFalse(self.config_home.exists())

    def test_run_rejects_missing_key_and_invalid_skill_before_child_execution(self):
        for args in (("run", "--", INTERPRETER, "-c", "raise AssertionError('executed')"),
                     ("--skill", "../../other", "run", "--", INTERPRETER, "-c", "raise AssertionError('executed')")):
            result = self.run_config(*args, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("executed", result.stderr)

    def test_set_key_preserves_literal_quotes_and_whitespace(self):
        value = '  quoted\'"key  '
        self.run_config("set-key", input_text=value)
        result = self.run_config(
            "run", "--", INTERPRETER, "-c",
            "import os,sys; assert os.environ['TIKIN_API_KEY'] == sys.argv[1]", value,
        )
        self.assertEqual(result.stdout, "")
        self.assertNotIn(value, result.stderr)

    def test_plugin_skill_and_runtime_versions_are_consistent(self):
        version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
        for directory in (".claude-plugin", ".codex-plugin", ".codebuddy-plugin"):
            manifest = json.loads((ROOT / directory / "plugin.json").read_text())
            self.assertEqual(manifest["version"], version)
            self.assertEqual(manifest["name"], "tikin-social")
        for skill in (ROOT / "skills").glob("*/SKILL.md"):
            text = skill.read_text()
            self.assertEqual(re.search(r'^metadata:\n  version: "([^"]+)"$', text, re.M).group(1), version)
            self.assertIn("v" + version + "｜", text)
            if (skill.parent / "pyproject.toml").exists():
                for filename in ("pyproject.toml", "uv.lock"):
                    self.assertIn('version = "' + version + '"', (skill.parent / filename).read_text())

    def test_init_creates_default_settings_with_private_permissions(self):
        self.run_config("init")

        settings_path = self.config_home / "tikin-social" / "settings.json"
        self.assertEqual(
            json.loads(settings_path.read_text()),
            {"routing": {"default": "auto", "platforms": {}}},
        )
        self.assertEqual(stat.S_IMODE(settings_path.stat().st_mode), 0o600)

    def test_empty_xdg_config_home_uses_home_default(self):
        process_env = self.env.copy()
        home = Path(self.tempdir.name) / "home"
        process_env["HOME"] = str(home)
        process_env["USERPROFILE"] = str(home)
        process_env["XDG_CONFIG_HOME"] = ""

        self.run_config("init", env=process_env)

        self.assertTrue((home / ".config" / "tikin-social" / "settings.json").is_file())
        self.assertFalse((Path(self.tempdir.name) / "tikin-social").exists())

    def test_init_does_not_read_or_migrate_legacy_alias(self):
        legacy = self.config_home / "tikin"
        legacy.mkdir(parents=True)
        legacy_env = legacy / ".env"
        legacy_env.write_text("TIKIN_API_KEY=legacy-secret\n")
        legacy_settings = legacy / "settings.json"
        legacy_settings.write_text('{"routing":{"default":"confirm","platforms":{}}}')
        result = self.run_config("init")
        self.assertEqual(legacy_env.read_text(), "TIKIN_API_KEY=legacy-secret\n")
        self.assertFalse((self.config_home / "tikin-social" / ".env").exists())
        self.assertEqual(self.run_config("get-policy", "youtube").stdout.strip(), "auto")
        self.assertNotIn("legacy-secret", result.stdout + result.stderr)

    def test_set_key_writes_private_env_and_status_never_echoes_secrets(self):
        secret = "secret-from-stdin"
        self.run_config("init")

        set_result = self.run_config("set-key", input_text=f"{secret}\n")
        status_result = self.run_config("status")

        env_path = self.config_home / "tikin-social" / ".env"
        self.assertIn("TIKIN_API_KEY=secret-from-stdin", env_path.read_text())
        self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)
        report = json.loads(status_result.stdout)
        self.assertTrue(report["key_configured"])
        self.assertEqual(report["key_source"], str(env_path))
        self.assertEqual(report["sources"]["TIKIN_API_KEY"], str(env_path))
        self.assertEqual(report["sources"]["TIKIN_BASE_URL"], "built-in default")
        self.assertEqual(report["settings"], {"routing": {"default": "auto", "platforms": {}}})
        for output in (set_result.stdout, set_result.stderr, status_result.stdout):
            self.assertNotIn(secret, output)

    def test_status_only_returns_known_non_secret_settings(self):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        settings_path = config_dir / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "routing": {"default": "auto", "platforms": {}},
                    "future_secret": "do-not-print-this",
                }
            )
        )

        result = self.run_config("status")

        self.assertNotIn("do-not-print-this", result.stdout)
        self.assertEqual(
            json.loads(result.stdout)["settings"],
            {"routing": {"default": "auto", "platforms": {}}},
        )

    def test_environment_key_wins_and_set_key_preserves_other_env_values(self):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        env_path = config_dir / ".env"
        env_path.write_text(
            "TIKIN_BASE_URL=https://private.example\nTIKIN_API_KEY=file-secret\n"
        )
        process_env = self.env.copy()
        process_env["TIKIN_API_KEY"] = "process-secret"

        status_result = self.run_config("status", env=process_env)
        self.run_config("set-key", input_text="replacement-secret\n")

        self.assertEqual(json.loads(status_result.stdout)["key_source"], "environment")
        self.assertNotIn("process-secret", status_result.stdout)
        self.assertNotIn("file-secret", status_result.stdout)
        self.assertIn("TIKIN_BASE_URL=https://private.example", env_path.read_text())
        self.assertIn("TIKIN_API_KEY=replacement-secret", env_path.read_text())

    def test_init_repairs_existing_env_file_permissions_without_echoing_it(self):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        env_path = config_dir / ".env"
        secret = "existing-secret"
        env_path.write_text(f"TIKIN_API_KEY={secret}\n")
        env_path.chmod(0o644)

        result = self.run_config("init")

        self.assertEqual(stat.S_IMODE(env_path.stat().st_mode), 0o600)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_init_does_not_touch_legacy_unhidden_env(self):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        legacy_path = config_dir / "env"
        env_path = config_dir / ".env"
        legacy_path.write_text("TIKIN_API_KEY=legacy-secret\n")
        env_path.write_text("TIKIN_API_KEY=current-secret\n")
        legacy_path.chmod(0o644)

        self.run_config("init")

        self.assertEqual(env_path.read_text(), "TIKIN_API_KEY=current-secret\n")
        self.assertEqual(stat.S_IMODE(legacy_path.stat().st_mode), 0o644)

    def test_routing_supports_global_defaults_and_platform_overrides(self):
        self.run_config("init")
        self.assertEqual(self.run_config("get-policy", "xiaohongshu").stdout.strip(), "auto")

        self.run_config(
            "set-routing",
            "--default",
            "confirm",
            "--platform",
            "xiaohongshu=auto",
            "--platform",
            "instagram=auto",
        )

        self.assertEqual(self.run_config("get-policy", "xiaohongshu").stdout.strip(), "auto")
        self.assertEqual(self.run_config("get-policy", "instagram").stdout.strip(), "auto")
        self.assertEqual(self.run_config("get-policy", "youtube").stdout.strip(), "confirm")
        settings_path = self.config_home / "tikin-social" / "settings.json"
        self.assertEqual(
            json.loads(settings_path.read_text()),
            {
                "routing": {
                    "default": "confirm",
                    "platforms": {"instagram": "auto", "xiaohongshu": "auto"},
                }
            },
        )

    def test_init_refuses_current_env_symlink(self):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        outside = Path(self.tempdir.name) / "outside-secret"
        outside.write_text("TIKIN_API_KEY=outside-secret\n")
        (config_dir / ".env").symlink_to(outside)

        result = self.run_config("init", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((config_dir / ".env").is_symlink())
        self.assertEqual(outside.read_text(), "TIKIN_API_KEY=outside-secret\n")
        self.assertNotIn("outside-secret", result.stdout)
        self.assertNotIn("outside-secret", result.stderr)

    def write_config(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def global_files(self, skill="tikin-douyin"):
        root = self.config_home / "tikin-social"
        return [root / skill / ".env.local", root / skill / ".env",
                root / (".env." + skill), root / ".env.local", root / ".env",
                self.config_home / skill / ".env"]

    def test_all_global_layers_precede_the_current_skill_fallback(self):
        files = self.global_files()
        for index, path in enumerate(files):
            self.write_config(path, f"TIKIN_API_KEY=layer-{index}\n")
        for index, path in enumerate(files):
            with self.subTest(layer=path):
                report = json.loads(self.run_config("--skill", "tikin-douyin", "config-check").stdout)
                self.assertEqual(report["fields"]["TIKIN_API_KEY"]["source"], str(path))
                child = self.run_config("--skill", "tikin-douyin", "run", "--", INTERPRETER, "-c",
                    "import os,sys; assert os.environ['TIKIN_API_KEY'] == sys.argv[1]", f"layer-{index}")
                self.assertEqual(child.stdout, "")
                path.write_text('TIKIN_API_KEY=""\n')

    def test_plugin_partial_values_and_empty_directory_fall_back_per_field(self):
        root = self.config_home / "tikin-social"
        (root / "tikin-douyin").mkdir(parents=True)
        self.write_config(root / ".env", "TIKIN_API_KEY=\nTIKIN_BASE_URL=https://plugin.example\n")
        fallback = self.config_home / "tikin-douyin" / ".env"
        self.write_config(fallback, "TIKIN_API_KEY=skill-secret\nTIKIN_BASE_URL=https://ignored.example\n")
        report = json.loads(self.run_config("--skill", "tikin-douyin", "config-check").stdout)
        self.assertEqual(report["fields"]["TIKIN_API_KEY"]["source"], str(fallback))
        self.assertEqual(report["fields"]["TIKIN_BASE_URL"]["source"], str(root / ".env"))
        self.assertNotIn("skill-secret", json.dumps(report))

    def test_all_17_skills_use_plugin_shared_configuration(self):
        shared = self.config_home / "tikin-social" / ".env"
        self.write_config(shared, "TIKIN_API_KEY=shared-secret\n")
        for path in (ROOT / "skills").glob("*/SKILL.md"):
            with self.subTest(skill=path.parent.name):
                report = json.loads(self.run_config("--skill", path.parent.name, "status").stdout)
                self.assertEqual(report["key_source"], str(shared))

    def test_global_files_are_isolated_from_other_skills_and_legacy_aliases(self):
        for path in (self.config_home / "tikin" / ".env",
                     self.config_home / "tikin-plugin" / ".env",
                     self.config_home / "tikin-social" / ".env.tikin-tiktok",
                     self.config_home / "tikin-social" / "tikin-tiktok" / ".env",
                     self.config_home / "tikin-tiktok" / ".env",
                     self.config_home / "tikin-douyin" / ".env.local",
                     Path(self.env["XDG_CONFIG_HOME"]) / "tikin-social" / ".env"):
            self.write_config(path, "TIKIN_API_KEY=must-not-be-read\n")
        report = json.loads(self.run_config("--skill", "tikin-douyin", "status").stdout)
        self.assertFalse(report["key_configured"])
        result = self.run_config("--skill", "tikin-not-a-real-skill", "status", check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_no_global_option_skips_both_kinds_of_config_and_saved_routing(self):
        for path in self.global_files():
            self.write_config(path, "TIKIN_API_KEY=global-secret\n")
        self.write_config(self.config_home / "tikin-social" / "settings.json",
                          '{"routing":{"default":"confirm","platforms":{}}}')
        args = ("--skill", "tikin-douyin", "--no-global-config")
        report = json.loads(self.run_config(*args, "status").stdout)
        self.assertFalse(report["key_configured"])
        self.assertFalse(report["global_enabled"])
        self.assertEqual(report["settings"]["routing"]["default"], "auto")
        env = self.env.copy()
        env["TIKIN_API_KEY"] = "explicit-secret"
        self.assertEqual(json.loads(self.run_config(*args, "status", env=env).stdout)["key_source"], "environment")
        self.assertEqual(self.run_config(*args, "get-policy", "youtube").stdout.strip(), "auto")
        compatible = json.loads(self.run_config("--skill", "tikin-douyin", "--use-global-config", "status").stdout)
        self.assertTrue(compatible["key_configured"])
        rejected = self.run_config("--use-global-config", "--no-global-config", "status", check=False)
        self.assertNotEqual(rejected.returncode, 0)

    def test_no_caller_reads_only_shared_files(self):
        self.write_config(self.config_home / "tikin-social" / ".env.tikin-setup", "TIKIN_API_KEY=not-selected\n")
        self.write_config(self.config_home / "tikin-setup" / ".env", "TIKIN_API_KEY=not-selected\n")
        self.write_config(Path(self.tempdir.name) / ".env.tikin-setup", "TIKIN_API_KEY=not-selected\n")
        result = self.run_config("--plugin-only", "config-check", check=False)
        self.assertEqual(result.returncode, 3)
        report = json.loads(result.stdout)
        self.assertIsNone(report["skill"])
        self.assertEqual(len(report["layers"]), 4)
        shared = self.config_home / "tikin-social" / ".env"
        self.write_config(shared, "TIKIN_API_KEY=shared-secret\n")
        self.assertEqual(json.loads(self.run_config("--plugin-only", "status").stdout)["key_source"], str(shared))

    def test_each_unreadable_global_file_is_reported_and_blocks_commands(self):
        for path in self.global_files():
            with self.subTest(path=path):
                path.mkdir(parents=True)
                env = self.env.copy()
                env["TIKIN_API_KEY"] = "valid-test-key"
                result = self.run_config("--skill", "tikin-douyin", "config-check", env=env, check=False)
                self.assertEqual(result.returncode, 3)
                report = json.loads(result.stdout)
                self.assertIn({"source": str(path), "reason": "unreadable"}, report["problems"])
                result = self.run_config("--skill", "tikin-douyin", "run", "--", INTERPRETER,
                                         "-c", "raise AssertionError('executed')", env=env, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unreadable", result.stderr)
                self.assertNotIn("executed", result.stderr)
                path.rmdir()

    def test_inspection_is_secret_free_reports_sources_and_never_writes_files(self):
        result = self.run_config("config-check", check=False)
        self.assertEqual(result.returncode, 3)
        self.assertFalse(self.user_home.exists())
        self.run_config("status")
        self.run_config("get-policy", "youtube")
        self.assertFalse(self.user_home.exists())
        env = self.env.copy()
        env["TIKIN_API_KEY"] = "source-report-secret"
        env["TIKIN_BASE_URL"] = "https://user:password@example.invalid"
        result = self.run_config("config-check", env=env, check=False)
        self.assertEqual(result.returncode, 3)
        for value in ("source-report-secret", "password", env["TIKIN_BASE_URL"]):
            self.assertNotIn(value, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "secret-book.config-inspection/v1")
        self.assertEqual(report["consumer"], {"kind": "plugin", "name": "tikin-social"})
        self.assertEqual(report["fields"]["TIKIN_BASE_URL"]["problem"], "invalid_url")
        self.assertEqual(len(report["environment"]["TIKIN_API_KEY"]), 64)

    def test_distribution_and_skills_only_entrypoints_preserve_identity_and_loading(self):
        for mode in ("plugin", "skills-only"):
            with self.subTest(mode=mode):
                install = Path(self.tempdir.name) / ("installed " + mode)
                setup = install / "skills" / "tikin-setup"
                shutil.copytree(SKILL_DIR, setup, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
                if mode == "plugin":
                    shutil.copytree(ROOT / ".claude-plugin", install / ".claude-plugin")
                env = self.env.copy()
                env["UV_PROJECT_ENVIRONMENT"] = str(VENV_DIR)
                shared = self.config_home / "tikin-social" / ".env"
                self.write_config(shared, "TIKIN_API_KEY=installed-secret\n")
                result = subprocess.run([INTERPRETER, str(setup / "scripts" / "tikin-config"),
                                         "--skill", "tikin-douyin", "config-check"],
                                        cwd=self.tempdir.name, env=env, text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["fields"]["TIKIN_API_KEY"]["source"], str(shared))
                declaration = json.loads((setup / "references" / "credentials.json").read_text())
                self.assertEqual(declaration["consumer"]["name"], "tikin-social")
                self.assertEqual(set(declaration["consumer"]["skills"]),
                                 {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")})
                self.assertNotIn("installed-secret", result.stdout + result.stderr)

    def test_mismatched_manifest_blocks_every_command_before_side_effects(self):
        commands = [
            ("init",), ("set-key",), ("set-routing", "--default", "confirm"),
            ("get-policy", "youtube"), ("status",), ("config-check",), ("validate",),
            ("run", "--", INTERPRETER, "-c", "raise AssertionError('child-executed')"),
        ]
        for directory in (".claude-plugin", ".codex-plugin", ".codebuddy-plugin"):
            install = Path(self.tempdir.name) / ("wrong identity " + directory)
            setup = install / "skills" / "tikin-setup"
            shutil.copytree(SKILL_DIR, setup, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
            manifest = install / directory / "plugin.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps({"name": "tikin-plugin", "version": "1.0.0"}))
            env = self.env.copy()
            env["UV_PROJECT_ENVIRONMENT"] = str(VENV_DIR)
            for command in commands:
                with self.subTest(manifest=directory, command=command[0]):
                    result = subprocess.run([INTERPRETER, str(setup / "scripts" / "tikin-config"), *command],
                                            cwd=self.tempdir.name, env=env, input="fixture-input-secret\n",
                                            text=True, capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Plugin manifest identity disagrees", result.stderr)
                    self.assertNotIn("fixture-input-secret", result.stdout + result.stderr)
                    self.assertNotIn("child-executed", result.stdout + result.stderr)
                    self.assertFalse(self.user_home.exists(), "rejected commands must not initialize configuration")

    def start_stub_tikin(self, responder):
        """Serve /api/usage/token/ locally. No request ever leaves the machine.

        `responder` receives the 1-based request number and returns
        (status, extra_headers, body_bytes).
        """
        calls = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append(self.path)
                status, extra_headers, body = responder(len(calls))
                self.send_response(status)
                for name, value in (extra_headers or {}).items():
                    self.send_header(name, value)
                if body:
                    self.send_header("Content-Type", "application/json")
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def log_message(self, _format, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, calls

    def write_env_pointing_at(self, server, secret):
        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / ".env").write_text(
            f"TIKIN_API_KEY={secret}\n"
            f"TIKIN_BASE_URL=http://127.0.0.1:{server.server_port}\n"
        )

    def test_validate_checks_the_key_without_echoing_it(self):
        secret = "validation-secret"

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if (
                    self.path == "/api/usage/token/"
                    and self.headers.get("Authorization") == f"Bearer {secret}"
                ):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                else:
                    self.send_response(401)
                    self.end_headers()

            def log_message(self, _format, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True)
        (config_dir / ".env").write_text(
            "TIKIN_API_KEY=wrong-home-key\n"
            f"TIKIN_BASE_URL=http://127.0.0.1:{server.server_port}\n"
        )
        (Path(self.tempdir.name) / ".env.tikin-douyin").write_text(
            f"TIKIN_API_KEY={secret}\n"
        )

        result = self.run_config("--skill", "tikin-douyin", "validate")

        self.assertEqual(result.stdout.strip(), "valid")
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_validate_retries_a_transient_server_error_then_succeeds(self):
        secret = "transient-secret"

        def responder(call_number):
            if call_number == 1:
                return (503, None, None)
            return (200, None, b'{"ok":true}')

        server, calls = self.start_stub_tikin(responder)
        self.write_env_pointing_at(server, secret)

        result = self.run_config("validate")

        self.assertEqual(result.stdout.strip(), "valid")
        self.assertEqual(len(calls), 2)
        self.assertIn("attempt 1/3", result.stderr)
        self.assertIn("HTTP 503", result.stderr)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_validate_honors_retry_after_and_stops_after_three_attempts(self):
        secret = "rate-limited-secret"

        def responder(_call_number):
            return (429, {"Retry-After": "0"}, None)

        server, calls = self.start_stub_tikin(responder)
        self.write_env_pointing_at(server, secret)

        result = self.run_config("validate", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 3)
        self.assertIn("attempt 1/3", result.stderr)
        self.assertIn("attempt 2/3", result.stderr)
        self.assertIn("retrying in 0s", result.stderr)
        self.assertIn("after 3 attempts", result.stderr)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_validate_never_retries_an_unauthorized_key(self):
        secret = "rejected-secret"

        def responder(_call_number):
            return (401, None, None)

        server, calls = self.start_stub_tikin(responder)
        self.write_env_pointing_at(server, secret)

        result = self.run_config("validate", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("authentication or permission rejected (HTTP 401)", result.stderr)
        self.assertNotIn("attempt", result.stderr)
        self.assertNotIn(secret, result.stdout)
        self.assertNotIn(secret, result.stderr)

    def test_validate_never_retries_a_deterministic_client_error(self):
        secret = "bad-request-secret"

        def responder(_call_number):
            return (422, None, None)

        server, calls = self.start_stub_tikin(responder)
        self.write_env_pointing_at(server, secret)

        result = self.run_config("validate", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("HTTP 422", result.stderr)
        self.assertNotIn("attempt", result.stderr)

    def test_validate_retries_a_connection_failure_and_reports_the_budget(self):
        # Bind a port, then close it so nothing is listening: every attempt fails
        # to connect, which is a transient class and must be retried 3 times.
        import socket

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
        probe.close()

        config_dir = self.config_home / "tikin-social"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / ".env").write_text(
            "TIKIN_API_KEY=unreachable-secret\n"
            f"TIKIN_BASE_URL=http://127.0.0.1:{dead_port}\n"
        )

        result = self.run_config("validate", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("attempt 1/3", result.stderr)
        self.assertIn("attempt 2/3", result.stderr)
        self.assertIn("after 3 attempts", result.stderr)
        self.assertNotIn("unreachable-secret", result.stderr)


if __name__ == "__main__":
    unittest.main()
