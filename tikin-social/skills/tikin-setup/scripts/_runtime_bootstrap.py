"""ADR 0007 bootstrap. This module remains parseable on Python 3.9."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def ensure_runtime(marker="SETUP_AIHUB_BOOTSTRAP_REEXEC", project=None):
    project = Path(project).resolve() if project else Path(__file__).resolve().parent.parent
    environment = project / (os.environ.get("UV_PROJECT_ENVIRONMENT") or ".venv")
    target = os.path.normcase(os.path.realpath(environment))
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    pin = project.joinpath(".python-version").read_text(encoding="utf-8").strip()
    expected = tuple(int(part) for part in pin.split("."))

    def fail(reason):
        quote = "'" + str(project).replace("'", "''") + "'" if os.name == "nt" else shlex.quote(str(project))
        hint = "uv sync --project %s --locked --no-dev" % quote
        if reason == "uv_missing":
            hint = "winget install --id astral-sh.uv -e" if os.name == "nt" else "curl -LsSf https://astral.sh/uv/install.sh | sh"
        elif reason == "uv_too_old":
            hint = "uv self update"
        # Never forward package-manager logs, which can include authenticated index URLs.
        print(json.dumps({"schema": "setup-aihub.result/v1", "status": "runtime_error", "reason": reason,
                          "hint": hint}, ensure_ascii=True))
        raise SystemExit(1)

    try:
        probe = subprocess.run(["uv", "--version"], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        fail("uv_missing")
    match = re.match(rb"uv (\d+)\.(\d+)", probe.stdout)
    if probe.returncode or not match or tuple(map(int, match.groups())) < (0, 8):
        fail("uv_too_old")
    if (os.path.normcase(os.path.realpath(sys.prefix)) == target and sys.version_info[:len(expected)] == expected
            and environment.joinpath("pyvenv.cfg").is_file() and python.is_file()):
        os.environ.pop(marker, None)
        return
    if os.environ.get(marker) == target:
        fail("runtime_reentry")

    valid = False
    if python.is_file() and environment.joinpath("pyvenv.cfg").is_file():
        try:
            probe = subprocess.run([str(python), "-I", "-c", "import json,sys;print(json.dumps([sys.prefix,list(sys.version_info[:2])]))"],
                                   capture_output=True, timeout=10)
            prefix, version = json.loads(probe.stdout)
            valid = probe.returncode == 0 and os.path.normcase(os.path.realpath(prefix)) == target and tuple(version) == expected[:2]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    if not valid:
        sys.stderr.write("[bootstrap] 正在按 uv.lock 准备 Skill 运行环境。\n")
        try:
            result = subprocess.run(["uv", "sync", "--locked", "--no-dev", "--project", str(project)],
                                    capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError):
            fail("runtime_preparation_failed")
        if result.returncode or not python.is_file() or not environment.joinpath("pyvenv.cfg").is_file():
            # Only rebuild the Skill-owned default directory. uv remains in
            # charge of its files; never clear an arbitrary external override.
            owned = project / ".venv"
            known = {"Include", "Lib", "Scripts", "bin", "include", "lib", "lib64", "share", "pyvenv.cfg", "CACHEDIR.TAG", ".gitignore", ".lock"}
            safe = (environment == owned and environment.is_dir() and not environment.is_symlink()
                    and not getattr(environment.lstat(), "st_file_attributes", 0) & 0x400
                    and all(p.name in known for p in environment.iterdir()))
            if not safe:
                fail("runtime_preparation_failed")
            try:
                rebuilt = subprocess.run(["uv", "venv", "--clear", "--python", pin, str(environment)], capture_output=True, timeout=60)
                if rebuilt.returncode:
                    fail("runtime_preparation_failed")
                result = subprocess.run(["uv", "sync", "--locked", "--no-dev", "--project", str(project)], capture_output=True, timeout=60)
            except (OSError, subprocess.SubprocessError):
                fail("runtime_preparation_failed")
            if result.returncode or not python.is_file() or not environment.joinpath("pyvenv.cfg").is_file():
                fail("runtime_preparation_failed")
    os.environ[marker] = target
    if os.name == "nt":
        raise SystemExit(subprocess.run([str(python)] + sys.argv).returncode)
    os.execv(str(python), [str(python)] + sys.argv)
