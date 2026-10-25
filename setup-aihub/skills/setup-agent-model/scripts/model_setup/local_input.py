"""User-owned native password input. The value only returns over a private pipe."""
import getpass
import os
from pathlib import Path
import subprocess
import sys

from .common import SetupError


def read_key(mode, path):
    if mode == "terminal":
        if not sys.stdin.isatty():
            raise SetupError("manual_input_requires_local_terminal")
        return getpass.getpass("在本机填写 Key（输入隐藏，不进聊天）：")
    scripts = Path(__file__).resolve().parent.parent
    if sys.platform == "win32":
        executable = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [str(executable), "-NoProfile", "-STA", "-File", str(scripts / "prompt_key.ps1"), "-Target", path]
    elif sys.platform == "darwin":
        command = ["/usr/bin/osascript", str(scripts / "prompt_key.applescript"), path]
    else:
        raise SetupError("unsupported_os")
    try:
        process = subprocess.run(command, capture_output=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        raise SetupError("local_input_unavailable") from None
    if process.returncode:
        raise SetupError("local_input_cancelled_or_unavailable")
    return process.stdout.decode("utf-8").rstrip("\r\n")
