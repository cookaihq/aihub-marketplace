#!/usr/bin/env python3
"""Agent helper. Credential values are never command arguments or JSON inputs."""
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")
from _runtime_bootstrap import ensure_runtime
ensure_runtime()

import argparse
import json
import os
import re
from pathlib import Path

from setup_core.consumers import ADAPTERS, HOSTS, Consumer
from setup_core.errors import SetupError
from setup_core.progress import (Tasks, active, apply_plan, consumer_for, guard_context, make_plan,
                                 pending_delegation, recheck, secret_book_compatibility, secret_book_handoff, secret_book_result)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown argv; it may be an accidentally pasted
        # Key. Show only the fixed help location, never the supplied argument.
        raise SetupError("invalid_arguments", hint="Use --help; no Key values are accepted.")


def arguments():
    parser = Parser(description="Setup API Key: 本机无值检查、手填准备、指定字段清除与进度恢复。")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)

    def context(command, root_required=True):
        command.add_argument("--plugin", required=True, choices=ADAPTERS)
        command.add_argument("--plugin-root", required=root_required)
        caller = command.add_mutually_exclusive_group(required=True)
        caller.add_argument("--skill")
        caller.add_argument("--plugin-only", action="store_true")
        command.add_argument("--no-global-config", action="store_true")

    def task(command):
        command.add_argument("--task", required=True)

    def host(command):
        command.add_argument("--host", required=True, choices=HOSTS)
        command.add_argument("--cwd", required=True, help="实际业务工作文件夹")

    inspect = sub.add_parser("inspect", help="只读；不创建配置或进度、不联网鉴权")
    context(inspect)
    host(inspect)
    start = sub.add_parser("start", help="开始需跨轮恢复的配置任务；只保存无值元数据")
    context(start, False)
    host(start)
    start.add_argument("--operation", choices=("configure", "repair", "clear", "check"), required=True)
    start.add_argument("--source", choices=("manual", "secret-book"))
    start.add_argument("--installation", choices=("installed", "not_installed", "disabled", "unloaded", "unknown"), default="unknown")
    start.add_argument("--submission", choices=("not_submitted", "submitted", "unknown"), default="unknown")
    start.add_argument("--business-record", help="既有业务记录的本机路径；只存引用，不复制内容")
    start.add_argument("--business-task-id", help="已知业务任务 ID；不能放入请求或凭证")
    listing = sub.add_parser("list", help="只读列出同一宿主/运行环境/工作文件夹的未完成任务")
    host(listing)
    listing.add_argument("--plugin", choices=ADAPTERS)
    for name in ("status", "attach", "source", "select", "plan", "apply", "continue", "reconcile", "cancel", "forget", "handoff", "handoff-result"):
        command = sub.add_parser(name)
        task(command)
        host(command)
        if name == "attach":
            command.add_argument("--plugin-root", required=True)
            command.add_argument("--installation", choices=("installed", "disabled", "unloaded", "unknown"), required=True)
        elif name == "source":
            command.add_argument("--source", choices=("manual", "secret-book"), required=True)
        elif name in ("plan", "select"):
            command.add_argument("--target", required=True)
            command.add_argument("--fields", required=True, help="逗号分隔的声明字段名；不接收值")
        elif name == "apply":
            command.add_argument("--confirm", required=True, help="使用者已授权的当前计划指纹")
        elif name == "handoff":
            command.add_argument("--availability", required=True,
                                 choices=("missing", "unknown", "unloaded", "incompatible", "available"))
            command.add_argument("--secret-book-root", help="可用时必填：当前宿主选用的 Secret Book 完整 Skill 实体")
        elif name == "handoff-result":
            command.add_argument("--status", required=True, choices=("completed", "cancelled", "pending", "failed", "unknown"))
            command.add_argument("--reference", help="Secret Book 公开的不透明恢复引用；不传其状态文件")
    return parser.parse_args()


def run(args):
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        raise SetupError("cwd_not_directory")
    tasks = Tasks()
    if args.command in ("start", "inspect"):
        if args.plugin_root:
            consumer = Consumer(args.plugin, args.plugin_root, args.skill, cwd, not args.no_global_config)
            context = consumer.context(args.host)
        else:
            context = {"host": args.host, "platform": os.name, "home": str(Path.home().resolve()), "cwd": str(cwd),
                       "plugin": args.plugin, "root": None, "version": None, "artifact_revision": None,
                       "caller": args.skill, "global_enabled": not args.no_global_config}
        if args.command == "inspect":
            return {"context": context, "mode": "skill" if args.skill else "plugin_shared",
                    "inspection": consumer.inspect(), "online_authentication": "not_performed",
                    "host_installation": "not_verified", "host_loading": "not_verified", "business_call": "not_verified"}
        business = {}
        if args.business_record:
            record = Path(args.business_record).resolve()
            if record.suffix != ".json" or not record.is_file():
                raise SetupError("invalid_business_record")
            business["record"] = str(record)
        if args.business_task_id:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", args.business_task_id):
                raise SetupError("invalid_business_task_id")
            business["task_id"] = args.business_task_id
        return tasks.start(context, args.operation, args.source, args.installation, args.submission, business)
    if args.command == "list":
        return {"tasks": tasks.matches(args.host, cwd, args.plugin)}
    state = tasks.load(args.task)
    guard_context(state, args.host, cwd)
    if args.command == "status":
        # Do not consume a pending authorization or inspect any business files.
        return state
    with tasks.lock({"task": args.task}):
        state = tasks.load(args.task)
        guard_context(state, args.host, cwd)
        if args.command == "cancel":
            if pending_delegation(state):
                raise SetupError("secret_book_owns_write")
            state["phase"] = "cancelled"
            state.pop("plan", None)
            state.pop("authorization", None)
            tasks.save(state)
            return state
        if args.command == "forget":
            if state["phase"] not in ("completed", "cancelled"):
                raise SetupError("close_task_before_forgetting")
            tasks.path(state["id"]).unlink()
            return {"forgotten_task": state["id"], "business_configuration": "preserved"}
        if args.command == "attach":
            active(state)
            old = state["context"]
            consumer = Consumer(old["plugin"], args.plugin_root, old["caller"], cwd, old["global_enabled"])
            state["context"], state["installation"] = consumer.context(args.host), args.installation
            state["phase"] = "inspection"
            state.pop("plan", None)
            state.pop("authorization", None)
            tasks.save(state)
            return state
        if args.command == "source":
            active(state)
            state["source"], state["phase"] = args.source, "inspection" if state["context"]["root"] else "installation"
            state.pop("plan", None)
            state.pop("authorization", None)
            tasks.save(state)
            return state
        if args.command == "plan":
            return make_plan(tasks, state, args.target, args.fields.split(","))
        if args.command == "select":
            active(state)
            consumer = consumer_for(state)
            report = consumer.inspect()
            fields = args.fields.split(",")
            from setup_core.local_config import validate_target
            target = validate_target(consumer, report, args.target, fields, "clear" if state["operation"] == "clear" else "prepare")
            state["selection"] = {"target": target["path"], "fields": fields}
            state.pop("plan", None)
            state.pop("authorization", None)
            state["phase"] = "inspection"
            tasks.save(state)
            return state
        if args.command == "apply":
            return apply_plan(tasks, state, args.confirm)
        if args.command in ("continue", "reconcile"):
            if state["phase"] in ("completed", "cancelled"):
                return state
            delegated_complete = state.get("secret_book", {}).get("status") == "completed"
            if args.command == "continue" and (state["phase"] in ("waiting_confirmation", "installation")
                    or state["phase"] == "waiting_secret_book" and not delegated_complete):
                return state  # "继续" is not a new write authorization or delegated result.
            return recheck(tasks, state, args.command == "reconcile")
        if args.command == "handoff":
            active(state)
            if state["source"] != "secret-book" or state["operation"] not in ("configure", "repair"):
                raise SetupError("invalid_secret_book_operation")
            if args.availability != "available":
                state["phase"] = "waiting_secret_book"
                state["secret_book"] = {"status": args.availability, "reference": None, "contract": "not_delegated", "delegated": False}
                tasks.save(state)
                options = ["安装并继续", "自行填写本机文件", "暂不配置"] if args.availability == "missing" else ["核对当前宿主的安装、加载与能力", "自行填写本机文件", "暂不配置"]
                return {"task": state, "options": options, **secret_book_compatibility(state["context"]["caller"])}
            return secret_book_handoff(tasks, state, args.secret_book_root)
        if args.command == "handoff-result":
            return secret_book_result(tasks, state, args.status, args.reference)
    raise SetupError("unknown_command")


def main():
    try:
        result = run(arguments())
        print(json.dumps({"schema": "setup-aihub.result/v1", "status": "ok", "result": result}, ensure_ascii=False, indent=2))
        return 0
    except SetupError as error:
        print(json.dumps({"schema": "setup-aihub.result/v1", "status": "needs_attention", "reason": error.reason,
                          **error.details}, ensure_ascii=False))
        return 2
    except Exception:
        # File/JSON/process exception messages may carry secret input. Keep the
        # public boundary closed; reproduce with synthetic fixtures for diagnosis.
        print(json.dumps({"schema": "setup-aihub.result/v1", "status": "needs_attention", "reason": "local_operation_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
