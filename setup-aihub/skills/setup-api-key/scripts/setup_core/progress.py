"""Per-task metadata and durable confirmations. No credential or request bodies."""
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

from .consumers import Consumer, HOSTS, fingerprint, path_id
from .errors import SetupError
from .local_config import checked_path, edit, snapshot, validate_target, transform
from .local_platform import exclusive_lock, private_directory, private_permissions, sync_replaced_file
from .secret_book import compatibility as secret_book_compatibility, inspect_dependency

SCHEMA = "setup-aihub.task/v1"
PHASES = {"installation", "inspection", "waiting_manual", "waiting_secret_book", "waiting_confirmation",
          "applying", "recheck", "completed", "cancelled", "result_unknown"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Tasks:
    def __init__(self):
        self.directory = Path.home() / ".config/setup-aihub/tasks"

    def path(self, task_id):
        if not re.fullmatch(r"[a-f0-9]{32}", task_id):
            raise SetupError("invalid_task_id")
        return checked_path(self.directory / (task_id + ".json"))

    def load(self, task_id):
        path = self.path(task_id)
        try:
            if path.stat().st_size > 1024 * 1024:
                raise SetupError("invalid_progress")
            state = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SetupError("task_not_found") from None
        except (OSError, ValueError):
            raise SetupError("invalid_progress") from None
        allowed = {"schema", "id", "created", "updated", "context", "operation", "source", "phase", "installation",
                   "submission", "plan", "authorization", "result", "secret_book", "last_reason", "business", "selection"}
        if (not isinstance(state, dict) or set(state) - allowed or state.get("schema") != SCHEMA
                or state.get("id") != task_id or state.get("phase") not in PHASES):
            raise SetupError("unsupported_progress_schema")
        return state

    def save(self, state):
        path = self.path(state["id"])
        private_directory(self.directory)
        state["updated"] = now()
        content = (json.dumps(state, ensure_ascii=True, indent=2) + "\n").encode()
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".task-", suffix=".tmp")
        try:
            private_permissions(Path(name), fd=fd)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            checked_path(path)
            os.replace(name, path)
            sync_replaced_file(path, content)
        finally:
            if fd is not None:
                os.close(fd)
            with contextlib.suppress(FileNotFoundError):
                os.unlink(name)

    @contextlib.contextmanager
    def lock(self, key):
        # Stable locks in Setup's non-secret directory keep project sidecars out
        # of Git and serialize this helper across tasks and processes.
        path = checked_path(self.directory / (fingerprint(key) + ".lock"))
        private_directory(self.directory)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            private_permissions(path, fd=fd)
            with exclusive_lock(fd, timeout=15):
                yield
        finally:
            os.close(fd)

    def start(self, context, operation, source, installation, submission, business=None):
        state = {"schema": SCHEMA, "id": uuid.uuid4().hex, "created": now(), "context": context,
                 "operation": operation, "source": source, "installation": installation,
                 "submission": submission, "business": business or {},
                 "phase": "inspection" if context.get("root") else "installation"}
        self.save(state)
        return state

    def matches(self, host, cwd, plugin=None):
        # Read-only: a status query must not create the progress directory.
        results = []
        if not self.directory.exists():
            return results
        checked_path(self.directory / "probe")
        for path in sorted(self.directory.glob("*.json")):
            state = self.load(path.stem)
            if state["phase"] in ("completed", "cancelled"):
                continue
            context = state["context"]
            if (context["host"] == host and context["platform"] == os.name and path_id(context["cwd"]) == path_id(cwd)
                    and path_id(context["home"]) == path_id(Path.home()) and (plugin is None or context["plugin"] == plugin)):
                results.append({"id": state["id"], "plugin": context["plugin"], "phase": state["phase"], "updated": state["updated"]})
        return results


def guard_context(state, host, cwd):
    context = state["context"]
    if (host not in HOSTS or context["host"] != host or context["platform"] != os.name
            or path_id(context["home"]) != path_id(Path.home().resolve()) or path_id(context["cwd"]) != path_id(Path(cwd).resolve())):
        raise SetupError("task_context_mismatch")


def consumer_for(state):
    context = state["context"]
    if not context.get("root"):
        raise SetupError("plugin_location_required")
    consumer = Consumer.from_context(context)
    if consumer.context(context["host"]) != context:
        raise SetupError("artifact_changed_refresh_required")
    return consumer


def pending_delegation(state):
    delegation = state.get("secret_book", {})
    return delegation.get("delegated") is True and delegation.get("status") in ("pending", "unknown")


def active(state, *, accept_delegated_result=False):
    if state["phase"] in ("completed", "cancelled"):
        raise SetupError("task_closed")
    if state["phase"] in ("applying", "result_unknown"):
        raise SetupError("reconcile_before_retry")
    if pending_delegation(state) and not accept_delegated_result:
        raise SetupError("secret_book_owns_write")


def make_plan(tasks, state, target, fields):
    active(state)
    if state["source"] != "manual":
        raise SetupError("secret_book_owns_write")
    action = "clear" if state["operation"] == "clear" else "prepare"
    if state["operation"] == "check":
        raise SetupError("check_is_read_only")
    consumer = consumer_for(state)
    report = consumer.inspect()
    target_snapshot = validate_target(consumer, report, target, fields, action)
    plan = {"action": action, "target": target_snapshot["path"], "fields": fields,
            "context": state["context"], "inspection": report, "target_snapshot": target_snapshot,
            "shared_effect": "same_os_user_and_runtime_across_hosts" if path_id(target_snapshot["path"]).startswith(path_id(Path.home() / ".config") + os.sep) else "calling_project"}
    if consumer.name == "tikin-social":
        plan["association_review"] = "confirm_key_belongs_to_effective_service_before_using_it"
    if action == "clear":
        projection = consumer.inspect({"target": target_snapshot["path"], "fields": fields})
        if projection["before"] != report:
            raise SetupError("sources_changed")
        plan["projection"] = projection
    if snapshot(target) != target_snapshot:
        raise SetupError("target_changed")
    plan["confirmation"] = fingerprint(plan)
    state["plan"], state["phase"] = plan, "waiting_confirmation"
    state["selection"] = {"target": plan["target"], "fields": fields}
    state.pop("authorization", None)
    state.pop("last_reason", None)
    tasks.save(state)
    return state


def apply_plan(tasks, state, confirmation):
    active(state)
    if state["source"] != "manual" or state["phase"] != "waiting_confirmation":
        raise SetupError("no_pending_confirmation")
    plan = state.get("plan", {})
    unsigned = {key: value for key, value in plan.items() if key != "confirmation"}
    if not confirmation or confirmation != plan.get("confirmation") or fingerprint(unsigned) != confirmation:
        raise SetupError("confirmation_mismatch")
    with tasks.lock({"target": path_id(plan["target"])}):
        consumer = consumer_for(state)
        if consumer.inspect() != plan["inspection"] or state["context"] != plan["context"]:
            raise SetupError("sources_changed")
        if snapshot(plan["target"]) != plan["target_snapshot"]:
            raise SetupError("target_changed")
        state["phase"], state["authorization"] = "applying", confirmation
        tasks.save(state)  # A crash after this point requires inspection, never replay.
        try:
            result = edit(plan)
            state["result"] = result
            state["phase"] = "waiting_manual" if plan["action"] == "prepare" else "recheck"
            tasks.save(state)
            if plan["action"] == "clear":
                return recheck(tasks, state)
        except BaseException:
            state["phase"] = "result_unknown"
            with contextlib.suppress(Exception):
                tasks.save(state)
            raise
    return state


def result_layers(state, report):
    return {"local": report, "online_authentication": "not_performed", "business_call": "not_verified",
            "host_installation": state["installation"], "host_loading": "not_verified",
            "business_next_step": {"not_submitted": "return_and_check_original_authorization", "submitted": "query_existing_result",
                                   "unknown": "reconcile_submission"}[state["submission"]]}


def recheck(tasks, state, reconcile=False):
    if state["phase"] in ("applying", "result_unknown") and not reconcile:
        raise SetupError("reconcile_before_retry")
    if pending_delegation(state):
        raise SetupError("secret_book_owns_write")
    consumer = consumer_for(state)
    report = consumer.inspect()
    previous = state.get("result", {})
    state["result"] = {**previous, **result_layers(state, report)}
    if (not reconcile and state["phase"] == "waiting_manual" and state.get("plan", {}).get("action") == "prepare"
            and snapshot(state["plan"]["target"])["revision"] == previous.get("revision")):
        state["last_reason"] = "manual_change_not_observed"
        tasks.save(state)
        return state
    if reconcile:
        # This read establishes the current outcome, not a claim that a previous
        # write succeeded. Drop the old confirmation; user can plan a new action.
        state["phase"] = "inspection"
        state.pop("plan", None)
        state.pop("authorization", None)
        state["result"]["write_outcome"] = "review_current_file_before_new_action"
    elif state["operation"] == "clear":
        plan = state.get("plan", {})
        if state["phase"] != "recheck" or plan.get("action") != "clear":
            state["phase"] = "inspection"
            tasks.save(state)
            return state
        path = checked_path(plan["target"])
        raw = path.read_bytes() if path.exists() else b""
        if transform(raw, plan["fields"], "clear") != raw:
            state["phase"] = "inspection"
            state["last_reason"] = "selected_fields_still_present"
        else:
            state["phase"] = "completed"
        state["result"]["deletion_effect_matches_preview"] = report["fields"] == plan["projection"]["after"]["fields"]
    else:
        state["phase"] = "completed" if report["status"] == "ok" else "inspection"
    if state["phase"] == "completed":
        state.pop("last_reason", None)
    tasks.save(state)
    return state


def secret_book_handoff(tasks, state, dependency_root):
    active(state)
    if state["source"] != "secret-book" or state["operation"] not in ("configure", "repair"):
        raise SetupError("invalid_secret_book_operation")
    consumer = consumer_for(state)
    dependency = inspect_dependency(dependency_root, consumer.caller)
    report = consumer.inspect()
    state["phase"] = "waiting_secret_book"
    state["secret_book"] = {"status": "pending", "contract": "secret-book/" + secret_book_compatibility(consumer.caller)["minimum_verified_release"],
                            "reference": None, "delegated": True, "dependency": dependency}
    tasks.save(state)
    return {"task": state, "handoff": {"consumer": report["consumer"], "version": consumer.version,
            "skill": consumer.caller, "cwd": str(consumer.cwd), "global_enabled": consumer.global_enabled,
            "declaration_path": str(consumer.declaration_path), "inspection": report,
            "operation": state["operation"], "selection": state.get("selection"), "role": "consumer", "remote_access": "read_only",
            "writer": "secret-book", "dependency": dependency, **secret_book_compatibility(consumer.caller),
            "required_capabilities": ["consumer_role", "read_only_existing_table_connection", "no_record_id_backfill", "public_resume"]}}


def secret_book_result(tasks, state, status, reference=None):
    active(state, accept_delegated_result=True)
    if (state["source"] != "secret-book" or state["phase"] != "waiting_secret_book"
            or state.get("secret_book", {}).get("delegated") is not True):
        raise SetupError("no_secret_book_handoff")
    if reference is not None and not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", reference):
        raise SetupError("invalid_public_reference")
    state["secret_book"] = {**state["secret_book"], "status": status,
                            "reference": reference or state["secret_book"].get("reference")}
    # Persist a public completion before the local read. If that read fails, the
    # next turn must retry verification, not ask the other writer to save again.
    tasks.save(state)
    if status == "completed":
        # A reported save is independently checked, even in contract simulations.
        state = recheck(tasks, state)
    else:
        state["phase"] = "cancelled" if status == "cancelled" else "waiting_secret_book"
        tasks.save(state)
    return state
