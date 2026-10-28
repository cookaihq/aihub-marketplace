"""Catalog and durable Agent-reviewed defaults. Never writes Agent rules or preferences.

The host supplies installation evidence and semantic rule findings. Native target
guides own checking, rule edits, and reminder storage; this module freezes the menu
and full preview so a later numeric reply cannot select a different set of targets.
"""
import json
import hashlib
from pathlib import Path, PurePosixPath
import re

from .consumers import fingerprint
from .errors import SetupError

CATALOG = Path(__file__).resolve().parents[4] / "references/default-settings-targets.json"
AGENT_NAMES = {"codex": "ChatGPT/Codex", "claude-code": "Claude Code", "workbuddy": "WorkBuddy"}
INSTALLED = {"installed", "disabled", "unloaded"}
INSTALLATIONS = INSTALLED | {"not_installed", "unknown", "source_conflict"}
STATUSES = {"missing", "configured_global", "configured_project", "conflict", "unknown", "skipped"}
PENDING = {"pending_check", "waiting_choice", "set_default_requested", "dismiss_requested", "waiting_confirmation", "applying"}


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    try:
        source = Path(path)
        if source.stat().st_size > 1024 * 1024:
            raise ValueError()
        return json.loads(source.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, ValueError, TypeError):
        raise SetupError("invalid_default_settings_input") from None


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4096 and "\x00" not in value


def identifier(item):
    return item["kind"] + ":" + item["name"]


def catalog(host):
    data = read_json(CATALOG)
    fields = {"kind", "name", "display_name", "source_repository", "setup_guide", "rule_template", "default_message"}
    if (host not in AGENT_NAMES or not isinstance(data, dict) or set(data) != {"schema_version", "targets"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or not isinstance(data["targets"], list)):
        raise SetupError("invalid_default_settings_catalog")
    targets, seen = [], set()
    for item in data["targets"]:
        if (not isinstance(item, dict) or set(item) != fields or not all(text(v) for v in item.values())
                or item["kind"] not in ("plugin", "skill")
                or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", item["name"])
                or not re.fullmatch(r"[\w.-]+/[\w.-]+", item["source_repository"])):
            raise SetupError("invalid_default_settings_catalog")
        for key in ("setup_guide", "rule_template"):
            path = PurePosixPath(item[key])
            if path.is_absolute() or ".." in path.parts or "\\" in item[key] or ":" in item[key] or path.suffix != ".md":
                raise SetupError("invalid_default_settings_catalog")
        try:
            message = item["default_message"].format(agent=AGENT_NAMES[host])
        except (KeyError, ValueError, IndexError, AttributeError):
            raise SetupError("invalid_default_settings_catalog") from None
        key = identifier(item)
        if key in seen:
            raise SetupError("duplicate_default_settings_target")
        seen.add(key)
        targets.append({**item, "id": key, "default_message": message})
    return {"schema_version": 1, "revision": fingerprint(data), "agent_name": AGENT_NAMES[host], "targets": targets}


def revision(path):
    """Allow shared instruction symlinks, record their identity, never copy contents."""
    path = Path(path).expanduser()
    if not path.is_absolute() or any(c in str(path) for c in "\r\n\x00"):
        raise SetupError("invalid_default_rule_path")
    try:
        real = path.resolve()
        if real.exists() and (not real.is_file() or real.stat().st_size > 1024 * 1024):
            raise ValueError()
        digest = hashlib.sha256(real.read_bytes()).hexdigest() if real.exists() else None
    except (OSError, RuntimeError, ValueError):
        raise SetupError("default_rule_unreadable") from None
    return {"path": str(path), "real_path": str(real), "revision": digest}


def artifacts(item, root):
    if not Path(root).is_absolute():
        raise SetupError("default_settings_absolute_root_required")
    root = Path(root).resolve()
    result = {}
    for key in ("setup_guide", "rule_template"):
        path = (root / item[key]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise SetupError("default_settings_artifact_missing")
        result[key] = str(path)
    return result


def directory_identity(value):
    path = Path(value).expanduser()
    if not path.is_absolute() or (path.exists() and not path.is_dir()):
        raise SetupError("invalid_default_settings_config_directory")
    return {"path": str(path), "real_path": str(path.resolve())}


def saved_defaults(state):
    defaults = state.get("result", {}).get("default_settings", {})
    if (not isinstance(defaults, dict) or defaults and
            (type(defaults.get("schema_version")) is not int or defaults["schema_version"] != 1)):
        raise SetupError("unsupported_default_settings_schema")
    return defaults


def pending(state):
    return saved_defaults(state).get("phase") in PENDING


def checkpoint(state):
    if state["phase"] != "completed" or state["operation"] not in ("configure", "repair"):
        raise SetupError("credential_setup_not_completed")
    if not state["context"]["global_enabled"]:
        raise SetupError("default_settings_global_disabled")
    return saved_defaults(state)


def record(state, report):
    checkpoint(state)
    current = catalog(state["context"]["host"])
    definitions = {t["id"]: t for t in current["targets"]}
    if not isinstance(report, dict) or set(report) != {"targets"} or not isinstance(report["targets"], list):
        raise SetupError("invalid_default_settings_report")
    rows, seen = [], set()
    required = {"id", "installation", "evidence", "status", "reason", "session_loaded", "reminder_enabled", "already_prompted"}
    optional = {"root", "config_dir", "global_rule_file", "rule_files"}
    for source in report["targets"]:
        if (not isinstance(source, dict) or not required <= set(source) or set(source) - required - optional
                or source["id"] not in definitions or source["id"] in seen
                or source["installation"] not in INSTALLATIONS or source["status"] not in STATUSES
                or source["session_loaded"] not in ("verified", "not_verified")
                or type(source["reminder_enabled"]) is not bool or type(source["already_prompted"]) is not bool
                or not text(source["evidence"]) or not text(source["reason"])):
            raise SetupError("invalid_default_settings_report")
        seen.add(source["id"])
        row = dict(source)
        if row["installation"] not in INSTALLED and row["status"] not in ("unknown", "skipped"):
            raise SetupError("uninstalled_default_settings_target")
        if row["status"] not in ("unknown", "skipped"):
            if (not all(text(row.get(k)) for k in ("root", "config_dir", "global_rule_file"))
                    or not isinstance(row.get("rule_files"), list) or not row["rule_files"]
                    or not all(text(p) for p in row["rule_files"])):
                raise SetupError("default_rule_evidence_required")
            item = definitions[row["id"]]
            refs = artifacts(item, row["root"])
            files = list(dict.fromkeys([*row["rule_files"], row["global_rule_file"], *refs.values()]))
            row.update(artifacts=refs, snapshots=[revision(p) for p in files])
            row["config_directory"] = directory_identity(row["config_dir"])
            row["config_dir"] = row["config_directory"]["real_path"]
        row.update(display_name=definitions[row["id"]]["display_name"], default_message=definitions[row["id"]]["default_message"])
        rows.append(row)
    if seen != set(definitions):
        raise SetupError("default_settings_targets_incomplete")
    eligible = [r["id"] for r in rows if r["installation"] in INSTALLED and r["status"] == "missing"
                and r["reminder_enabled"] and not r["already_prompted"]]
    result = {"schema_version": 1, "catalog_revision": current["revision"], "agent_name": current["agent_name"],
              "phase": "waiting_choice" if eligible else "completed", "targets": rows, "eligible": eligible}
    state["result"]["default_settings"] = result
    return result


def fresh(state, defaults):
    if defaults.get("catalog_revision") != catalog(state["context"]["host"])["revision"]:
        raise SetupError("default_settings_changed_recheck")
    for row in defaults["targets"]:
        directory = row.get("config_directory")
        if directory and directory_identity(directory["path"]) != directory:
            raise SetupError("default_settings_changed_recheck")
        for expected in row.get("snapshots", []):
            if revision(expected["path"]) != expected:
                raise SetupError("default_settings_changed_recheck")


def choose(state, choice, selected=None):
    defaults = checkpoint(state)
    if defaults.get("phase") != "waiting_choice":
        raise SetupError("no_default_settings_choice")
    choices = {"1": "set_default_requested", "设为默认": "set_default_requested",
               "2": "skipped", "本次跳过": "skipped", "3": "dismiss_requested", "不再提醒": "dismiss_requested"}
    if choice not in choices:
        raise SetupError("invalid_default_settings_choice")
    selected = defaults["eligible"] if selected is None else selected
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= set(defaults["eligible"]):
        raise SetupError("invalid_default_settings_selection")
    if choices[choice] != "skipped":
        fresh(state, defaults)
    defaults.update(phase=choices[choice], selected=list(selected))
    if choices[choice] == "skipped":
        defaults["eligible"] = []
    return defaults


def preview(state, request):
    defaults = checkpoint(state)
    if defaults.get("phase") != "set_default_requested":
        raise SetupError("default_settings_preview_not_requested")
    fresh(state, defaults)
    if not isinstance(request, dict) or set(request) != {"shared_with"} or not isinstance(request["shared_with"], list) or not all(text(s) for s in request["shared_with"]):
        raise SetupError("invalid_default_settings_preview")
    writes = []
    for row in defaults["targets"]:
        if row["id"] in defaults["selected"]:
            target = revision(row["global_rule_file"])
            writes.append({"id": row["id"], "target": target, "scope": "global", "config_dir": row["config_dir"],
                           "rule": Path(row["artifacts"]["rule_template"]).read_text(encoding="utf-8")})
    plan = {"context": state["context"], "catalog_revision": defaults["catalog_revision"],
            "writes": writes, "shared_with": request["shared_with"]}
    plan["confirmation"] = fingerprint(plan)
    defaults.update(phase="waiting_confirmation", preview=plan)
    return defaults


def verify(state, confirmation):
    defaults = checkpoint(state)
    if defaults.get("phase") != "waiting_confirmation" or defaults["preview"]["confirmation"] != confirmation:
        raise SetupError("default_settings_confirmation_required")
    fresh(state, defaults)
    # This verifies a human-approved preview; it does not obtain user consent or
    # edit files. The Agent now follows each target's native documented workflow.
    defaults["phase"] = "applying"
    return defaults


def finish(state, report):
    defaults = checkpoint(state)
    phase = defaults.get("phase")
    if phase not in ("applying", "dismiss_requested"):
        raise SetupError("default_settings_not_applying")
    if not isinstance(report, dict) or set(report) != {"outcomes"} or not isinstance(report["outcomes"], list):
        raise SetupError("invalid_default_settings_outcome")
    seen = set()
    for outcome in report["outcomes"]:
        if (not isinstance(outcome, dict) or set(outcome) != {"id", "status", "session_loaded", "evidence"}
                or outcome["id"] not in defaults["selected"] or outcome["id"] in seen
                or outcome["session_loaded"] not in ("verified", "not_verified") or not text(outcome["evidence"])
                or outcome["status"] not in ({"written", "failed"} if phase == "applying" else {"dismissed", "failed"})):
            raise SetupError("invalid_default_settings_outcome")
        seen.add(outcome["id"])
        if outcome["status"] == "written":
            write = next(w for w in defaults["preview"]["writes"] if w["id"] == outcome["id"])
            path = Path(write["target"]["path"])
            try:
                present = str(path.resolve()) == write["target"]["real_path"] and write["rule"] in path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                present = False
            if not present:
                raise SetupError("default_rule_write_not_verified")
    if seen != set(defaults["selected"]):
        raise SetupError("default_settings_outcomes_incomplete")
    defaults.update(phase="completed", outcomes=report["outcomes"], eligible=[])
    for outcome in report["outcomes"]:
        row = next(r for r in defaults["targets"] if r["id"] == outcome["id"])
        row["session_loaded"] = outcome["session_loaded"]
        if outcome["status"] == "written":
            row.update(status="configured_global", reason=outcome["evidence"])
        elif outcome["status"] == "dismissed":
            row["reminder_enabled"] = False
    return defaults
