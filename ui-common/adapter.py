import json
import os
from pathlib import Path

from skill_ui.contracts import Adapter
from catalog import Catalog
from web import install


class MarketplaceAdapter(Adapter):
    def __init__(self, project):
        self.project = project.resolve()
        self.package = Path(__file__).resolve().parent.parent
        self.options = json.loads(os.environ.get('AIHUB_UI_OPTIONS', '{}'))
        self.plugin = self.options['plugin']
        self.title = 'AIhub Studio' if self.plugin == 'aihub-studio' else 'Tikin Social'
        self._catalog = None
        self._configuration = None

    @property
    def catalog(self):
        if self._catalog is None:
            self._catalog = Catalog(self.project, self.plugin, self.options.get('task_dirs', []))
        return self._catalog

    @property
    def configuration(self):
        if self._configuration is None:
            from configuration import Configuration
            self._configuration = Configuration(self.package, self.project, self.options)
        return self._configuration

    def config(self):
        return self.configuration.snapshot()

    def save(self, changes, revision):
        return self.configuration.save(changes, revision)

    def artifacts(self):
        return self.catalog.snapshot()

    def resource(self, resource_id):
        return self.catalog.resource(resource_id)


def build(project):
    install()
    return MarketplaceAdapter(project)
