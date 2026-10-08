"""Real relocated entrypoints and cross-package contracts, using synthetic homes."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from test_setup import MARKET, SKILL
from setup_core.consumers import Consumer
from setup_core.errors import SetupError
from setup_core.local_config import transform


class DistributionTests(unittest.TestCase):
    def test_version_manifests_declared_skills_and_market_entries_are_consistent(self):
        for plugin in ("setup-aihub", "aihub-studio", "tikin-social"):
            root = MARKET / plugin
            if plugin == "aihub-studio":
                version = json.loads((root / "package.json").read_text())["version"]
                lock = json.loads((root / "package-lock.json").read_text())
                self.assertEqual(lock["version"], version)
                self.assertEqual(lock["packages"][""]["version"], version)
            else:
                name = {"tikin-social": "tikin-setup", "setup-aihub": "setup-api-key"}[plugin]
                version = tomllib.loads((root / "skills" / name / "pyproject.toml").read_text())["project"]["version"]
            for folder in (".claude-plugin", ".codex-plugin", ".codebuddy-plugin"):
                manifest = json.loads((root / folder / "plugin.json").read_text(encoding="utf-8"))
                self.assertEqual((manifest["name"], manifest["version"]), (plugin, version))
            for source in (".claude-plugin", ".codebuddy-plugin", ".agents/plugins"):
                market = json.loads((MARKET / source / "marketplace.json").read_text(encoding="utf-8"))
                entry, = [entry for entry in market["plugins"] if entry["name"] == plugin]
                if source == ".agents/plugins":
                    self.assertEqual(entry["source"]["path"], "./" + plugin)
                else:
                    self.assertEqual(entry["version"], version)
                    self.assertEqual(entry["source"], "./" + plugin)
            for file in (root / "skills").glob("*/SKILL.md"):
                text = file.read_text(encoding="utf-8")
                self.assertEqual(re.search(r"^name: (.+)$", text, re.M)[1], file.parent.name)
                self.assertEqual(re.search(r'^metadata:\n  version: "([^"]+)"$', text, re.M)[1], version)
                self.assertIn("description: v" + version + "｜", text)
                runtime = file.parent / "pyproject.toml"
                if runtime.exists():
                    self.assertEqual(tomllib.loads(runtime.read_text())["project"]["version"], version)
                    lock = tomllib.loads((file.parent / "uv.lock").read_text())
                    self.assertEqual(next(p["version"] for p in lock["package"] if p["name"] == file.parent.name), version)
            for file in ("README.md", "CHANGELOG.md", "LICENSE"):
                self.assertTrue((root / file).is_file())
        self.assertEqual((SKILL / "scripts/_runtime_bootstrap.py").read_bytes(),
                         (MARKET / "tikin-social/skills/tikin-setup/scripts/_runtime_bootstrap.py").read_bytes())

    def test_packaged_links_do_not_require_another_installed_plugin_or_private_docs(self):
        checked = 0
        for plugin in ("setup-aihub", "aihub-studio", "tikin-social"):
            root = MARKET / plugin
            for file in root.rglob("*.md"):
                if any(part in {".venv", ".test-build", "node_modules"} for part in file.parts):
                    continue
                text = file.read_text(encoding="utf-8")
                # Literal Markdown examples are not navigable document links.
                text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)
                text = re.sub(r"`[^`\n]*`", "", text)
                for target in re.findall(r"\]\(([^)]+)\)", text):
                    target = target.split("#")[0].strip("<>")
                    if not target or "://" in target or "<" in target:
                        continue
                    path = (file.parent / target).resolve()
                    self.assertTrue(path.is_relative_to(root.resolve()), (file, target))
                    self.assertTrue(path.exists(), (file, target))
                    checked += 1
        self.assertGreater(checked, 80)

    @unittest.skipUnless(os.name == "nt", "native Windows entrypoint")
    def test_windows_aihub_launcher_preserves_cwd_arguments_and_read_only_projection(self):
        with tempfile.TemporaryDirectory(prefix="AIhub Windows 入口 ") as temporary:
            root = Path(temporary)
            plugin = root / "插件 空格"
            project = root / "业务 空格"
            project.mkdir()
            for part in ("scripts", "dist", "catalog", "references"):
                shutil.copytree(MARKET / "aihub-studio" / part, plugin / part)
            shutil.copyfile(MARKET / "aihub-studio/package.json", plugin / "package.json")
            env = {k: v for k, v in os.environ.items() if not k.startswith("AIHUB_")}
            env.update(HOME=str(root / "user"), USERPROFILE=str(root / "user"))
            powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            command = [str(powershell), "-NoProfile", "-File", str(plugin / "scripts/aihub.ps1"),
                       "config-check", "--skill", "aihub-image", "--credentials-only", "--no-global-config"]
            missing = subprocess.run(command, cwd=project, env=env, capture_output=True, timeout=45)
            self.assertEqual(missing.returncode, 3, missing.stdout + missing.stderr)
            report = json.loads(missing.stdout)
            self.assertEqual(report["skill"], "aihub-image")
            self.assertEqual(Path(report["cwd"]), project)
            self.assertFalse(report["global_enabled"])
            self.assertEqual(list(project.iterdir()), [])
            target = project / ".env.local"
            content = b"AIHUB_API_KEY=synthetic-native-entry\nUNRELATED=keep\n"
            target.write_bytes(content)
            ready = subprocess.run(command, cwd=project, env=env, capture_output=True, timeout=45)
            self.assertEqual(ready.returncode, 0, ready.stdout + ready.stderr)
            self.assertEqual(Path(json.loads(ready.stdout)["fields"]["AIHUB_API_KEY"]["source"]), target)
            projected = subprocess.run(command + ["--delete-from", str(target), "--delete-fields", "AIHUB_API_KEY"],
                                       cwd=project, env=env, capture_output=True, timeout=45)
            self.assertEqual(projected.returncode, 0, projected.stdout + projected.stderr)
            projection = json.loads(projected.stdout)
            self.assertEqual(projection["before"]["status"], "ok")
            self.assertEqual(projection["after"]["status"], "configuration_required")
            self.assertEqual(target.read_bytes(), content)
            self.assertNotIn(b"synthetic-native-entry", missing.stdout + ready.stdout + projected.stdout)

    def test_relocated_bootstrap_repairs_missing_and_broken_default_runtime(self):
        with tempfile.TemporaryDirectory(prefix="Setup runtime 中文 ") as temporary:
            root = Path(temporary)
            project = root / "独立目录 空格"
            user = root / "user"
            user.mkdir()
            cwd = root / "业务目录"
            cwd.mkdir()
            shutil.copytree(SKILL, project, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
            env = {k: v for k, v in os.environ.items() if not k.startswith(("AIHUB_", "TIKIN_", "SETUP_AIHUB_", "UV_PROJECT_ENVIRONMENT"))}
            env.update(HOME=str(user), USERPROFILE=str(user), UV_PYTHON=sys.executable, UV_PYTHON_DOWNLOADS="never", PYTHONUTF8="1")
            command = [sys.executable, str(project / "scripts/setup_api_key.py"), "list", "--host", "codex", "--cwd", str(cwd)]
            proc = subprocess.run(command, env=env, capture_output=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((project / ".venv/pyvenv.cfg").is_file())
            self.assertFalse((cwd / ".venv").exists())
            # A damaged owned venv lacking pyvenv.cfg must not loop or use caller's.
            (project / ".venv/pyvenv.cfg").unlink()
            proc = subprocess.run(command, env=env, capture_output=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((project / ".venv/pyvenv.cfg").is_file())
            self.assertFalse((user / ".config").exists())

    def test_uv_relative_environment_is_relative_to_each_consuming_project(self):
        with tempfile.TemporaryDirectory(prefix="Setup uv override ") as temporary:
            root = Path(temporary)
            project = root / "技能"
            cwd = root / "工作文件夹"
            cwd.mkdir()
            shutil.copytree(SKILL, project, ignore=shutil.ignore_patterns(".venv", "__pycache__"))
            env = {**os.environ, "UV_PROJECT_ENVIRONMENT": ".custom-runtime", "UV_PYTHON": sys.executable,
                   "UV_PYTHON_DOWNLOADS": "never", "HOME": str(root / "user"), "USERPROFILE": str(root / "user"), "PYTHONUTF8": "1"}
            proc = subprocess.run([sys.executable, str(project / "scripts/setup_api_key.py"), "list", "--host", "codex", "--cwd", str(cwd)],
                                  cwd=cwd, env=env, capture_output=True, timeout=40)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((project / ".custom-runtime/pyvenv.cfg").is_file())
            self.assertFalse((cwd / ".custom-runtime").exists())

    def test_invalid_report_and_subprocess_error_never_leak_raw_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            consumer = Consumer("aihub-studio", MARKET / "aihub-studio", None, temporary)
            value = "synthetic-private-output"
            for result in (subprocess.CompletedProcess([], 1, value.encode(), value.encode()),
                           subprocess.CompletedProcess([], 0, json.dumps({"error": value}).encode(), b"")):
                with patch("setup_core.consumers.subprocess.run", return_value=result):
                    with self.assertRaises(SetupError) as raised:
                        consumer.inspect()
                    self.assertNotIn(value, str(raised.exception))

    def test_format_guard_refuses_multiline_or_embedded_bom_without_transforming(self):
        for raw in (b'AIHUB_API_KEY="first\ncontinuation"\n', b"X=ok\n\xef\xbb\xbfAIHUB_API_KEY=synthetic\n"):
            with self.assertRaises(SetupError):
                transform(raw, ["AIHUB_API_KEY"], "clear")


if __name__ == "__main__":
    unittest.main()
