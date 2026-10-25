"""Persistent confirmation and independent readback. Credentials stay in memory."""
import contextlib
import json
import os
from pathlib import Path
import platform
import secrets
import tempfile

from .common import (SKILL, HOSTS, SetupError, digest, checked_path, private_directory,
                     private_permissions, sync_replaced_file, exclusive_lock, replace_content)
from . import clients, plans


def context(host, cwd):
    if host not in HOSTS:
        raise SetupError("actual_host_required")
    return {"host": host, "cwd": str(Path(cwd).absolute()), "platform": platform.system(), "installation": str(SKILL)}


class Tasks:
    def __init__(self):
        self.root = Path.home() / ".config/setup-aihub/agent-model/tasks"

    def path(self, task):
        if not re_id(task):
            raise SetupError("invalid_task_id")
        return checked_path(self.root / (task + ".json"))

    @contextlib.contextmanager
    def lock(self, identity):
        private_directory(self.root)
        path = checked_path(self.root / (digest(identity) + ".lock"))
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            private_permissions(path, fd=fd)
            with exclusive_lock(fd, timeout=15):
                yield
        finally:
            os.close(fd)

    def save(self, state):
        private_directory(self.root)
        target = self.path(state["id"])
        fd, name = tempfile.mkstemp(dir=self.root, prefix=".state-")
        try:
            private_permissions(Path(name), fd=fd)
            raw = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode()
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, target)
            sync_replaced_file(target, raw)
        finally:
            if fd is not None:
                os.close(fd)
            if os.path.exists(name):
                os.unlink(name)

    def load(self, task, current):
        try:
            state = json.loads(self.path(task).read_bytes())
        except (ValueError, OSError):
            raise SetupError("task_unreadable") from None
        if (not isinstance(state, dict) or state.get("schema") != "setup-agent-model.task/v1"
                or state.get("id") != task or state.get("phase") not in {
                    "waiting_confirmation", "waiting_secret_book", "applying", "result_unknown", "saved", "cancelled", "needs_review"}):
            raise SetupError("unsupported_progress_schema")
        if state["context"] != current:
            raise SetupError("task_context_changed")
        return state

    def start(self, plan, current, source):
        if source not in ("manual", "secret-book", "preserve") or (source == "preserve") != (plan["request"]["key_mode"] == "preserve"):
            raise SetupError("credential_source_mismatch")
        task = {"schema": "setup-agent-model.task/v1", "id": secrets.token_hex(16), "context": current,
                "source": source, "phase": "waiting_secret_book" if source == "secret-book" else "waiting_confirmation",
                "plan": plan, "confirmation_token": secrets.token_hex(24), "secret_book": None, "result": None}
        self.save(task)
        return task

    def list(self, current):
        result = []
        if self.root.exists():
            for path in sorted(self.root.glob("*.json")):
                try:
                    state = self.load(path.stem, current)
                except SetupError:
                    continue
                if state["phase"] != "cancelled":
                    result.append({"id": state["id"], "phase": state["phase"], "client": state["plan"]["request"]["client"]})
        return result


def re_id(value):
    import re
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value)


def write(plan, key):
    plans.revalidate(plan)
    if plan["request"]["key_mode"] == "replace":
        if not isinstance(key, str) or not key.strip() or len(key) > 16384 or any(ord(c) < 32 for c in key):
            raise SetupError("invalid_key_input")
    elif key is not None:
        raise SetupError("unexpected_key_input")
    client = plan["request"]["client"]
    data, raw, _ = clients.load(plan["target"]["path"], client)
    updated, pointers = clients.transform(data, plan["request"], plan["selected_models"], key)
    expected_keys = [clients.value_at(updated, p) for p in pointers]
    result = replace_content(plan["target"], clients.encode(updated, client, raw))
    checked, _, _ = clients.load(plan["target"]["path"], client)
    if [clients.value_at(checked, p) for p in pointers] != expected_keys:
        raise SetupError("key_readback_failed")
    verification = plans.verify(plan)
    if not verification["saved"]:
        raise SetupError("configuration_readback_failed")
    return {"schema": "setup-agent-model.write/v1", "status": "written", "plan_fingerprint": plan["fingerprint"],
            "path": result["path"], "revision": result["revision"], "key_matches": True, "verification": verification}


def apply(tasks, state, token, key):
    if state["source"] == "secret-book":
        raise SetupError("secret_book_is_the_only_writer")
    if state["phase"] != "waiting_confirmation":
        raise SetupError("readback_before_retry")
    if not token or token != state["confirmation_token"]:
        raise SetupError("confirmation_required")
    with tasks.lock(state["plan"]["target"]["path"]):
        fresh = tasks.load(state["id"], state["context"])
        if fresh != state:
            raise SetupError("task_changed")
        plans.revalidate(state["plan"])
        state["phase"] = "applying"
        tasks.save(state)
        try:
            result = write(state["plan"], key)
        except BaseException:
            state["phase"] = "result_unknown"
            tasks.save(state)
            raise
        state.update(phase="saved", result=result, confirmation_token=None)
        tasks.save(state)
    return state


def recheck(tasks, state):
    result = plans.verify(state["plan"])
    previous = state.get("result")
    result["matches_saved_revision"] = bool(previous and previous.get("revision") == result["revision"])
    state["result"] = result
    # Presence alone cannot prove that a replacement Key was the intended one.
    state["phase"] = "saved" if result["saved"] and result["matches_saved_revision"] else "needs_review"
    state["confirmation_token"] = None
    tasks.save(state)
    return state


def accept_secret_book(tasks, state, receipt, reference):
    if state["source"] != "secret-book" or state["phase"] != "waiting_secret_book":
        raise SetupError("no_pending_secret_book_handoff")
    if (not isinstance(receipt, dict) or receipt.get("schema") != "setup-agent-model.write/v1"
            or receipt.get("status") != "written" or receipt.get("plan_fingerprint") != state["plan"]["fingerprint"]
            or receipt.get("path") != state["plan"]["target"]["path"] or receipt.get("key_matches") is not True):
        raise SetupError("invalid_public_write_receipt")
    if not isinstance(reference, str) or not reference or len(reference) > 150:
        raise SetupError("public_resume_reference_required")
    state["secret_book"] = {"reference": reference, "status": "written"}
    state["result"] = receipt
    tasks.save(state)  # Record receipt before independent readback; never save twice.
    return recheck(tasks, state)
