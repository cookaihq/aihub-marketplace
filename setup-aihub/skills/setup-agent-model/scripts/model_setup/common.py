"""Reuse the complete Plugin's proven file and Windows ACL primitives."""
import hashlib
import json
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL.parent / "setup-api-key" / "scripts"))
from setup_core.errors import SetupError
from setup_core.local_config import checked_path, snapshot, same_snapshot, git_safe, replace_content
from setup_core.local_platform import exclusive_lock, private_directory, private_permissions, sync_replaced_file

HOSTS = ("hermes", "workbuddy", "chatgpt", "codex", "claude-desktop", "claude-code")
NAMES = dict(zip(HOSTS, ("Hermes", "WorkBuddy", "ChatGPT 桌面客户端", "Codex CLI", "Claude 桌面客户端", "Claude Code CLI")))


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def json_object(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise SetupError("duplicate_json_key")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(SetupError("invalid_number")))
    except (ValueError, UnicodeError):
        raise SetupError("invalid_json") from None


def single_line(value, *, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise SetupError("invalid_text_field")
    return value
