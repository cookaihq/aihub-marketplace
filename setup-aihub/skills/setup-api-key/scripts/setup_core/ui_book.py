"""UI adapter for the checksum-pinned Secret Book core (MIT).

The dependency is an unmodified source snapshot, not an installed Skill. Only
read operations and local connection saves are exposed. Secrets stay in memory.
"""
import contextlib
import dataclasses
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlsplit

from .consumers import fingerprint
from .errors import SetupError
from .local_config import checked_path, snapshot, same_snapshot, git_safe, replace_content

ROOT = Path(__file__).resolve().parents[2]
READ_SCOPES = "base:app:read base:table:read base:field:read base:record:read"


def load_core():
    cached = sys.modules.get("_setup_secret_book")
    if cached:
        return cached
    directory = ROOT / "vendor/secret_book"
    manifest = json.loads((directory / "UPSTREAM.json").read_text())
    for name, digest in manifest["files"].items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise SetupError("secret_book_dependency_changed")
    # The bundled dependency has no third-party packages. Its own bootstrap is
    # satisfied by Setup's already checked, locked Python 3.13 environment.
    previous = os.environ.get("UV_PROJECT_ENVIRONMENT")
    os.environ["UV_PROJECT_ENVIRONMENT"] = sys.prefix
    sys.path.insert(0, str(directory / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("_setup_secret_book", directory / "scripts/secret_book.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        importlib.import_module("consumers")
        return module
    finally:
        if previous is None:
            os.environ.pop("UV_PROJECT_ENVIRONMENT", None)
        else:
            os.environ["UV_PROJECT_ENVIRONMENT"] = previous
        sys.path.pop(0)


class Book:
    def __init__(self, metadata):
        self.metadata = metadata
        self.api = None
        self.deadline = 0
        self.login = None

    @contextlib.contextmanager
    def operation(self):
        self.api = load_core()
        self.deadline = time.monotonic() + 120
        self.api._lark_exec = self.execute
        # Upstream human CLI output is not a browser/API contract. Suppress it,
        # including errors which might contain arbitrary remote response text.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                yield
            except self.api.ProfileGuidance as exc:
                data = exc.payload
                reason = data.get("status", "secret_book_unavailable")
                code = data.get("error_kind")
                if code == "feishu_identity_mismatch":
                    raise SetupError("identity_changed", expected=data.get("expected_identity"), observed=data.get("observed_identity")) from None
                if code in ("feishu_profile_not_authenticated", "feishu_profile_not_found"):
                    raise SetupError("login_required") from None
                if reason not in ("missing_keys", "record_unavailable", "table_fields_missing", "related_fields_differ"):
                    reason = code if isinstance(code, str) and code.startswith("feishu_") else "secret_book_unavailable"
                raise SetupError(reason) from None
            except SystemExit:
                raise SetupError("secret_book_configuration_invalid") from None
            finally:
                self.api._SENSITIVE.clear()

    def execute(self, argv, kind="read", what="read", **_):
        # This adapter never exposes a remote mutation, including through a
        # dependency's internal call. Auth is handled separately below.
        if kind != "read":
            raise SetupError("remote_write_refused")
        retry_at = self.metadata.get("retry_at", 0)
        if retry_at > time.time():
            raise SetupError("rate_limited", retry_at=retry_at)
        for attempt in range(3):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise SetupError("network_budget")
            try:
                proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=min(30, remaining))
            except FileNotFoundError:
                raise SetupError("lark_unavailable") from None
            except subprocess.TimeoutExpired:
                if attempt == 2:
                    raise SetupError("network_budget") from None
                proc = subprocess.CompletedProcess(argv, 1, "", '{"ok":false,"error":{"type":"network","subtype":"timeout"}}')
            except OSError:
                raise SetupError("lark_unavailable") from None
            if proc.returncode == 0:
                return proc
            error = self.api._lark_error(proc)
            transient = ((error.get("type") == "network" and error.get("subtype") in ("timeout", "transport", "dns", "server_error"))
                         or (error.get("type") == "api" and error.get("subtype") in ("server_error", "rate_limit")))
            if not transient:
                return proc
            wait = 2 ** attempt
            details = error.get("details") if isinstance(error.get("details"), dict) else {}
            raw = error.get("retry_after", details.get("retry_after"))
            if raw is not None:
                try:
                    wait = max(0, float(raw))
                except (ValueError, TypeError):
                    try:
                        wait = max(0, parsedate_to_datetime(raw).timestamp() - time.time())
                    except (ValueError, TypeError, OverflowError):
                        pass
            self.metadata["retry_at"] = time.time() + wait
            if attempt == 2:
                if error.get("subtype") == "rate_limit":
                    raise SetupError("rate_limited", retry_at=self.metadata["retry_at"])
                return proc
            if wait > min(5, self.deadline - time.monotonic()):
                raise SetupError("rate_limited", retry_at=self.metadata["retry_at"])
            time.sleep(wait)
        raise SetupError("network_budget")

    def prepare(self):
        executable = shutil.which("lark-cli")
        local = Path.home() / ".config/setup-aihub/tools/lark"
        candidates = [local / ("node_modules/@larksuite/cli/bin/lark-cli.exe" if os.name == "nt" else "node_modules/.bin/lark-cli")]
        if not executable:
            executable = next((str(path) for path in candidates if path.is_file()), None)
        if not executable:
            npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
            if not npm:
                raise SetupError("lark_prepare_failed")
            # Prepare only the user-owned dependency; no global package changes.
            try:
                proc = subprocess.run([npm, "install", "--prefix", str(local), "@larksuite/cli@1.0.82", "--no-audit", "--no-fund"],
                                      capture_output=True, timeout=180)
            except (OSError, subprocess.TimeoutExpired):
                raise SetupError("lark_prepare_failed") from None
            executable = next((str(path) for path in candidates if path.is_file()), None)
            if not executable or proc.returncode:
                raise SetupError("lark_prepare_failed")
        try:
            probe = subprocess.run([executable, "--version"], capture_output=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            raise SetupError("lark_unavailable") from None
        if probe.returncode:
            raise SetupError("lark_unavailable")
        os.environ["PATH"] = str(Path(executable).parent) + os.pathsep + os.environ.get("PATH", "")
        return {"ready": True}

    def profiles(self):
        with self.operation():
            proc = self.execute(["lark-cli", "profile", "list"])
            if proc.returncode:
                raise SetupError("lark_unavailable")
            items = json.loads(proc.stdout)
            if not isinstance(items, list):
                raise SetupError("lark_unavailable")
            return [{key: item.get(key) for key in ("name", "appId", "user", "tokenStatus")} for item in items]

    def connections(self):
        with self.operation():
            api = self.api
            # Check high-priority sources before offering the global list. Partial
            # or invalid project records must not be hidden by a new connection.
            layers, values = api._config_layers(True)
            explicit = any(any(v.get(k) for k in api.RESOURCE_ENV_KEYS) for _, v in layers)
            if explicit:
                snap = api.resolve_config_snapshot(True)
                return [{"id": "source", "name": snap.source, "profile": snap.lark_profile, "source": snap.source}]
            store = api._load_named_config_store(values)
            if any(values.get(k) for k in api.RESOURCE_ENV_KEYS):
                raise SetupError("secret_book_configuration_invalid")
            return [{"id": cid, "name": row["name"], "profile": row["lark_profile"],
                     "app_id": row["feishu_app_id"], "user_id": row["feishu_user_open_id"],
                     "source": str(api.global_config_path()), "table_id": row["table_id"]}
                    for cid, row in store["configs"].items()]

    def args(self, connection):
        if connection == "source":
            return SimpleNamespace(use_global_config=True, config_name=None)
        api = self.api
        store = api._load_named_config_store(api._parse_env_file(api.global_config_path()))
        record = store["configs"].get(connection)
        if not record:
            raise SetupError("secret_book_configuration_invalid")
        return SimpleNamespace(use_global_config=True, config_name=record["name"])

    def records(self, connection):
        with self.operation():
            backend = self.api.require_backend(self.args(connection))
            self.api._inspect_connection(backend)
            items = backend.list_records()
            return [{key: row.get(key, "") for key in ("id", "name", "service", "account", "purpose", "expires_at")}
                    for row in items]

    def fields(self, connection, record_id):
        with self.operation():
            backend = self.api.require_backend(self.args(connection))
            rows = backend.find("id", record_id, with_secret=True)
            if len(rows) != 1 or not record_id:
                raise SetupError("record_unavailable")
            row = rows[0]
            if row.get("expires_at") and row["expires_at"][:10] < date.today().isoformat():
                raise SetupError("record_unavailable")
            values = self.api.parse_payload(row["secret"], allow_empty=True)
            return [{"key": key, "present": bool(value.strip())} for key, value in values.items()]

    def values(self, connection, record_id, mapping, consumer, selected):
        with self.operation():
            from consumers import Configuration
            args = self.args(connection)
            args.requirements = str(consumer.declaration_path)
            args.map = [target + "=" + source for target, source in mapping.items()]
            args.key = selected
            config = Configuration(self.api, args)
            snap = self.api._snapshot_for_args(args)
            if snap.ids:
                raise SetupError("secret_book_configuration_invalid")
            # Revalidate expiry and uniqueness before every preview/confirmation.
            backend = self.api.require_backend(args)
            rows = backend.find("id", record_id, with_secret=False)
            if len(rows) != 1 or not record_id or (rows[0].get("expires_at") and rows[0]["expires_at"][:10] < date.today().isoformat()):
                raise SetupError("record_unavailable")
            values, metadata = config.records(snap, [record_id], config.mapping())
            # Group association remains the upstream contract, including defaults.
            report = consumer.inspect()
            from .ui_model import effective_values
            actual = effective_values(report, consumer.declaration)
            for group in consumer.declaration.get("groups", []):
                if set(group).intersection(selected) and any(values.get(k) != actual.get(k) for k in group if k not in selected):
                    raise SetupError("related_fields_differ")
            return {k: values[k] for k in selected}, {"source": dataclasses.asdict(snap), **metadata}

    def identity(self, profile):
        with self.operation():
            observed = self.api._capture_profile_identity(profile)
            return {k: v for k, v in observed.items() if not k.startswith("_")}

    def connect(self, profile, identity, url):
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or not parts.hostname.endswith((".feishu.cn", ".larksuite.com"))):
            raise SetupError("invalid_url")
        with self.operation():
            current = self.api._capture_profile_identity(profile)
            self.api._assert_profile_identity(identity, current)
            backend = self.api._resolve_table_url(url, profile, current)
            result = self.api._inspect_connection(backend)
            return {"app_token": result["app_token"], "table_id": result["table_id"], "identity": identity,
                    "url": url, "target": snapshot(self.api.global_config_path())}

    def rebind_preview(self, connection, identity):
        with self.operation():
            api = self.api
            if connection == "source":
                raise SetupError("repair_book_source")
            target = api.global_config_path()
            expected = snapshot(target)
            store = api._load_named_config_store(api._parse_env_file(target))
            row = store["configs"].get(connection)
            if not row:
                raise SetupError("secret_book_configuration_invalid")
            current = api._capture_profile_identity(identity["lark_profile"])
            api._assert_profile_identity(identity, current)
            backend = api.FeishuBackend(row["app_token"], row["table_id"], identity["lark_profile"], identity["open_id"], identity=current)
            api._inspect_connection(backend)
            same_snapshot(expected)
            return {"connection": connection, "name": row["name"], "app_token": row["app_token"],
                    "table_id": row["table_id"], "identity": identity, "target": expected,
                    "previous_identity": {k: row[k] for k in ("lark_profile", "feishu_app_id", "feishu_user_open_id")}}

    def save_connection(self, preview, name):
        with self.operation():
            api = self.api
            identity = api._capture_profile_identity(preview["identity"]["lark_profile"])
            api._assert_profile_identity(preview["identity"], identity)
            target = checked_path(api.global_config_path())
            with api._config_file_lock(target):
                current_target = same_snapshot(preview["target"], allow_new_parents=True)
                values = api._parse_env_file(target)
                store = api._load_named_config_store(values)
                api._validate_config_name(name)
                cid = preview.get("connection")
                if any(row["name"] == name and key != cid for key, row in store["configs"].items()) or any(values.get(k) for k in api.RESOURCE_ENV_KEYS):
                    raise SetupError("secret_book_configuration_invalid")
                if cid and cid not in store["configs"]:
                    raise SetupError("sources_changed")
                cid = cid or api._new_config_id(store["configs"])
                store["configs"][cid] = {"name": name, "app_token": preview["app_token"], "table_id": preview["table_id"],
                    "lark_profile": identity["lark_profile"], "feishu_app_id": identity["app_id"], "feishu_user_open_id": identity["open_id"]}
                if store["active_id"] is None:
                    store["active_id"] = cid
                from .ui_model import dotenv_content
                raw = target.read_bytes() if target.exists() else b""
                content = dotenv_content(raw, {api.ENV_CONFIGS_JSON: api._named_config_json(store)})
                replace_content(current_target, content)
                return cid

    def start_login(self, profile):
        if profile not in {row["name"] for row in self.profiles()}:
            raise SetupError("no_application")
        if self.login and self.login["expires"] > time.time():
            raise SetupError("login_pending")
        try:
            proc = subprocess.run(["lark-cli", "auth", "login", "--profile", profile, "--scope", READ_SCOPES, "--no-wait", "--json"], capture_output=True, text=True, timeout=30)
            data = json.loads(proc.stdout)
            if proc.returncode or not data.get("device_code") or not data.get("verification_url"):
                raise ValueError()
            url = urlsplit(data["verification_url"])
            if url.scheme != "https" or not url.hostname or not url.hostname.endswith((".feishu.cn", ".larksuite.com")):
                raise ValueError()
            self.login = {"profile": profile, "code": data["device_code"], "expires": time.time() + int(data["expires_in"])}
            return {"profile": profile, "url": data["verification_url"], "expires": self.login["expires"]}
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            raise SetupError("login_pending") from None

    def finish_login(self):
        if not self.login or self.login["expires"] <= time.time():
            self.login = None
            raise SetupError("login_expired")
        login = self.login
        try:
            proc = subprocess.run(["lark-cli", "auth", "login", "--profile", login["profile"], "--device-code", login["code"], "--json"], capture_output=True, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            raise SetupError("login_pending") from None
        if proc.returncode:
            raise SetupError("login_pending")
        self.login = None
        return self.identity(login["profile"])
