#!/usr/bin/env python3
"""Start/resume the private local configuration page. No secret argv/stdin."""
import sys
from _runtime_bootstrap import ensure_runtime
ensure_runtime()

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import webbrowser
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request

from setup_core.consumers import HOSTS, fingerprint, Consumer
from setup_core.errors import SetupError
from setup_core.local_config import checked_path
from setup_core.local_platform import private_directory, private_permissions
from setup_core.progress import Tasks, guard_context
from setup_core.ui_storage import write_json


class Parser(argparse.ArgumentParser):
    def error(self, _):
        raise SetupError("invalid_arguments", hint="Use --help; never pass Key values.")


def running(directory):
    try:
        record = json.loads((directory / "server.json").read_text())
        if not re.fullmatch(r"http://127\.0\.0\.1:[0-9]{1,5}", record["origin"]):
            return None
        with build_opener(ProxyHandler({})).open(record["origin"] + "/health", timeout=2) as response:
            data = json.load(response)
        if data.get("app") == "setup-aihub" and data.get("instance") == record["instance"]:
            record["lifetime"] = data["lifetime"]
            return record
    except (OSError, ValueError, KeyError):
        pass
    return None


def arguments():
    parser = Parser(description="打开本机 API Key 配置界面；密钥只能由本人在网页输入。")
    parser.add_argument("command", choices=("start", "status", "stop", "serve"))
    parser.add_argument("--host", required=True, choices=HOSTS)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--aihub-root")
    parser.add_argument("--tikin-root")
    parser.add_argument("--plugin", choices=("aihub-studio", "tikin-social"))
    parser.add_argument("--skill", help="真实业务 caller；无 caller 时省略，不借用 Skill 名")
    parser.add_argument("--task", help="明确的原 setup-api-key 任务 ID")
    parser.add_argument("--session", help="start 输出的界面会话 ID，用于 status/stop/恢复")
    parser.add_argument("--no-global-config", action="store_true")
    parser.add_argument("--operation", choices=("configure", "repair"), default="configure")
    parser.add_argument("--source", choices=("manual", "secret-book"))
    parser.add_argument("--scope", choices=("global", "project"))
    parser.add_argument("--submission", choices=("not_submitted", "submitted", "unknown"), default="unknown")
    parser.add_argument("--business-record")
    parser.add_argument("--business-task-id")
    parser.add_argument("--open", action="store_true")
    return parser.parse_args()


def main():
    args = arguments()
    cwd = str(Path(args.cwd).resolve(strict=True))
    services = {}
    for name, root in (("aihub-studio", args.aihub_root), ("tikin-social", args.tikin_root)):
        if root:
            caller = args.skill if args.plugin == name else None
            consumer = Consumer(name, root, caller, cwd, not args.no_global_config)
            services[name] = {"root": str(consumer.root), "caller": caller, "installation": "unknown"}
    options = {"host": args.host, "cwd": cwd, "services": services, "plugin": args.plugin, "task": args.task,
               "global_enabled": not args.no_global_config, "operation": args.operation, "submission": args.submission,
               "source": args.source or "manual", "scope": args.scope or ("project" if args.no_global_config else "global"),
               "business": {k: v for k, v in {"record": args.business_record, "task_id": args.business_task_id}.items() if v}}
    if args.task:
        task = Tasks().load(args.task)
        guard_context(task, args.host, cwd)
        context = task["context"]
        if task["operation"] not in ("configure", "repair"):
            raise SetupError("invalid_ui_operation")
        options.update(plugin=context["plugin"], global_enabled=context["global_enabled"], operation=task["operation"],
                       submission=task["submission"], business=task["business"], source=task["source"])
        options["services"][context["plugin"]] = {"root": context["root"], "caller": context["caller"], "installation": task["installation"]}
    session = args.session or fingerprint(options)[:32]
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise SetupError("invalid_session_id")
    config = checked_path(Path.home() / ".config/setup-aihub/ui" / session / "context.json")
    directory = config.parent
    if args.session:
        options = json.loads(config.read_text())
        if options["host"] != args.host or options["cwd"] != cwd:
            raise SetupError("task_context_mismatch")
    if args.command == "serve":
        from setup_core.ui_server import run
        return run(directory, options)
    record = running(directory)
    if args.command == "start":
        if not record:
            if not options["services"]:
                raise SetupError("no_services")
            private_directory(directory)
            write_json(config, options)
            logfile = checked_path(directory / "launcher.log")
            fd = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            private_permissions(logfile, fd=fd)
            with os.fdopen(fd, "ab") as log:
                flags = {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
                proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--host", args.host, "--cwd", cwd, "--session", session],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=cwd, **flags)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                record = running(directory)
                if record:
                    break
                if proc.poll() is not None:
                    raise SetupError("ui_start_failed", log=str(logfile))
                time.sleep(.15)
            if not record:
                raise SetupError("ui_start_timeout", session=session)
        url = record["origin"] + "/#" + record["token"]
        if args.open:
            webbrowser.open(url)
        return {"status": "running", "session": session, "url": url, "link_markdown": "[打开配置页](" + url + ")", "runtime": str(directory),
                "message": "请本人在此电脑的浏览器填写。空闲 60 分钟失效；完成后回到 Agent 继续原任务。", **record["lifetime"]}
    if args.command == "status":
        result = {"status": "running" if record else "stopped", "session": session, "runtime": str(directory)}
        if record:
            result["lifetime"] = record["lifetime"]
        if (directory / "progress.json").exists():
            state = json.loads((directory / "progress.json").read_text())
            result.update({k: state.get(k) for k in ("phase", "task_id", "service", "source", "receipt")})
        return result
    if record:
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor())
        def post(path, body, csrf=""):
            request = Request(record["origin"] + path, data=json.dumps(body).encode(), headers={"Origin": record["origin"], "Content-Type": "application/json", "X-Setup-CSRF": csrf})
            with opener.open(request, timeout=5) as response:
                return json.load(response)
        csrf = post("/api/session", {"token": record["token"]})["csrf"]
        post("/api/stop", {}, csrf)
        deadline = time.monotonic() + 5
        while running(directory) and time.monotonic() < deadline:
            time.sleep(.1)
        if running(directory):
            raise SetupError("ui_stop_pending")
    return {"status": "stopped", "session": session}


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        result = main()
        if result is not None:
            print(json.dumps(result, ensure_ascii=False))
    except SetupError as error:
        from setup_core.ui_errors import public_error
        print(json.dumps(public_error(error), ensure_ascii=False))
        raise SystemExit(2)
    except PermissionError:
        print(json.dumps({"error": "ui_permission_required", "message": "当前宿主未允许写入 Setup 运行目录或启动本机服务。请通过宿主的原生命令审批允许本次启动，保留默认沙箱；不要更改真实凭证。"}, ensure_ascii=False))
        raise SystemExit(2)
    except Exception as error:
        print(json.dumps({"error": "ui_operation_failed", "type": type(error).__name__}))
        raise SystemExit(1)
