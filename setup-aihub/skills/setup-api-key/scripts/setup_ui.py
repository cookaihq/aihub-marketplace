#!/usr/bin/env python3
"""Open the selected Plugin's configuration center, preserving task/resume identity."""
import sys
from _runtime_bootstrap import ensure_runtime
ensure_runtime()

import argparse
import json
from pathlib import Path
import subprocess
import time
import webbrowser
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, Request

from setup_core.consumers import HOSTS, Consumer, fingerprint
from setup_core.errors import SetupError
from setup_core.progress import Tasks, guard_context, consumer_for


class Parser(argparse.ArgumentParser):
    def error(self, _):
        raise SetupError('invalid_arguments', hint='Use --help; never pass Key values.')


def arguments():
    parser = Parser(description='打开指定 Plugin 的配置中心。密钥由本人在网页填写。')
    parser.add_argument('command', choices=('start', 'status', 'stop'))
    parser.add_argument('--host', required=True, choices=HOSTS)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--aihub-root')
    parser.add_argument('--tikin-root')
    parser.add_argument('--plugin', choices=('aihub-studio', 'tikin-social'))
    parser.add_argument('--skill')
    parser.add_argument('--task')
    parser.add_argument('--session', help='start 返回的任务 ID；用于恢复、查询和停止')
    parser.add_argument('--no-global-config', action='store_true')
    parser.add_argument('--operation', choices=('configure', 'repair'), default='configure')
    parser.add_argument('--scope', choices=('global', 'project'))
    parser.add_argument('--submission', choices=('not_submitted', 'submitted', 'unknown'), default='unknown')
    parser.add_argument('--business-record')
    parser.add_argument('--business-task-id')
    parser.add_argument('--config-dir')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--keep-running', action='store_true', help='Keep start attached to the host native background tool.')
    return parser.parse_args()


def main(args=None):
    args = args or arguments()
    if args.keep_running and args.command != 'start':
        raise SetupError('invalid_arguments', hint='--keep-running only applies to start')
    cwd, tasks = Path(args.cwd).resolve(strict=True), Tasks()
    task_id = args.task or args.session
    if task_id:
        state = tasks.load(task_id)
        guard_context(state, args.host, cwd)
        consumer = consumer_for(state)
        if state['operation'] not in ('configure', 'repair'):
            raise SetupError('invalid_ui_operation')
    else:
        if args.command != 'start':
            raise SetupError('task_required')
        roots = {name: root for name, root in [('aihub-studio', args.aihub_root), ('tikin-social', args.tikin_root)] if root}
        plugin = args.plugin or (next(iter(roots)) if len(roots) == 1 else None)
        if plugin not in roots:
            raise SetupError('explicit_plugin_required', available=list(roots))
        consumer = Consumer(plugin, roots[plugin], args.skill, cwd, not args.no_global_config)
        business = {}
        if args.business_record:
            record = Path(args.business_record).resolve(strict=True)
            if not record.is_file() or record.suffix != '.json':
                raise SetupError('invalid_business_record')
            business['record'] = str(record)
        if args.business_task_id:
            import re
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', args.business_task_id):
                raise SetupError('invalid_business_task_id')
            business['task_id'] = args.business_task_id
        state = tasks.start(consumer.context(args.host), args.operation, 'manual', 'unknown', args.submission, business)
    package = consumer.root if consumer.name == 'aihub-studio' else consumer.root / 'skills/tikin-setup'
    entry = package / 'scripts/ui.py'
    if not entry.is_file():
        raise SetupError('configuration_center_unavailable', hint='Update the selected business Plugin to the version containing scripts/ui.py, then resume this task.', task=state['id'])
    with tasks.lock({'task': state['id']}):
        state = tasks.load(state['id'])
        guard_context(state, args.host, cwd)
        if 'ui' not in state:
            state['ui'] = {'scope': args.scope or ('global' if consumer.global_enabled else 'project'), 'config_dir': args.config_dir,
                           'binding': fingerprint({'context': state['context'], 'business': state['business'], 'submission': state['submission']})}
            tasks.save(state)
        ui = state['ui']
    continuation = '请在项目 ' + str(cwd) + ' 中继续 setup-api-key 任务 ' + state['id'] + '；先核对配置和原业务提交状态，再继续已授权的任务。'
    command = [sys.executable, str(entry), args.command, '--project', str(cwd), '--page', 'configuration',
               '--agent', args.host, '--save-scope', ui['scope'], '--task-id', state['id'], '--task-binding', ui['binding'],
               '--continuation', continuation]
    if consumer.caller:
        command += ['--skill', consumer.caller]
    if not consumer.global_enabled:
        command += ['--no-global-config']
    if ui.get('config_dir'):
        command += ['--config-dir', ui['config_dir']]
    process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', cwd=cwd, timeout=210)
    try:
        result = json.loads(process.stdout)
    except ValueError:
        raise SetupError('ui_start_failed', task=state['id']) from None
    if process.returncode:
        raise SetupError('ui_operation_failed', task=state['id'])
    result.update(session=state['id'], task=state['id'], binding=ui['binding'],
                  message='保存后由 Agent 核对任务关联与原加载器；本页不重发业务请求。')
    if args.open and result.get('url'):
        webbrowser.open(result['url'])
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        args = arguments()
        result = main(args)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.keep_running and result.get('url'):
            location = urlsplit(result['url'])
            origin = location.scheme + '://' + location.netloc
            client = build_opener(ProxyHandler({}))
            while True:
                try:
                    with client.open(Request(origin + '/health', headers={'Origin': origin}), timeout=3) as response:
                        state = json.load(response)
                    if state.get('app') != 'skill-ui' or state.get('instance') != result.get('instance'):
                        break
                except (OSError, ValueError):
                    break
                time.sleep(1)
    except SetupError as error:
        print(json.dumps({'error': error.reason, **error.details}, ensure_ascii=False))
        raise SystemExit(2)
    except Exception:
        print(json.dumps({'error': 'ui_operation_failed', 'message': '请检查指定项目、Plugin 版本和本机运行环境。'}, ensure_ascii=False))
        raise SystemExit(1)
