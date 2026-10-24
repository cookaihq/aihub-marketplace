"""Two explicit adapters. No configuration precedence or credential values live here."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .errors import SetupError

ADAPTERS = {
    "aihub-studio": {
        "declaration": "references/credentials.json", "minimum": (1, 2, 0),
        "fields": {"AIHUB_API_KEY"}, "runtime": "package.json",
        "artifacts": ["scripts/aihub.mjs", "scripts/aihub.ps1", "dist/cli.js", "dist/config.js"],
    },
    "tikin-social": {
        "declaration": "skills/tikin-setup/references/credentials.json", "minimum": (1, 2, 0),
        "fields": {"TIKIN_API_KEY", "TIKIN_BASE_URL"}, "runtime": "skills/tikin-setup/pyproject.toml",
        "artifacts": ["skills/tikin-setup/scripts/tikin-config", "skills/tikin-setup/scripts/_runtime_bootstrap.py",
                      "skills/tikin-setup/.python-version", "skills/tikin-setup/uv.lock"],
    },
}
HOSTS = ("claude-code", "codex", "workbuddy")


def path_id(path):
    return os.path.normcase(os.path.abspath(path))


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise SetupError("incompatible_artifact") from None


class Consumer:
    def __init__(self, name, root, caller, cwd, global_enabled=True):
        if name not in ADAPTERS:
            raise SetupError("unsupported_plugin")
        self.name, self.adapter = name, ADAPTERS[name]
        self.root, self.cwd = Path(root).resolve(), Path(cwd).resolve()
        self.caller, self.global_enabled = caller, global_enabled
        manifests = [_json(self.root / folder / "plugin.json")
                     for folder in (".claude-plugin", ".codex-plugin", ".codebuddy-plugin")]
        versions = {item.get("version") for item in manifests}
        if any(item.get("name") != name for item in manifests) or len(versions) != 1:
            raise SetupError("plugin_identity_mismatch")
        self.version = versions.pop()
        if not isinstance(self.version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise SetupError("incompatible_version")
        version = tuple(map(int, self.version.split(".")))
        if version < self.adapter["minimum"] or version[0] != 1:
            raise SetupError("incompatible_version", minimum=".".join(map(str, self.adapter["minimum"])))
        self.declaration_path = self.root / self.adapter["declaration"]
        self.declaration = _json(self.declaration_path)
        consumer = self.declaration.get("consumer", {})
        keys = self.declaration.get("keys", {})
        if (self.declaration.get("schema_version") != 1 or consumer.get("kind") != "plugin"
                or consumer.get("name") != name or set(keys) != self.adapter["fields"]):
            raise SetupError("incompatible_declaration")
        skills = consumer.get("skills", [])
        if not isinstance(skills, list) or not skills or any(not isinstance(s, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", s) for s in skills):
            raise SetupError("incompatible_declaration")
        if caller is not None and caller not in skills:
            raise SetupError("unknown_caller")
        key = "AIHUB_API_KEY" if name == "aihub-studio" else "TIKIN_API_KEY"
        if keys[key].get("required") is not True or keys[key].get("sensitive") is not True:
            raise SetupError("incompatible_declaration")
        if name == "tikin-social" and (keys["TIKIN_BASE_URL"].get("default") != "https://console.tikin.net"
                or keys["TIKIN_BASE_URL"].get("required") is not False or keys["TIKIN_BASE_URL"].get("sensitive") is not False
                or self.declaration.get("groups") != [["TIKIN_API_KEY", "TIKIN_BASE_URL"]]):
            raise SetupError("incompatible_declaration")
        if name == "aihub-studio" and self.declaration.get("groups"):
            raise SetupError("incompatible_declaration")
        try:
            artifacts = [self.declaration_path, self.root / self.adapter["runtime"]]
            artifacts += [self.root / part for part in self.adapter["artifacts"]]
            self.revision = fingerprint([hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts])
        except OSError:
            raise SetupError("incomplete_plugin") from None

    def command(self):
        if self.name == "aihub-studio":
            if os.name == "nt":
                powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
                argv = [str(powershell), "-NoProfile", "-File", str(self.root / "scripts/aihub.ps1")]
            else:
                argv = ["node", str(self.root / "scripts/aihub.mjs")]
            argv += ["config-check", "--credentials-only"]
        else:
            project = self.root / "skills/tikin-setup"
            argv = ["uv", "run", "--locked", "--no-dev", "--project", str(project), "python", str(project / "scripts/tikin-config")]
        argv += ["--skill", self.caller] if self.caller else ["--plugin-only"]
        if not self.global_enabled:
            argv.append("--no-global-config")
        if self.name == "tikin-social":
            argv.append("config-check")
        return argv

    def inspect(self, deletion=None):
        argv = self.command()
        if deletion:
            argv += ["--delete-from", str(deletion["target"]), "--delete-fields", ",".join(deletion["fields"])]
        # Preserve the real calling directory and user-supplied uv override. Setup
        # never injects its own resolved venv, values or HOME into a business child.
        environment = dict(os.environ)
        environment.pop("SETUP_AIHUB_BOOTSTRAP_REEXEC", None)
        try:
            process = subprocess.run(argv, cwd=self.cwd, env=environment, capture_output=True, timeout=240)
        except FileNotFoundError:
            raise SetupError("runtime_missing", tool=argv[0]) from None
        except subprocess.TimeoutExpired:
            raise SetupError("inspection_timeout") from None
        except OSError:
            raise SetupError("inspection_start_failed") from None
        # The process can write sensitive errors. Do not forward stdout/stderr on
        # failure or retain unknown properties even when valid JSON is returned.
        if process.returncode not in (0, 3):
            raise SetupError("inspection_failed", exit_code=process.returncode)
        try:
            if len(process.stdout) > 1024 * 1024:
                raise ValueError()
            report = json.loads(process.stdout)
        except (UnicodeError, ValueError):
            raise SetupError("invalid_inspection_output") from None
        if deletion:
            if (process.returncode != 0 or report.get("schema") != "config-deletion-preview/v1"
                    or report.get("operation") != "delete" or path_id(report.get("target", "")) != path_id(deletion["target"])
                    or report.get("fields") != deletion["fields"]):
                raise SetupError("invalid_deletion_projection")
            return {"schema": "config-deletion-preview/v1", "operation": "delete", "target": str(deletion["target"]),
                    "fields": deletion["fields"], "before": self.validate(report.get("before")), "after": self.validate(report.get("after"))}
        result = self.validate(report)
        if (result["status"] == "ok") != (process.returncode == 0):
            raise SetupError("inspection_exit_mismatch")
        return result

    def validate(self, report):
        try:
            return self._validate(report)
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SetupError("incompatible_inspection") from None

    def _validate(self, report):
        if (report["schema"] != "secret-book.config-inspection/v1" or report["consumer"] != {"kind": "plugin", "name": self.name}
                or report["skill"] != self.caller or path_id(report["cwd"]) != path_id(self.cwd)
                or report["global_enabled"] is not self.global_enabled
                or set(report["fields"]) != self.adapter["fields"] or set(report["environment"]) != self.adapter["fields"]
                or report["status"] not in ("ok", "configuration_required")):
            raise ValueError()
        layers, paths = [], set()
        for layer in report["layers"]:
            path = layer["path"]
            if not isinstance(path, str) or not Path(path).is_absolute() or any(c in path for c in "\n\r\x00"):
                raise ValueError()
            revision = layer["revision"]
            if revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[a-f0-9]{64}", revision)):
                raise ValueError()
            item = {"path": path, "revision": revision}
            if "error" in layer:
                if layer["error"] != "unreadable":
                    raise ValueError()
                item["error"] = "unreadable"
            paths.add(path)
            layers.append(item)
        sources = paths | {"environment", "missing", "built-in default"}
        reasons = {"missing", "unreadable", "invalid_url", "invalid_key"}
        fields, environment, problems = {}, {}, []
        for key in self.adapter["fields"]:
            field = report["fields"][key]
            if type(field["present"]) is not bool or field["source"] not in sources:
                raise ValueError()
            fields[key] = {"source": field["source"], "present": field["present"]}
            if "problem" in field:
                if field["problem"] not in reasons:
                    raise ValueError()
                fields[key]["problem"] = field["problem"]
            value = report["environment"][key]
            if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)):
                raise ValueError()
            environment[key] = value
        for problem in report["problems"]:
            if problem["source"] not in sources or problem["reason"] not in reasons:
                raise ValueError()
            item = {"source": problem["source"], "reason": problem["reason"]}
            if "key" in problem:
                if problem["key"] not in fields:
                    raise ValueError()
                item["key"] = problem["key"]
            problems.append(item)
        if (not problems) != (report["status"] == "ok"):
            raise ValueError()
        return {"schema": report["schema"], "status": report["status"], "consumer": report["consumer"],
                "skill": self.caller, "cwd": str(self.cwd), "global_enabled": self.global_enabled,
                "layers": layers, "fields": fields, "environment": environment, "problems": problems}

    def context(self, host):
        return {"host": host, "platform": os.name, "home": str(Path.home().resolve()), "cwd": str(self.cwd),
                "plugin": self.name, "root": str(self.root), "version": self.version, "artifact_revision": self.revision,
                "caller": self.caller, "global_enabled": self.global_enabled}

    @classmethod
    def from_context(cls, context):
        return cls(context["plugin"], context["root"], context["caller"], context["cwd"], context["global_enabled"])
