"""Offline reminder preferences. Called only after tikin-config's runtime bootstrap.

The calling Agent reviews natural-language policies and writes approved rules.
This module never edits Agent instructions or reads API credentials.
"""
import json
import os
from pathlib import Path
import uuid

AGENTS = ("codex", "claude-code", "workbuddy")
PLUGIN = "tikin-social"


def read_settings(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"routing": {"default": "auto", "platforms": {}}}
    except (OSError, ValueError):
        raise ValueError("Cannot read Plugin settings.json; preserve the file and ask the user to repair it.") from None
    if not isinstance(value, dict):
        raise ValueError("settings.json must be an object.")
    preferences = value.get("default_skill_reminders")
    if "default_skill_reminders" in value:
        if not isinstance(preferences, dict) or type(preferences.get("version")) is not int or preferences["version"] != 1 or not isinstance(preferences.get("agents"), list):
            raise ValueError("Unsupported default_skill_reminders schema; preserve settings.json.")
        seen = set()
        for entry in preferences["agents"]:
            if not isinstance(entry, dict) or entry.get("agent") not in AGENTS or not isinstance(entry.get("config_dir"), str) or not Path(entry["config_dir"]).is_absolute() or type(entry.get("enabled")) is not bool:
                raise ValueError("Invalid reminder entry; preserve settings.json.")
            key = (entry["agent"], entry["config_dir"])
            if key in seen:
                raise ValueError("Duplicate reminder entries; preserve settings.json.")
            seen.add(key)
    return value


def update_settings(path, change):
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(target) + ".default-skills.lock")
    fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = target.parent / (".default-skills-" + str(uuid.uuid4()) + ".tmp")
    try:
        original = target.read_bytes() if target.exists() else None
        settings = read_settings(target)
        change(settings)
        with os.fdopen(os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="utf-8") as stream:
            stream.write(json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
        current = target.read_bytes() if target.exists() else None
        if current != original:
            raise ValueError("settings.json changed concurrently; inspect it before retrying.")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
        os.close(fd)
        lock.unlink()


def save_preference(path, agent, config_dir, enabled):
    def change(settings):
        preferences = settings.setdefault("default_skill_reminders", {"version": 1, "agents": []})
        entry = next((item for item in preferences["agents"] if item["agent"] == agent and item["config_dir"] == str(config_dir)), None)
        if entry is None:
            preferences["agents"].append({"agent": agent, "config_dir": str(config_dir), "enabled": enabled})
        else:
            entry["enabled"] = enabled
    update_settings(path, change)


def run(agent, action="check", config_dir=None, global_enabled=True):
    if agent not in AGENTS or action not in ("check", "dismiss", "enable"):
        raise ValueError("Explicit current Agent and a valid reminder action are required.")
    if not global_enabled:
        if action != "check":
            raise ValueError("Cannot save reminder preferences with --no-global-config.")
        return {"status": "skipped", "reason": "global_config_disabled", "plugin": PLUGIN, "agent": agent}
    if agent == "workbuddy" and not config_dir and os.environ.get("WORKBUDDY_CONFIG_DIR") and os.environ.get("CODEBUDDY_CONFIG_DIR") and Path(os.environ["WORKBUDDY_CONFIG_DIR"]).resolve() != Path(os.environ["CODEBUDDY_CONFIG_DIR"]).resolve():
        raise ValueError("WorkBuddy configuration directories disagree; pass the active directory with --config-dir.")
    configured = (os.environ.get("CODEX_HOME") if agent == "codex" else os.environ.get("CLAUDE_CONFIG_DIR") if agent == "claude-code" else os.environ.get("WORKBUDDY_CONFIG_DIR") or os.environ.get("CODEBUDDY_CONFIG_DIR"))
    default_dir = {"codex": ".codex", "claude-code": ".claude", "workbuddy": ".workbuddy"}[agent]
    directory = Path(config_dir or configured or Path.home() / default_dir).expanduser().resolve()
    settings_file = Path.home() / ".config" / PLUGIN / "settings.json"
    if action != "check":
        save_preference(settings_file, agent, directory, action == "enable")
    preferences = read_settings(settings_file).get("default_skill_reminders", {"agents": []})
    entry = next((item for item in preferences["agents"] if item["agent"] == agent and item["config_dir"] == str(directory)), None)
    enabled = entry["enabled"] if entry else True
    base = {"plugin": PLUGIN, "agent": agent, "config_dir": str(directory), "settings_file": str(settings_file), "reminder_enabled": enabled}
    if not enabled:
        return dict(base, status="dismissed")
    if action == "enable":
        return dict(base, status="enabled", next_step="Run check and review the active instructions.")
    names = ["AGENTS.override.md", "AGENTS.md"] if agent == "codex" else ["CLAUDE.md" if agent == "claude-code" else "CODEBUDDY.md"]
    candidates = [directory / name for name in names]
    primary = candidates[-1]
    for candidate in candidates:
        if not candidate.exists():
            continue
        if not candidate.is_file() or candidate.stat().st_size > 1024 * 1024:
            raise ValueError("Agent rule file is not a regular text file within the inspection limit.")
        if candidate.read_text(encoding="utf-8").strip():
            primary = candidate
            break
    rule = (Path(__file__).resolve().parents[2] / "references" / "default-skills-rule.md").read_text(encoding="utf-8").strip()
    return dict(base, status="review_required", global_candidates=[str(path) for path in candidates],
                primary_rule=str(primary), primary_real_path=str(primary.resolve()),
                additional_rules_directory=None if agent == "codex" else str(directory / "rules"),
                proposed_rule=rule, session_loaded="not_verified",
                next_step="Read the active global and project instructions, imports and host overrides. Decide semantic equivalence before offering a default. Never infer missing rules from this report alone.")
