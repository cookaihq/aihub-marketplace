"""Marketplace additions around the pinned Skill UI handler; vendored files remain unchanged."""
import json
from importlib import import_module
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from skill_ui import server
from skill_ui.contracts import UIError

ASSETS = Path(__file__).resolve().parent
CoreHandler = server.Handler


class MarketplaceHandler(CoreHandler):
    def send_header(self, keyword, value):
        if (keyword.lower() == 'content-security-policy' and self.server.page == 'configuration'
                and self.server.adapter.plugin == 'aihub-studio'):
            value = import_module('plugins.aihub-studio.web').media_policy(value)
        super().send_header(keyword, value)

    def get(self):
        parsed = urlsplit(self.path)
        if parsed.path in ('/app.js', '/style.css'):
            self.check_origin()
            name = parsed.path[1:]
            original = (server.STATIC / name).read_text(encoding='utf-8')
            extras = ('configuration.js', 'markdown.js', 'artifacts.js') if name.endswith('.js') else ('configuration.css', 'artifacts.css')
            # Prevent the core's single-file shortcut before its bootstrap runs.
            prelude = ("if(!new URL(location.href).searchParams.has('view')){const u=new URL(location.href);u.searchParams.set('view','collection');history.replaceState({},'',u);}\n"
                       if name.endswith('.js') else '')
            if name.endswith('.js'):
                prelude += 'const marketplaceSaveScope=' + json.dumps(self.server.adapter.options.get('save_scope', 'global')) + ';\n'
            content = prelude + original + '\n' + '\n'.join((ASSETS / file).read_text(encoding='utf-8') for file in extras)
            if self.server.page == 'configuration' and self.server.adapter.plugin == 'aihub-studio':
                content += '\n' + import_module('plugins.aihub-studio.web').assets('js' if name.endswith('.js') else 'css')
            return self.send(200, content.encode(), ('text/javascript' if name.endswith('.js') else 'text/css') + '; charset=utf-8')
        if parsed.path == '/api/minimax-voices':
            self.check_origin()
            self.authorized()
            self.server.lifetime()
            if self.server.page != 'configuration' or self.server.adapter.plugin != 'aihub-studio':
                raise UIError('page', '此页面不提供音色库。', 404)
            # A fresh read uses the latest credential; never cache a previous key's response.
            return self.send(200, import_module('plugins.aihub-studio.web').voices(self.server.adapter.configuration))
        if parsed.path == '/api/artifacts':
            self.check_origin()
            self.authorized()
            self.server.lifetime()
            if self.server.page != 'artifacts':
                raise UIError('page', '此页面不提供产物集合。', 404)
            query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
            if any(len(value) > 512 for value in query.values()):
                raise UIError('query', '筛选条件过长。')
            with self.server.lock:
                catalog = self.server.adapter.catalog
                if query.pop('refresh', None) == '1':
                    catalog.refresh()
                return self.send(200, catalog.snapshot(query))
        return super().get()


def install():
    # Server resolves its handler at construction, after the trusted adapter is loaded.
    server.Handler = MarketplaceHandler
