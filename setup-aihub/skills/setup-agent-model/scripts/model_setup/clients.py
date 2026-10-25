"""Native file adapters. Selection and activation are explicit, independent inputs."""
import copy
import io
import os
from pathlib import Path
import plistlib
import re
import sys
from urllib.parse import urlsplit

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml.tokens import AliasToken

from .common import HOSTS, NAMES, SetupError, checked_path, snapshot, digest, json_object, single_line

PROTOCOLS = {
    "hermes": {"openai-chat-completions", "openai-responses", "anthropic-messages"},
    "workbuddy": {"openai-chat-completions"},
    "chatgpt": {"openai-responses"}, "codex": {"openai-responses"},
    "claude-desktop": {"anthropic-messages"}, "claude-code": {"anthropic-messages"},
}
TRANSPORT = {"openai-chat-completions": "chat_completions", "openai-responses": "codex_responses",
             "anthropic-messages": "anthropic_messages"}


def codex_root():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex").absolute()


def hermes_native_root():
    suffix = os.environ.get("HERMES_DATA_DIR_SUFFIX", "")
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / ("hermes" + suffix)
    return Path.home() / (".hermes" + suffix)


def hermes_root():
    return Path(os.path.expandvars(os.environ.get("HERMES_HOME", ""))).expanduser().absolute() if os.environ.get("HERMES_HOME", "").strip() else hermes_native_root().absolute()


def hermes_profiles_root():
    root, native = hermes_root(), hermes_native_root().absolute()
    if root.is_relative_to(native):
        return native
    return root.parent.parent if root.parent.name == "profiles" else root


def desktop_root():
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Claude-3p/configLibrary"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude-3p/configLibrary"
    raise SetupError("unsupported_os")


def files(client, cwd):
    if client not in HOSTS:
        raise SetupError("unknown_client")
    cwd = Path(cwd).absolute()
    if client == "workbuddy":
        root = os.environ.get("CODEBUDDY_CONFIG_DIR") or os.environ.get("WORKBUDDY_CONFIG_DIR")
        return [(Path(os.path.expandvars(root)).expanduser() if root else Path.home() / ".workbuddy") / "models.json"]
    if client in ("codex", "chatgpt"):
        root = codex_root()
        return [root / "config.toml", *sorted(root.glob("*.config.toml"))]
    if client == "hermes":
        root = hermes_profiles_root()
        return list(dict.fromkeys([root / "config.yaml", hermes_root() / "config.yaml",
                                 *sorted((root / "profiles").glob("*/config.yaml"))]))
    if client == "claude-code":
        root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        return [root / "settings.json", cwd / ".claude/settings.json", cwd / ".claude/settings.local.json"]
    return sorted(p for p in desktop_root().glob("*.json") if p.name != "_meta.json")


def allowed_file(client, path, cwd):
    path = checked_path(path)
    if path in files(client, cwd):
        return path
    if client in ("codex", "chatgpt") and path.parent == codex_root() and re.fullmatch(r"[a-zA-Z0-9_-]+\.config\.toml", path.name):
        return path
    if client == "hermes" and path.name == "config.yaml" and path.parent.parent == hermes_profiles_root() / "profiles":
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", path.parent.name):
            return path
    # Desktop library creation/activation belongs to its native UI: the public
    # docs don't specify the _meta.json schema. Never invent it.
    raise SetupError("target_not_native_configuration")


def load(path, client):
    expected = snapshot(path)
    raw = Path(path).read_bytes() if expected["revision"] else b""
    try:
        text = raw.decode("utf-8-sig")
        if client == "hermes":
            yaml = YAML(typ="rt")
            yaml.preserve_quotes = True
            if any(isinstance(token, AliasToken) for token in yaml.scan(text)):
                raise SetupError("yaml_alias_requires_native_review")
            data = yaml.load(text) if text.strip() else {}
        elif client in ("codex", "chatgpt"):
            data = tomlkit.parse(text)
        else:
            data = json_object(text) if text.strip() else ([] if client == "workbuddy" else {})
    except SetupError:
        raise
    except Exception:
        raise SetupError("native_configuration_invalid", path=str(path)) from None
    if not isinstance(data, list if client == "workbuddy" else dict):
        raise SetupError("native_configuration_shape_invalid")
    return data, raw, expected


def encode(data, client, original):
    if client == "hermes":
        output = io.StringIO()
        yaml = YAML(typ="rt")
        yaml.preserve_quotes = True
        yaml.dump(data, output)
        text = output.getvalue()
    elif client in ("codex", "chatgpt"):
        text = tomlkit.dumps(data)
    else:
        import json
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if b"\r\n" in original:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    return (b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")


def _mapping(data, key):
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise SetupError("native_configuration_shape_invalid", field=key)
    return value


def safe_url(value):
    if not isinstance(value, str):
        return None
    try:
        p = urlsplit(value)
        if p.username or p.password or p.query or p.fragment or p.scheme not in ("https", "http"):
            return "[地址含认证信息或格式未知，已隐藏]"
        return value
    except ValueError:
        return "[地址格式未知]"


def entries(data, client):
    """Only allowlisted public fields leave this process. Never dump config."""
    if client == "workbuddy":
        if any(not isinstance(item, dict) for item in data):
            raise SetupError("native_configuration_shape_invalid")
        return [{"selector": str(i), "concept": "模型配置", "name": item.get("name"),
                 "models": [item.get("id")], "url": safe_url(item.get("url")),
                 "key_present": bool(item.get("apiKey")), "identity": digest(item)} for i, item in enumerate(data)]
    if client in ("codex", "chatgpt", "hermes"):
        field = "providers" if client == "hermes" else "model_providers"
        records = _mapping(data, field)
        result = []
        for name, item in records.items():
            if not isinstance(item, dict):
                raise SetupError("native_configuration_shape_invalid", field=field)
            models = item.get("models", {}) if client == "hermes" else []
            result.append({"selector": name, "concept": "Provider", "name": item.get("name", name),
                           "models": list(models) if isinstance(models, (dict, list)) else [],
                           "url": safe_url(item.get("api", item.get("base_url"))),
                           "key_present": bool(item.get("api_key" if client == "hermes" else "experimental_bearer_token")),
                           "identity": digest(item)})
        if client == "hermes" and isinstance(data.get("model"), dict):
            item = data["model"]
            result.append({"selector": "$model", "concept": "当前 model 配置", "name": item.get("provider"),
                           "models": [item.get("default")], "url": safe_url(item.get("base_url")),
                           "key_present": bool(item.get("api_key")), "identity": digest(item)})
        return result
    if client == "claude-code":
        env = _mapping(data, "env")
        return [{"selector": "$settings", "concept": "设置范围", "name": "Claude Code settings",
                 "models": [data.get("model")], "url": safe_url(env.get("ANTHROPIC_BASE_URL")),
                 "key_present": bool(env.get("ANTHROPIC_AUTH_TOKEN")), "identity": digest(data)}]
    if not data.get("inferenceProvider"):
        raise SetupError("desktop_library_entry_schema_unverified")
    return [{"selector": "$configuration", "concept": "第三方推理配置", "name": data.get("inferenceProvider"),
             "models": [m.get("name") if isinstance(m, dict) else m for m in data.get("inferenceModels", [])],
             "url": safe_url(data.get("inferenceGatewayBaseUrl")), "key_present": bool(data.get("inferenceGatewayApiKey")),
             "identity": digest(data)}]


def _policy_keys():
    """Only names, never values. HKLM shadows HKCU on Windows."""
    if sys.platform == "win32":
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r"SOFTWARE\Policies\Claude") as handle:
                    return [winreg.EnumValue(handle, i)[0] for i in range(winreg.QueryInfoKey(handle)[1])]
            except FileNotFoundError:
                continue
            except OSError:
                raise SetupError("desktop_policy_unreadable") from None
        return []
    result = set()
    for path in (Path("/Library/Managed Preferences/com.anthropic.claudefordesktop.plist"),
                 Path("/Library/Managed Preferences") / Path.home().name / "com.anthropic.claudefordesktop.plist"):
        if path.exists():
            try:
                result.update(plistlib.loads(path.read_bytes()).keys())
            except Exception:
                raise SetupError("desktop_policy_unreadable") from None
    return sorted(result)


def observations(client, path, data, selector, cwd):
    layers, blocks, notices, environment = [], [], [], {}
    def layer(p):
        current = snapshot(p)
        layers.append(current)
        return current
    def env(name):
        value = os.environ.get(name, "")
        environment[name] = digest(value) if value else None
        return bool(value)
    if client in ("codex", "chatgpt"):
        item = _mapping(data, "model_providers").get(selector, {})
        for key in ("env_key", "auth", "http_headers", "env_http_headers"):
            if item.get(key):
                blocks.append("provider_auth_override:" + key)
        if item.get("requires_openai_auth"):
            blocks.append("provider_uses_openai_login")
        if data.get("profiles"):
            notices.append("旧 profiles 表存在；本适配器只管理当前版本的独立 *.config.toml")
        for p in (codex_root() / "config.toml", Path(cwd) / ".codex/config.toml"):
            if p != path:
                layer(p)
                if p.exists():
                    other, _, _ = load(p, client)
                    provider = _mapping(other, "model_providers").get(selector, {})
                    if not isinstance(provider, dict):
                        raise SetupError("native_configuration_shape_invalid")
                    # Profiles merge with the base provider table. An inherited
                    # env/header credential can shadow the new inline bearer.
                    if p == codex_root() / "config.toml":
                        for key in ("env_key", "auth", "http_headers", "env_http_headers", "requires_openai_auth"):
                            if provider.get(key) and key not in item:
                                blocks.append("inherited_provider_auth:" + str(p) + ":" + key)
                    elif provider or any(other.get(k) for k in ("model", "model_provider")):
                        blocks.append("repair_project_configuration:" + str(p))
                    notices.append("配置层已核对文件；实际 profile/项目信任状态仍须在目标会话核对：" + str(p))
        notices.append("ChatGPT 与 Codex CLI 可能共享此文件；命令行、选定 profile 和项目层须分别核对")
    elif client == "hermes":
        item = data.get("model", {}) if selector == "$model" else _mapping(data, "providers").get(selector, {})
        for key in ("key_cmd", "key_env", "api_key_env", "extra_headers"):
            if item.get(key):
                blocks.append("provider_auth_override:" + key)
                if key in ("key_env", "api_key_env"):
                    env(item[key])
        names = {selector.lower(), "custom:" + selector.lower(),
                 "custom:" + str(item.get("name", selector)).strip().lower().replace(" ", "-")}
        if selector != "$model" and item.get("api_mode"):
            blocks.append("hermes_legacy_api_mode_requires_native_migration")
        roots = {path.parent, hermes_profiles_root(), hermes_native_root()}
        for root in roots:
            auth = root / "auth.json"
            layer(auth)
            if auth.exists():
                auth_data = json_object(auth.read_bytes())
                pools = auth_data.get("credential_pool", {})
                if not isinstance(pools, dict):
                    raise SetupError("credential_pool_invalid")
                if any(pools.get(name) for name in names) or (selector == "$model" and pools):
                    blocks.append("hermes_credential_pool_precedence:" + str(auth))
        if data.get("custom_providers"):
            notices.append("存在 Hermes 旧 custom_providers；先由原生迁移流程核对，不自动重写")
    elif client == "claude-code":
        envs = _mapping(data, "env")
        if data.get("apiKeyHelper") or envs.get("ANTHROPIC_API_KEY"):
            blocks.append("claude_alternate_authentication")
        if any(str(envs.get(k, "")).lower() not in ("", "0", "false")
               for k in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")):
            blocks.append("claude_alternate_provider")
        if any(envs.get(k) for k in ("ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_MODEL")):
            blocks.append("claude_model_override_requires_review")
        if any(data.get(k) for k in ("availableModels", "deniedModels", "modelOverrides")):
            notices.append("存在模型限制或映射，保留原策略；须从原生 /model 核对所选模型可用性")
        for key in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
                    "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY"):
            if env(key):
                notices.append("进程变量需核对启动来源：" + key)
        paths = files(client, cwd)
        for p in paths[paths.index(path) + 1:]:
            layer(p)
            if p.exists():
                higher, _, _ = load(p, client)
                if (higher.get("apiKeyHelper") or higher.get("model") or higher.get("availableModels")
                        or any(k.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_")) for k in _mapping(higher, "env"))):
                    blocks.append("repair_higher_priority_settings:" + str(p))
        managed = Path("C:/Program Files/ClaudeCode/managed-settings.json") if sys.platform == "win32" else Path("/Library/Application Support/ClaudeCode/managed-settings.json")
        layer(managed)
        if managed.exists():
            blocks.append("claude_managed_settings_require_review")
    elif client == "claude-desktop":
        app_behavior = {"disableAutoUpdates", "autoUpdaterEnforcementHours", "installedUpdateEnforcementEnabled",
                        "installedUpdateEnforcementHours", "updateViaUpdatesHost", "releaseChannel",
                        "relaunchEnforcementHours", "configRecheckIntervalMinutes", "egressProxyUrl", "egressProxyPacUrl"}
        if set(_policy_keys()) - app_behavior:
            blocks.append("desktop_managed_configuration_precedence")
        if any(data.get(k) for k in ("bootstrapUrl", "inferenceCredentialHelper", "inferenceGatewayOidc", "inferenceIdpOidc")):
            blocks.append("desktop_remote_or_helper_authentication")
        layer(path.parent / "_meta.json")
        notices.append("此配置是否已应用由原生配置库选择项决定；本工具保留 _meta.json，加载前从界面核对")
    return {"layers": layers, "blocks": sorted(set(blocks)), "notices": notices, "environment": environment}


def inspect(client, cwd, config=None):
    selected = [allowed_file(client, config, cwd)] if config else files(client, cwd)
    reports = []
    for path in selected:
        try:
            data, _, snap = load(path, client)
            records = entries(data, client)
            for entry in records:
                entry.update(observations(client, path, data, entry["selector"], cwd))
            selection = {}
            if client in ("codex", "chatgpt"):
                selection = {"model": data.get("model"), "provider": data.get("model_provider"),
                             "profile": None if path.name == "config.toml" else path.name.removesuffix(".config.toml")}
            elif client == "hermes":
                current = _mapping(data, "model")
                selection = {"model": current.get("default"), "provider": current.get("provider")}
            elif client == "claude-code":
                selection = {"model": data.get("model")}
            reports.append({"path": str(path), "snapshot": snap, "entries": records,
                            "file_selection": selection, "effective_source": "requires_target_session_check"})
        except SetupError as exc:
            reports.append({"path": str(path), "problem": exc.reason})
    return {"client": client, "name": NAMES[client], "cwd": str(Path(cwd).absolute()), "files": reports,
            "verification": {"inspection": "local_only", "client_loaded": "not_verified", "model_call": "not_run"}}


def _extend(existing, ids):
    if not isinstance(existing, list):
        raise SetupError("native_model_list_invalid")
    result = copy.deepcopy(existing)
    present = [x.get("name") if isinstance(x, dict) else x for x in result]
    result.extend(mid for mid in ids if mid not in present)
    return result


def transform(data, request, models, key):
    """key=None preserves existing credentials. This function never persists values."""
    client, selector = request["client"], request["selector"]
    data = copy.deepcopy(data)
    ids = [m["id"] for m in models]
    default = request.get("default_model")
    protocol = request["protocol"]
    base = "https://api.aihubmax.com" + ("" if protocol == "anthropic-messages" else "/v1")
    secret_paths = []
    if client == "workbuddy":
        if default:
            raise SetupError("workbuddy_default_requires_native_picker")
        if not request["new"] and len(ids) != 1:
            raise SetupError("existing_workbuddy_record_requires_one_model")
        for model in models:
            if request["new"]:
                item = {"name": request["name"] if len(models) == 1 else request["name"] + " · " + model["name"], "vendor": "Custom"}
                index = len(data)
                data.append(item)
            else:
                index = int(selector)
                item = data[index]
            changed_model = item.get("id") != model["id"]
            item.update(id=model["id"], url=base, useCustomProtocol=False)
            caps = next(r["capabilities"] for r in model["routes"] if r["protocol"] == protocol)
            for field, cap in (("supportsToolCall", "tool_calling"), ("supportsImages", "image_input")):
                if caps[cap] is not None:
                    item[field] = caps[cap]
                elif changed_model:
                    # Old model capabilities are not evidence about a new model.
                    # Omission delegates to the native picker without claiming support.
                    item.pop(field, None)
            if key is not None:
                item["apiKey"] = key
            secret_paths.append([index, "apiKey"])
    elif client in ("codex", "chatgpt"):
        if len(ids) > 1:
            raise SetupError("client_profile_requires_one_model")
        if not default and data.get("model") != ids[0]:
            raise SetupError("client_profile_model_choice_required")
        providers = data.setdefault("model_providers", {})
        item = providers.setdefault(selector, {})
        item.update(name=request.get("name", item.get("name", selector)), base_url=base, wire_api="responses")
        if key is not None:
            item["experimental_bearer_token"] = key
        secret_paths = [["model_providers", selector, "experimental_bearer_token"]]
        if default:
            data.update(model=default, model_provider=selector)
    elif client == "hermes":
        if selector == "$model":
            if len(ids) > 1:
                raise SetupError("hermes_bare_model_requires_one_selection")
            item = data.setdefault("model", {})
            if not default and (item.get("default") != ids[0] or item.get("provider") != "custom"):
                raise SetupError("hermes_bare_model_requires_default_choice")
            item.update(base_url=base, provider="custom", api_mode=TRANSPORT[protocol])
            if default:
                item["default"] = default
            secret_paths = [["model", "api_key"]]
        else:
            item = data.setdefault("providers", {}).setdefault(selector, {})
            item.update(api=base, transport=TRANSPORT[protocol], discover_models=False)
            if request.get("name"):
                item["name"] = request["name"]
            existing = item.setdefault("models", {})
            if isinstance(existing, dict):
                for mid in ids:
                    existing.setdefault(mid, {})
            elif isinstance(existing, list):
                item["models"] = _extend(existing, ids)
            else:
                raise SetupError("native_model_list_invalid")
            if default:
                if item.get("enabled") is False:
                    item["enabled"] = True
                item["default_model"] = default
                data.setdefault("model", {}).update(provider="custom:" + selector, default=default)
            secret_paths = [["providers", selector, "api_key"]]
        if key is not None:
            item["api_key"] = key
    elif client == "claude-code":
        env = data.setdefault("env", {})
        env["ANTHROPIC_BASE_URL"] = base
        if key is not None:
            env["ANTHROPIC_AUTH_TOKEN"] = key
        secret_paths = [["env", "ANTHROPIC_AUTH_TOKEN"]]
        # These are model aliases, not an administrative availableModels allowlist.
        aliases = {"claude-sonnet-5-5": "SONNET", "claude-opus-5-5": "OPUS", "claude-fable-5-1": "FABLE"}
        for mid in ids:
            if mid in aliases:
                env["ANTHROPIC_DEFAULT_" + aliases[mid] + "_MODEL"] = mid
            elif mid != default:
                raise SetupError("custom_claude_model_requires_default_choice")
        if default:
            data["model"] = default
    else:
        data.update(inferenceProvider="gateway", inferenceGatewayBaseUrl=base,
                    inferenceGatewayAuthScheme="bearer", inferenceCredentialKind="static")
        if key is not None:
            data["inferenceGatewayApiKey"] = key
        secret_paths = [["inferenceGatewayApiKey"]]
        existing = data.get("inferenceModels", [])
        if not existing and ids and not default:
            raise SetupError("desktop_first_model_requires_default_choice")
        data["inferenceModels"] = _extend(existing, ids)
        if default:
            result = data["inferenceModels"]
            chosen = next(m for m in result if (m.get("name") if isinstance(m, dict) else m) == default)
            result.remove(chosen)
            result.insert(0, chosen)
    return data, secret_paths


def value_at(data, pointer):
    for segment in pointer:
        try:
            data = data[segment]
        except (KeyError, IndexError, TypeError):
            return None
    return data
