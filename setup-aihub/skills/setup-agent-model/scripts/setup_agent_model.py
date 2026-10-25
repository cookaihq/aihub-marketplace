"""Local configuration entry point. JSON output never contains configuration values."""
from _runtime_bootstrap import ensure_runtime
ensure_runtime(marker="SETUP_AGENT_MODEL_BOOTSTRAP_REEXEC")

import argparse
import json
from pathlib import Path
import subprocess
import sys

# Real imports check the locked dependencies; repair only this Skill's environment.
try:
    import tomlkit
    import ruamel.yaml
except Exception:
    try:
        skill = Path(__file__).resolve().parent.parent
        repaired = subprocess.run(["uv", "sync", "--frozen", "--no-dev", "--project", str(skill)], capture_output=True, timeout=180)
        if repaired.returncode:
            raise RuntimeError
        import tomlkit
        import ruamel.yaml
    except Exception:
        print('{"status":"runtime_error","reason":"dependency_import_failed"}')
        raise SystemExit(1)

from model_setup.common import SKILL, HOSTS, SetupError, json_object
from model_setup import catalog, clients, plans, workflow, local_input


def parser():
    p = argparse.ArgumentParser(description="Inspect and configure six native model clients without exposing Keys")
    sub = p.add_subparsers(dest="action", required=True)
    q = sub.add_parser("catalog")
    q.add_argument("--offline", action="store_true")
    q = sub.add_parser("catalog-build")
    q.add_argument("--check", action="store_true")
    q = sub.add_parser("inspect")
    q.add_argument("--client", choices=HOSTS, required=True)
    q.add_argument("--config")
    q.add_argument("--cwd", default=str(Path.cwd()))
    q = sub.add_parser("plan")
    q.add_argument("--request", required=True, help="JSON containing choices only; never a Key")
    q.add_argument("--source", choices=("manual", "secret-book", "preserve"), required=True)
    q.add_argument("--offline", action="store_true")
    for action in ("list", "status", "apply", "recheck", "cancel", "handoff", "accept-secret-book"):
        q = sub.add_parser(action)
        if action != "list":
            q.add_argument("--task", required=True)
        if action == "apply":
            q.add_argument("--confirm", required=True)
            q.add_argument("--input", choices=("dialog", "terminal"), default="dialog")
        if action == "handoff":
            q.add_argument("--output", required=True, help="Public no-value report for Secret Book")
        if action == "accept-secret-book":
            q.add_argument("--receipt", required=True)
            q.add_argument("--reference", required=True, help="Public Secret Book workflow ID")
    for action in ("plan", "list", "status", "apply", "recheck", "cancel", "handoff", "accept-secret-book"):
        q = sub.choices[action]
        q.add_argument("--host", choices=HOSTS, required=True)
        q.add_argument("--cwd", default=str(Path.cwd()))
    sub.add_parser("native-bridge", help="Restricted Secret Book native protocol over stdin")
    return p


def main():
    args = parser().parse_args()
    if sys.platform not in ("win32", "darwin") and args.action != "catalog-build":
        raise SetupError("unsupported_os")
    if args.action == "catalog-build":
        path = SKILL / "data/models.json"
        expected = catalog.manifest(path.read_bytes())
        output = path.with_name("models.manifest.json")
        if args.check:
            if json_object(output.read_bytes()) != expected:
                raise SetupError("catalog_manifest_stale")
        else:
            output.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        return expected
    if args.action == "catalog":
        return catalog.load(refresh=not args.offline)
    if args.action == "inspect":
        return clients.inspect(args.client, args.cwd, args.config)
    if args.action == "native-bridge":
        return bridge(json_object(sys.stdin.buffer.read(2 * 1024 * 1024)))
    current = workflow.context(args.host, args.cwd)
    tasks = workflow.Tasks()
    if args.action == "list":
        return tasks.list(current)
    if args.action == "plan":
        request = json_object(Path(args.request).read_bytes())
        loaded = catalog.load(refresh=not args.offline)
        plan = plans.build(request, args.cwd, loaded["catalog"], loaded["manifest"])
        return tasks.start(plan, current, args.source)
    with tasks.lock(args.task):
        state = tasks.load(args.task, current)
        if args.action == "status":
            return state
        if args.action == "apply":
            if state["source"] == "secret-book" or state["phase"] != "waiting_confirmation":
                raise SetupError("readback_before_retry")
            if state["confirmation_token"] != args.confirm:
                raise SetupError("confirmation_required")
            plans.revalidate(state["plan"])
            if state["source"] == "manual":
                key = local_input.read_key(args.input, state["plan"]["target"]["path"])
            else:
                key = None
            return workflow.apply(tasks, state, args.confirm, key)
        if args.action == "recheck":
            return workflow.recheck(tasks, state)
        if args.action == "cancel":
            state.update(phase="cancelled", confirmation_token=None)
            tasks.save(state)
            return state
        if args.action == "handoff":
            if state["source"] != "secret-book" or state["phase"] != "waiting_secret_book":
                raise SetupError("no_pending_secret_book_handoff")
            plans.revalidate(state["plan"])
            report = {"schema": "secret-book.native-inspection/v1", "consumer": {"kind": "plugin", "name": "setup-aihub"},
                      "skill": "setup-agent-model", "cwd": current["cwd"], "plan": state["plan"]}
            Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return {"report": str(Path(args.output).absolute()), "requirements": str(SKILL / "references/credentials.json"),
                    "writer": "secret-book", "remote_access": "read_only", "required_version": "2.7.0",
                    "task": state["id"], "key": "AIHUB_API_KEY"}
        if args.action == "accept-secret-book":
            return workflow.accept_secret_book(tasks, state, json_object(Path(args.receipt).read_bytes()), args.reference)


def bridge(message):
    if not isinstance(message, dict) or set(message) - {"operation", "plan", "values"}:
        raise SetupError("invalid_native_bridge_request")
    plan = message.get("plan")
    plans.validate_plan(plan)
    if plan.get("cwd") != str(Path.cwd().absolute()):
        raise SetupError("native_bridge_working_directory_changed")
    if message.get("operation") == "inspect":
        plans.revalidate(plan)
        data, _, _ = clients.load(plan["target"]["path"], plan["request"]["client"])
        return {"schema": "setup-agent-model.native-check/v1", "plan_fingerprint": plan["fingerprint"],
                "key_present": all(bool(clients.value_at(data, p)) for p in plan["secret_fields"])}
    if message.get("operation") == "verify":
        return plans.verify(plan)
    if message.get("operation") != "apply" or set(message.get("values", {})) != {"AIHUB_API_KEY"}:
        raise SetupError("invalid_native_bridge_operation")
    with workflow.Tasks().lock(plan["target"]["path"]):
        return workflow.write(plan, message["values"]["AIHUB_API_KEY"])


if __name__ == "__main__":
    try:
        result = main()
        print(json.dumps(result, ensure_ascii=True))
    except SetupError as exc:
        print(json.dumps({"schema": "setup-agent-model.result/v1", "status": "needs_attention", "reason": exc.reason,
                          "details": exc.details}, ensure_ascii=True))
        raise SystemExit(3)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.SubprocessError):
        # Parser and process errors can contain secret input; only stable codes escape.
        print('{"schema":"setup-agent-model.result/v1","status":"error","reason":"local_operation_failed"}')
        raise SystemExit(1)
