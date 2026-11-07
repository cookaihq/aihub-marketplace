"""Called from each Plugin's pinned runtime entry. Never accepts credential values."""
import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time


def main(package, plugin):
    parser = argparse.ArgumentParser(description='Manage a local Plugin configuration or artifact page.')
    parser.add_argument('command', choices=('start', 'status', 'stop'))
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--page', choices=('configuration', 'artifacts'), required=True)
    parser.add_argument('--task-dir', type=Path, action='append', default=[])
    parser.add_argument('--skill')
    parser.add_argument('--agent', choices=('codex', 'claude-code', 'workbuddy', 'hermes'))
    parser.add_argument('--config-dir', type=Path)
    parser.add_argument('--no-global-config', action='store_true')
    parser.add_argument('--save-scope', choices=('global', 'project'), default='global')
    parser.add_argument('--idle-seconds', type=int, default=3600)
    parser.add_argument('--public-origin')
    parser.add_argument('--runtime-dir', type=Path)
    parser.add_argument('--task-id')
    parser.add_argument('--task-binding')
    parser.add_argument('--continuation')
    parser.add_argument('--keep-running', action='store_true',
                        help='Keep start attached to the host native background tool until this page stops.')
    args = parser.parse_args()
    if args.keep_running and args.command != 'start':
        parser.error('--keep-running is only valid with start')
    project = args.project.resolve(strict=True)
    if not project.is_dir() or project.is_relative_to(package):
        parser.error('project must be an existing work directory outside the Plugin installation')
    options = {'plugin': plugin, 'task_dirs': [str(path.resolve(strict=True)) for path in args.task_dir], 'skill': args.skill,
               'agent': args.agent, 'config_dir': str(args.config_dir.resolve()) if args.config_dir else None,
               'global_enabled': not args.no_global_config, 'save_scope': args.save_scope}
    if args.task_id:
        if len(args.task_id) > 128 or not args.task_binding or len(args.task_binding) > 128:
            parser.error('task identity and binding are required and must be bounded')
        options['task'] = {'id': args.task_id, 'binding': args.task_binding,
                           'continuation': args.continuation or '请重新检查配置，并继续此前已授权的任务。'}
    encoded = json.dumps(options, ensure_ascii=False, sort_keys=True)
    os.environ['AIHUB_UI_OPTIONS'] = encoded
    scope = hashlib.sha256(encoded.encode()).hexdigest()[:16]
    runtime = (args.runtime_dir or project / 'tmp' / (plugin + '-ui')).resolve() / scope
    if runtime.is_relative_to(package):
        parser.error('runtime directory must stay outside the installation')
    sys.path.insert(0, str(package / 'shared'))
    from skill_ui.__main__ import main as core_main
    sys.argv = [sys.argv[0], args.command, '--adapter', str(package / 'ui' / 'adapter.py'), '--project', str(project),
                '--page', args.page, '--runtime-dir', str(runtime), '--idle-seconds', str(args.idle_seconds)]
    if args.public_origin:
        sys.argv += ['--public-origin', args.public_origin]
    if not args.keep_running:
        return core_main()
    # WorkBuddy reaps a completed tool's child process tree. Keep the original
    # native background tool alive; do not escape its process/security controls.
    with redirect_stdout(io.StringIO()) as output:
        result = core_main()
    started = output.getvalue()
    print(started, end='', flush=True)
    state = json.loads(started)
    from skill_ui.__main__ import running
    while True:
        record = running(Path(state['runtime']))
        if not record or record['instance'] != state.get('instance'):
            break
        time.sleep(1)
    return result
