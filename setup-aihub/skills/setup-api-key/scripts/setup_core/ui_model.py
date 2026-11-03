"""Production browser workflow using the existing business loaders and writers."""
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from .consumers import Consumer, fingerprint, path_id
from .errors import SetupError
from .local_config import ASSIGNMENT, checked_path, snapshot, validate_target, transform, replace_content
from .progress import Tasks, consumer_for, guard_context, active, recheck
from .ui_storage import write_json
from .ui_book import Book

SERVICES = {"aihub-studio": {"name": "AIhub Studio", "key": "AIHUB_API_KEY"},
            "tikin-social": {"name": "Tikin Social", "key": "TIKIN_API_KEY"}}


def dotenv_content(raw, values):
    # Reuse the existing parser/format guard, preserving unrelated bytes and BOM.
    content = transform(raw, list(values), "clear")
    newline = b"\r\n" if b"\r\n" in raw else b"\n"
    if content and content != b"\xef\xbb\xbf" and not content.endswith(b"\n"):
        content += newline
    for key, value in values.items():
        content += (key + "='" + value + "'").encode("utf-8") + newline
    return content


def effective_values(report, declaration):
    """Internal association check; never returned to the browser or persisted."""
    result = {}
    for key, row in report["fields"].items():
        source = row["source"]
        if source == "environment":
            result[key] = os.environ.get(key)
        elif source == "built-in default":
            result[key] = declaration["keys"][key].get("default")
        elif source != "missing":
            for line in checked_path(source).read_text(encoding="utf-8-sig").splitlines():
                match = ASSIGNMENT.fullmatch(line)
                if match and match[1] == key:
                    value = match[2]
                    result[key] = value[1:-1] if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0] else value
    return result


def checked_values(values, fields):
    if not isinstance(values, dict) or not values or not set(values) <= set(fields):
        raise SetupError("invalid_input")
    result = {}
    for key, value in values.items():
        if (not isinstance(value, str) or not value.strip() or len(value) > 8192
                or value != value.strip() or any(ord(c) < 32 or c in "\x7f\x85\u2028\u2029" for c in value)):
            raise SetupError("invalid_input")
        if key == "TIKIN_BASE_URL":
            p = urlsplit(value)
            if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment:
                raise SetupError("invalid_url")
        result[key] = value
    return result


class ConfigurationUI:
    def __init__(self, directory, options):
        self.directory = Path(directory)
        self.options = options
        self.lock = threading.RLock()
        self.tasks = Tasks()
        self.values = {}
        self.salt = secrets.token_bytes(32)
        self.preview = None
        self.connection_preview = None
        self.confirmed_identity = None
        path = self.directory / "progress.json"
        if path.exists():
            state = json.loads(path.read_text())
            if state.get("schema") != "setup-aihub.web/v1" or state.get("context") != options:
                raise SetupError("task_context_mismatch")
            self.state = state
        else:
            services = options["services"]
            if not services:
                raise SetupError("no_services")
            self.state = {"schema": "setup-aihub.web/v1", "context": options, "service": options.get("plugin") or next(iter(services)),
                          "source": options.get("source", "manual"), "scope": options.get("scope") or ("global" if options["global_enabled"] else "project"),
                          "phase": "connections" if options.get("source") == "secret-book" else "manual",
                          "task_id": options.get("task"), "book": {}, "receipt": None}
        self.book = Book(self.state["book"])
        if self.state["phase"] in ("review", "identity", "connection_review", "authorizing"):
            self.state["phase"] = "manual" if self.state["source"] == "manual" else "connections"
        if self.state.get("task_id"):
            state = self.task()
            if state["phase"] in ("applying", "result_unknown"):
                self.state["phase"] = "uncertain"
            elif state["phase"] == "completed":
                self.state["phase"] = "done"
        self.save()

    def save(self):
        write_json(self.directory / "progress.json", self.state)

    def consumer(self):
        name = self.state["service"]
        config = self.options["services"][name]
        return Consumer(name, config["root"], config.get("caller"), self.options["cwd"], self.options["global_enabled"])

    def task(self):
        state = self.tasks.load(self.state["task_id"])
        guard_context(state, self.options["host"], self.options["cwd"])
        if state["context"]["plugin"] != self.state["service"]:
            raise SetupError("task_context_mismatch")
        return state

    def ensure_task(self):
        if self.state.get("task_id"):
            task = self.task()
            if task["phase"] not in ("completed", "cancelled"):
                active(task)
                task["source"] = self.state["source"]
                return task
        consumer = self.consumer()
        task = self.tasks.start(consumer.context(self.options["host"]), self.options.get("operation", "configure"),
            self.state["source"], self.options["services"][consumer.name].get("installation", "unknown"),
            self.options.get("submission", "unknown"), self.options.get("business", {}))
        self.state["task_id"] = task["id"]
        return task

    def public(self):
        # Explicit allowlist. No raw task state, file bytes, values, environment,
        # login device code or volatile confirmation digest leaves this object.
        result = {k: self.state.get(k) for k in ("service", "source", "scope", "phase", "task_id", "receipt", "connections", "records", "fields", "record_id", "mapping", "profiles", "identity", "error")}
        result["services"] = {k: SERVICES[k] for k in self.options["services"]}
        result["key_present"] = bool(self.values)
        result["global_enabled"] = self.options["global_enabled"]
        result["preview"] = self.preview["public"] if self.preview else None
        result["connection_preview"] = self.connection_preview["public"] if self.connection_preview else None
        result["login"] = self.state.get("login") if self.book.login else None
        result["connection"] = self.state["book"].get("connection")
        return result

    def discard(self):
        self.values.clear()
        self.preview = None
        self.connection_preview = None

    def inspect(self):
        report = self.consumer().inspect()
        self.state["inspection"] = report
        return report

    def plan(self, scope):
        if self.state["phase"] == "uncertain":
            raise SetupError("reconcile_before_retry")
        if scope not in ("global", "project"):
            raise SetupError("invalid_input")
        consumer = self.consumer()
        book_meta = None
        if self.state["source"] == "secret-book":
            selected = list(self.state.get("mapping", {}))
            self.values, book_meta = self.book.values(self.state["book"]["connection"], self.state["record_id"], self.state["mapping"], consumer, selected)
        values = checked_values(self.values, consumer.adapter["fields"])
        report = consumer.inspect()
        task = self.ensure_task()
        # An explicit new preview refreshes the same caller's installed artifact.
        # The prior confirmation remains unusable; no saved selection is replayed.
        task["context"] = consumer.context(self.options["host"])
        groups = {}
        selection = task.get("selection", {})
        for key in values:
            source = report["fields"][key]["source"]
            if source == "environment":
                raise SetupError("repair_environment_at_injection_source", field=key)
            if source in ("missing", "built-in default"):
                if selection.get("target") and key in selection.get("fields", []):
                    target = Path(selection["target"])
                else:
                    target = consumer.cwd / ".env.local" if scope == "project" else Path.home() / ".config" / consumer.name / ".env"
            else:
                target = Path(source)
            groups.setdefault(str(target), {})[key] = values[key]
        targets = []
        for target, selected in groups.items():
            snap = validate_target(consumer, report, target, list(selected), "prepare")
            path = Path(target)
            content = dotenv_content(path.read_bytes() if path.exists() else b"", selected)
            targets.append({"snapshot": snap, "fields": list(selected), "after": hashlib.sha256(content).hexdigest()})
        public = {"id": secrets.token_urlsafe(24), "service": SERVICES[consumer.name]["name"], "source": self.state["source"],
                  "scope": scope, "targets": [{"path": t["snapshot"]["path"], "fields": t["fields"],
                    "changes": [{"key": k, "source": report["fields"][k]["source"], "operation": "replace" if report["fields"][k]["present"] else "add"} for k in t["fields"]]} for t in targets],
                  "caller": consumer.caller, "cwd": str(consumer.cwd), "book": book_meta,
                  "shared_effect": "同一系统用户的各 Agent 共用所选配置；项目来源仍优先。"}
        if consumer.name == "tikin-social":
            address = values.get("TIKIN_BASE_URL") or effective_values(report, consumer.declaration).get("TIKIN_BASE_URL")
            try:
                public["service_address"] = checked_values({"TIKIN_BASE_URL": address}, ["TIKIN_BASE_URL"])["TIKIN_BASE_URL"]
            except SetupError:
                public["service_address"] = "当前服务地址无效，请先修复实际来源。"
        self.preview = {"public": public, "targets": targets, "inspection": report, "context": consumer.context(self.options["host"]),
                        "value_digest": hmac.new(self.salt, json.dumps(values, sort_keys=True).encode(), "sha256").hexdigest()}
        task["phase"] = "waiting_confirmation"
        task["plan"] = {"action": "web_save", "targets": targets, "inspection": report}
        self.tasks.save(task)
        self.state.update(phase="review", scope=scope)

    def confirm(self, token):
        if not self.preview or not isinstance(token, str) or not secrets.compare_digest(token, self.preview["public"]["id"]):
            raise SetupError("confirmation_mismatch")
        old = self.preview
        consumer = self.consumer()
        if self.state["source"] == "secret-book":
            values, meta = self.book.values(self.state["book"]["connection"], self.state["record_id"], self.state["mapping"], consumer, list(self.state["mapping"]))
            if meta != old["public"]["book"]:
                raise SetupError("sources_changed")
            self.values = values
        if not hmac.compare_digest(old["value_digest"], hmac.new(self.salt, json.dumps(self.values, sort_keys=True).encode(), "sha256").hexdigest()):
            self.discard()
            self.state["phase"] = "manual" if self.state["source"] == "manual" else "records"
            raise SetupError("sources_changed")
        task = self.task()
        with self.tasks.lock({"task": task["id"]}), contextlib.ExitStack() as stack:
            task = self.task()
            active(task)
            if (task["phase"] != "waiting_confirmation" or task["source"] != self.state["source"]
                    or task.get("plan") != {"action": "web_save", "targets": old["targets"], "inspection": old["inspection"]}):
                raise SetupError("confirmation_mismatch")
            for target in sorted(old["targets"], key=lambda t: t["snapshot"]["path"]):
                stack.enter_context(self.tasks.lock({"target": path_id(target["snapshot"]["path"])}))
            if consumer.context(self.options["host"]) != old["context"] or consumer.inspect() != old["inspection"]:
                raise SetupError("sources_changed")
            for target in old["targets"]:
                if snapshot(target["snapshot"]["path"]) != target["snapshot"]:
                    raise SetupError("target_changed")
            task["phase"] = "applying"
            task["result"] = {"written": []}
            self.tasks.save(task)
            self.state["phase"] = "uncertain"
            self.save()
            try:
                for target in old["targets"]:
                    path = Path(target["snapshot"]["path"])
                    content = dotenv_content(path.read_bytes() if path.exists() else b"", {k: self.values[k] for k in target["fields"]})
                    result = replace_content(target["snapshot"], content)
                    task["result"]["written"].append({**result, "fields": target["fields"]})
                    self.tasks.save(task)
                task["phase"] = "recheck"
                self.tasks.save(task)
                task = recheck(self.tasks, task)
            except BaseException:
                task["phase"] = "result_unknown"
                self.tasks.save(task)
                self.discard()
                raise
        self.state["receipt"] = {"service": SERVICES[consumer.name]["name"], "written": task["result"]["written"],
            "fields": task["result"]["local"]["fields"], "local_status": task["result"]["local"]["status"],
            "online_authentication": "not_performed", "business_call": "not_verified", "business_next_step": task["result"]["business_next_step"]}
        self.state["phase"] = "done" if task["phase"] == "completed" else "check_result"
        self.discard()

    def action(self, action, payload):
        with self.lock:
            self.state.pop("error", None)
            try:
                return self._action(action, payload)
            finally:
                self.save()

    def _action(self, action, data):
        if self.state["phase"] == "uncertain" and action != "reconcile":
            raise SetupError("reconcile_before_retry")
        if action == "choose":
            service, source = data.get("service"), data.get("source")
            if service not in self.options["services"] or source not in ("manual", "secret-book"):
                raise SetupError("invalid_input")
            if self.state["phase"] == "uncertain":
                raise SetupError("reconcile_before_retry")
            if self.state.get("task_id"):
                current = self.task()
                if current["phase"] not in ("completed", "cancelled"):
                    active(current)
                    if service != self.state["service"]:
                        current["phase"] = "cancelled"
                        self.tasks.save(current)
                        self.state["task_id"] = None
            self.discard()
            self.state.update(service=service, source=source, phase="manual" if source == "manual" else "connections")
            if source == "secret-book":
                self.book.prepare()
                self.state["connections"] = self.book.connections()
                if len(self.state["connections"]) == 1:
                    self.state["book"]["connection"] = self.state["connections"][0]["id"]
                    self.state["records"] = self.book.records(self.state["book"]["connection"])
                    self.state["phase"] = "records"
                elif not self.state["connections"]:
                    self.state["profiles"] = self.book.profiles()
                    self.state["phase"] = "accounts"
        elif action == "manual":
            if self.state["source"] != "manual":
                raise SetupError("invalid_input")
            self.values = checked_values(data.get("values"), self.consumer().adapter["fields"])
            self.plan(data.get("scope"))
        elif action == "preview":
            self.plan(data.get("scope", self.state["scope"]))
        elif action == "save":
            self.confirm(data.get("id"))
        elif action == "back":
            self.preview = None
            self.state["phase"] = "manual" if self.state["source"] == "manual" else "records"
        elif action in ("cancel", "reset"):
            if self.state.get("task_id"):
                task = self.task()
                if task["phase"] not in ("completed", "cancelled"):
                    active(task)
                    task["phase"] = "cancelled"
                    self.tasks.save(task)
            self.discard()
            self.book.login = None
            self.state.update(phase="cancelled" if action == "cancel" else "manual", task_id=None, source="manual")
        elif action == "reconcile":
            task = self.task()
            with self.tasks.lock({"task": task["id"]}):
                task = self.task()
                plan = task.get("plan", {})
                outcomes = [{"path": t["snapshot"]["path"], "matches_saved_content": snapshot(t["snapshot"]["path"])["revision"] == t["after"]} for t in plan.get("targets", [])]
                task["context"] = self.consumer().context(self.options["host"])
                task = recheck(self.tasks, task, reconcile=True)
                self.state["receipt"] = {"reconciled": outcomes, "fields": task["result"]["local"]["fields"], "local_status": task["result"]["local"]["status"]}
                self.state["phase"] = "check_result"
                self.discard()
        elif action in ("connections", "recheck"):
            self.book.prepare()
            self.state["connections"] = self.book.connections()
            self.state["phase"] = "connections"
        elif action == "use-connection":
            connection = data.get("id")
            if connection not in {row["id"] for row in self.book.connections()}:
                raise SetupError("invalid_input")
            self.state["book"]["connection"] = connection
            self.state["records"] = self.book.records(connection)
            self.state.update(phase="records", record_id=None, mapping={}, fields=[])
        elif action == "select-record":
            connection = self.state["book"].get("connection")
            rid = data.get("id")
            if not isinstance(rid, str) or not rid or len(rid) > 200:
                raise SetupError("invalid_input")
            fields = self.book.fields(connection, rid)
            self.state.update(record_id=rid, fields=fields, mapping={})
        elif action == "mapping":
            mapping = data.get("mapping")
            available = {row["key"] for row in self.state.get("fields", []) if row["present"]}
            if not isinstance(mapping, dict) or not mapping or not set(mapping) <= self.consumer().adapter["fields"] or any(v not in available for v in mapping.values()):
                raise SetupError("invalid_input")
            self.state["mapping"] = mapping
        elif action in ("accounts", "repair-connection"):
            self.book.prepare()
            self.state["book"].pop("repair_connection", None)
            if action == "repair-connection":
                connection = data.get("id")
                if connection == "source":
                    raise SetupError("repair_book_source")
                if connection not in {row["id"] for row in self.book.connections()}:
                    raise SetupError("invalid_input")
                self.state["book"]["repair_connection"] = connection
            self.state["profiles"] = self.book.profiles()
            self.state["phase"] = "accounts"
        elif action == "use-account":
            if data.get("profile") not in {p["name"] for p in self.book.profiles()}:
                raise SetupError("invalid_input")
            self.state["book"]["profile"] = data["profile"]
            identity = self.book.identity(data["profile"])
            self.state.update(identity=identity, phase="identity")
            self.confirmed_identity = None
        elif action == "confirm-identity":
            identity = self.book.identity(self.state["book"]["profile"])
            if identity != self.state.get("identity") or data.get("id") != fingerprint(identity):
                raise SetupError("identity_changed")
            self.confirmed_identity = identity
            connection = self.state["book"].get("repair_connection")
            if connection:
                preview = self.book.rebind_preview(connection, identity)
                self.connection_preview = {"private": preview, "public": {"id": secrets.token_urlsafe(24),
                    "name": preview["name"], "table_id": preview["table_id"], "identity": identity,
                    "previous_identity": preview["previous_identity"], "path": preview["target"]["path"]}}
                self.state["phase"] = "connection_review"
            else:
                self.state["phase"] = "table"
        elif action == "connect":
            if not self.confirmed_identity:
                raise SetupError("identity_changed")
            url, name = data.get("url"), data.get("name")
            if not isinstance(url, str) or len(url) > 2048 or not isinstance(name, str) or not name.strip() or len(name) > 80:
                raise SetupError("invalid_input")
            preview = self.book.connect(self.confirmed_identity["lark_profile"], self.confirmed_identity, url)
            self.connection_preview = {"private": preview, "public": {"id": secrets.token_urlsafe(24), "name": name,
                "url": url, "identity": self.confirmed_identity, "path": preview["target"]["path"]}}
            self.state["phase"] = "connection_review"
        elif action == "save-connection":
            if not self.connection_preview or data.get("id") != self.connection_preview["public"]["id"]:
                raise SetupError("confirmation_mismatch")
            try:
                cid = self.book.save_connection(self.connection_preview["private"], self.connection_preview["public"]["name"])
            except (OSError, SetupError):
                self.connection_preview = None
                self.state["phase"] = "connections"
                raise SetupError("connection_save_unconfirmed") from None
            self.state["book"]["connection"] = cid
            self.connection_preview = None
            self.state["connections"] = self.book.connections()
            self.state["records"] = self.book.records(cid)
            self.state["phase"] = "records"
        elif action == "start-login":
            profile = data.get("profile") or self.state["book"].get("profile")
            self.state["book"]["profile"] = profile
            self.state["login"] = self.book.start_login(profile)
            self.state["phase"] = "authorizing"
        elif action == "finish-login":
            self.state["identity"] = self.book.finish_login()
            self.state.pop("login", None)
            self.state["phase"] = "identity"
        elif action == "cancel-login":
            self.book.login = None
            self.state.pop("login", None)
            self.state["phase"] = "accounts"
        else:
            raise SetupError("invalid_action")
        return self.public()
