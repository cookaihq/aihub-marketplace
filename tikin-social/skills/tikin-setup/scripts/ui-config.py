"""Private JSON pipe to the original loader. Never an Agent-facing inspection command."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
from _runtime_bootstrap import ensure_runtime

# Enter the consuming Plugin's environment before reading stdin. A re-exec
# after json.load would leave the child without its configuration payload.
ensure_runtime('TIKIN_SETUP_BOOTSTRAP_REEXEC')


def main():
    options = json.load(sys.stdin)
    os.chdir(options['project'])
    loader = importlib.machinery.SourceFileLoader('tikin_ui_loader', str(Path(__file__).with_name('tikin-config')))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    layers = []
    values, sources, inspection = module.resolve_config(options.get('skill'), options['global_enabled'],
                                                       file_overrides=options.get('overrides'), layer_values=layers)
    result = {'shared': {'values': values, 'sources': sources, 'inspection': inspection, 'layerValues': layers},
              'home_directory': str(Path.home())}
    if options['global_enabled']:
        from default_skills import read_settings, run
        path = module.config_dir() / 'settings.json'
        settings = read_settings(path, options.get('overrides', {}).get(str(path)))
        module.validate_routing(settings)
        result.update(settings=settings, settings_path=str(path))
        if options.get('agent'):
            result['reminder'] = {'config_dir': run(options['agent'], 'preference', options.get('config_dir'))['config_dir']}
    return result


if __name__ == '__main__':
    try:
        result = main()
    except (Exception, SystemExit):
        result = {'error': 'Configuration cannot be read. Check files and caller identity.'}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(1 if 'error' in result else 0)
