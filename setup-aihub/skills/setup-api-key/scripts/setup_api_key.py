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

from setup_core.consumers import ADAPTERS, HOSTS, Consumer, host_context
from setup_core.errors import SetupError
from setup_core import default_settings
from setup_core.progress import (Tasks, active, apply_plan, consumer_for, guard_context, make_plan,
                                 recheck)


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
    start.add_argument("--source", choices=("manual",))
    start.add_argument("--installation", choices=("installed", "not_installed", "disabled", "unloaded", "unknown"), default="unknown")
    start.add_argument("--submission", choices=("not_submitted", "submitted", "unknown"), default="unknown")
    start.add_argument("--business-record", help="既有业务记录的本机路径；只存引用，不复制内容")
    start.add_argument("--business-task-id", help="已知业务任务 ID；不能放入请求或凭证")
    listing = sub.add_parser("list", help="只读列出同一宿主/运行环境/工作文件夹的未完成任务")
    host(listing)
    listing.add_argument("--plugin", choices=ADAPTERS)
    defaults = sub.add_parser("defaults", help="指定清单、Agent 核对结果与默认设置选项的跨轮恢复；不写规则")
    host(defaults)
    defaults.add_argument("--action", required=True, choices=("catalog", "record", "status", "choose", "preview", "verify", "finish"))
    defaults.add_argument("--task")
    defaults.add_argument("--input", help="无凭证 JSON 报告或内部写入计划参数文件")
    defaults.add_argument("--choice", choices=("1", "2", "3", "设为默认", "设为默认 (推荐)", "设为默认（推荐）", "本次跳过", "不再提醒"))
    defaults.add_argument("--targets", help="用户明确选定的 eligible 子集，逗号分隔 ID；省略表示整个菜单")
    for name in ("status", "attach", "source", "select", "plan", "apply", "continue", "reconcile", "cancel", "forget"):
        command = sub.add_parser(name)
        task(command)
        host(command)
        if name == "attach":
            command.add_argument("--plugin-root", required=True)
            command.add_argument("--installation", choices=("installed", "disabled", "unloaded", "unknown"), required=True)
        elif name == "source":
            command.add_argument("--source", choices=("manual",), required=True)
        elif name in ("plan", "select"):
            command.add_argument("--target", required=True)
            command.add_argument("--fields", required=True, help="逗号分隔的声明字段名；不接收值")
        elif name == "apply":
            command.add_argument("--confirm", required=True, help="使用者已授权的当前计划指纹")
    return parser.parse_args()


def run(args):
    cwd = Path(args.cwd).resolve()
    if not cwd.is_dir():
        raise SetupError("cwd_not_directory")
    if args.command == "defaults" and args.action == "catalog":
        return default_settings.catalog(args.host)
    if args.command == "defaults" and not args.task:
        raise SetupError("default_settings_task_required")
    tasks = Tasks()
    if args.command in ("start", "inspect"):
        if args.plugin_root:
            consumer = Consumer(args.plugin, args.plugin_root, args.skill, cwd, not args.no_global_config)
            context = consumer.context(args.host)
        else:
            context = {"host": args.host, "platform": os.name, "home": str(Path.home().resolve()), "cwd": str(cwd),
                       "plugin": args.plugin, "root": None, "version": None, "artifact_revision": None,
                       "caller": args.skill, "global_enabled": not args.no_global_config, **host_context(args.host)}
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
    if args.command == "defaults" and args.action == "status":
        return {"task": state["id"], "credential_phase": state["phase"],
                "default_settings": state.get("result", {}).get("default_settings")}
    if args.command == "status":
        # Do not consume a pending authorization or inspect any business files.
        return state
    with tasks.lock({"task": args.task}):
        state = tasks.load(args.task)
        guard_context(state, args.host, cwd)
        if args.command == "defaults":
            if args.action in ("record", "preview", "finish"):
                if not args.input:
                    raise SetupError("default_settings_input_required")
                result = getattr(default_settings, args.action)(state, default_settings.read_json(args.input))
            elif args.action == "choose":
                result = default_settings.choose(state, args.choice, args.targets.split(",") if args.targets else None)
            else:
                result = default_settings.verify(state)
            tasks.save(state)
            return {"task": state["id"], "credential_phase": state["phase"], "default_settings": result}
        if args.command == "cancel":
            if state["phase"] == "completed" and default_settings.pending(state):
                state["result"]["default_settings"].update(phase="skipped", eligible=[])
                tasks.save(state)
                return state
            state["phase"] = "cancelled"
            if default_settings.pending(state):
                state["result"]["default_settings"]["phase"] = "skipped"
            state.pop("plan", None)
            state.pop("authorization", None)
            tasks.save(state)
            return state
        if args.command == "forget":
            if state["phase"] not in ("completed", "cancelled") or default_settings.pending(state):
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
            if args.command == "continue" and state["phase"] in ("waiting_confirmation", "installation"):
                return state
            return recheck(tasks, state, args.command == "reconcile")
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
