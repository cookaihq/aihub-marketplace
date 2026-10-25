"""A public, value-free native write plan, revalidated by both credential paths."""
import copy
from pathlib import Path
import re

from . import clients
from .common import SetupError, digest, single_line, git_safe

REQUEST_KEYS = {"client", "config", "selector", "new", "identity", "name", "models", "protocol",
                "default_model", "key_mode", "key_group", "custom_models", "route_evidence"}


def choose(request, catalog):
    ids = request.get("models")
    if (not isinstance(ids, list) or not ids or len(ids) > 30 or any(not isinstance(mid, str) for mid in ids)
            or len(set(ids)) != len(ids)):
        raise SetupError("model_selection_required")
    protocol = request.get("protocol")
    if protocol not in clients.PROTOCOLS[request["client"]]:
        raise SetupError("client_protocol_unsupported")
    if request.get("default_model") is not None and request["default_model"] not in ids:
        raise SetupError("default_must_be_selected_separately")
    by_id = {m["id"]: m for m in catalog["models"]}
    custom = request.get("custom_models", [])
    if not isinstance(custom, list):
        raise SetupError("custom_models_invalid")
    if custom:
        from .catalog import validate
        validate({**catalog, "models": custom})
        if any(m["id"] in by_id or m["id"] not in ids for m in custom):
            raise SetupError("custom_model_conflicts_with_catalog")
        by_id.update({m["id"]: m for m in custom})
    selected = []
    evidence = request.get("route_evidence", [])
    if not isinstance(evidence, list) or any(not isinstance(e, dict) or set(e) != {"model", "protocol", "source"}
            or not isinstance(e["source"], str) or not e["source"].startswith("https://")
            or clients.safe_url(e["source"]) != e["source"] for e in evidence):
        raise SetupError("route_evidence_invalid")
    for mid in ids:
        if mid not in by_id:
            raise SetupError("model_not_in_catalog", model=mid)
        model = copy.deepcopy(by_id[mid])
        if model["status"] != "active":
            raise SetupError("model_deprecated", model=mid)
        groups = model.get("key_groups", [])
        chosen_group = request.get("key_group")
        if chosen_group == "Claude-Max" and request["client"] != "claude-code":
            raise SetupError("claude_max_restricted_to_claude_code")
        if groups == ["Claude-Max"] and request["client"] != "claude-code":
            raise SetupError("catalog_group_restricted", model=mid)
        if chosen_group and chosen_group not in groups and chosen_group != "auto":
            raise SetupError("key_group_not_registered", model=mid)
        if protocol not in {r["protocol"] for r in model["routes"]}:
            if not any(e["model"] == mid and e["protocol"] == protocol for e in evidence):
                raise SetupError("model_protocol_needs_evidence", model=mid, protocol=protocol)
            model["routes"].append({"protocol": protocol, "capabilities": {
                "tool_calling": None, "image_input": None, "reasoning_efforts": None}})
        selected.append(model)
    return selected


def changes(before, after, secrets, prefix=()):
    result = []
    if before == after:
        return result
    if list(prefix) in secrets:
        return [{"field": list(prefix), "before": "[已填写]" if before else "[未填写]", "after": "[本机输入或 Secret Book]"}]
    if prefix and prefix[-1] in ("api", "url", "base_url", "ANTHROPIC_BASE_URL", "inferenceGatewayBaseUrl"):
        return [{"field": list(prefix), "before": clients.safe_url(before), "after": clients.safe_url(after)}]
    if isinstance(after, dict) and (isinstance(before, dict) or before is None):
        old = before or {}
        for name in after:
            result += changes(old.get(name), after[name], secrets, (*prefix, name))
        for name in old.keys() - after.keys():
            result.append({"field": [*prefix, name], "operation": "remove", "before": old[name], "after": None})
    elif isinstance(after, list) and (isinstance(before, list) or before is None):
        old = before or []
        for i, value in enumerate(after):
            result += changes(old[i] if i < len(old) else None, value, secrets, (*prefix, i))
    else:
        result.append({"field": list(prefix), "before": before, "after": after})
    return result


def build(request, cwd, catalog, manifest):
    if (not isinstance(request, dict) or set(request) - REQUEST_KEYS or
            request.get("client") not in clients.HOSTS or type(request.get("new")) is not bool or
            request.get("key_mode") not in ("replace", "preserve")):
        raise SetupError("invalid_configuration_request")
    client = request["client"]
    path = clients.allowed_file(client, request["config"], cwd)
    selector = single_line(request["selector"])
    data, raw, snap = clients.load(path, client)
    records = clients.entries(data, client)
    matches = [entry for entry in records if entry["selector"] == selector]
    if request["new"]:
        if matches and client not in ("claude-code",):
            raise SetupError("configuration_already_exists")
        if client == "claude-desktop":
            raise SetupError("desktop_create_in_native_library")
        if client in ("hermes", "codex", "chatgpt") and not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", selector):
            raise SetupError("invalid_provider_name")
        if client == "claude-code" and (selector != "$settings" or snap["revision"] is not None):
            raise SetupError("select_existing_settings")
        single_line(request.get("name"))
        if request["key_mode"] != "replace":
            raise SetupError("new_configuration_requires_key")
    elif len(matches) != 1 or request.get("identity") != matches[0]["identity"]:
        raise SetupError("inspect_and_select_exact_configuration")
    observed = clients.observations(client, path, data, selector, cwd)
    if observed["blocks"]:
        raise SetupError("higher_priority_source_requires_repair", blockers=observed["blocks"])
    selected = choose(request, catalog)
    projected, pointers = clients.transform(data, request, selected, "__LOCAL_KEY_INPUT__" if request["key_mode"] == "replace" else None)
    planned_sources = clients.observations(client, path, projected, selector, cwd)
    if planned_sources["blocks"]:
        raise SetupError("planned_source_requires_repair", blockers=planned_sources["blocks"])
    if request["key_mode"] == "preserve" and any(not clients.value_at(data, p) for p in pointers):
        raise SetupError("existing_key_missing")
    git_safe(path)
    plan = {"schema": "setup-agent-model.plan/v1", "request": request, "cwd": str(Path(cwd).absolute()),
            "target": snap, "observations": observed, "planned_observations": planned_sources,
            "selected_models": selected, "catalog_manifest": manifest,
            "secret_fields": pointers, "changes": changes(data, projected, pointers),
            "shared_with": ["chatgpt", "codex"] if client in ("codex", "chatgpt") else [client],
            "verification": {"saved": False, "client_loaded": "not_verified", "model_call": "not_run"}}
    plan["fingerprint"] = digest(plan)
    return plan


def revalidate(plan):
    validate_plan(plan)
    # The selected catalog is frozen for this confirmation. A later data refresh
    # does not silently change a model, route, capability or default.
    frozen = {"models": plan["selected_models"]}
    request = {**plan["request"], "custom_models": []}
    regenerated = build(request, plan["cwd"], frozen, plan["catalog_manifest"])
    regenerated["request"] = plan["request"]
    regenerated["fingerprint"] = digest({k: v for k, v in regenerated.items() if k != "fingerprint"})
    if regenerated != plan:
        raise SetupError("plan_stale")
    return regenerated


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema") != "setup-agent-model.plan/v1":
        raise SetupError("invalid_plan")
    fingerprint = plan.get("fingerprint")
    if fingerprint != digest({k: v for k, v in plan.items() if k != "fingerprint"}):
        raise SetupError("plan_changed")
    request = plan["request"]
    path = clients.allowed_file(request["client"], request["config"], plan["cwd"])
    if str(path) != plan["target"]["path"]:
        raise SetupError("plan_target_mismatch")


def verify(plan):
    """Independent readback, also safe after an interrupted/uncertain writer."""
    validate_plan(plan)
    request = plan["request"]
    data, raw, snap = clients.load(plan["target"]["path"], request["client"])
    keys_present = all(bool(clients.value_at(data, pointer)) for pointer in plan["secret_fields"])
    matched = True
    for change in plan["changes"]:
        if change["field"] in plan["secret_fields"]:
            continue
        if change.get("operation") == "remove":
            parent = clients.value_at(data, change["field"][:-1])
            if isinstance(parent, dict) and change["field"][-1] in parent:
                matched = False
            continue
        if clients.value_at(data, change["field"]) != change["after"]:
            matched = False
    observed = clients.observations(request["client"], Path(snap["path"]), data, request["selector"], plan["cwd"])
    return {"path": snap["path"], "revision": snap["revision"], "keys_present": keys_present,
            "configuration_matches": matched, "source_blocks": observed["blocks"],
            "saved": keys_present and matched, "client_loaded": "not_verified", "model_call": "not_run"}
