import json
import os
from importlib import import_module
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
            if self.plugin == 'aihub-studio':
                configuration_class = import_module('plugins.aihub-studio.scopes').StudioConfiguration
            else:
                from configuration import Configuration
                configuration_class = Configuration
            self._configuration = configuration_class(self.package, self.project, self.options)
        return self._configuration

    def config(self):
        return self.configuration.snapshot()

    def preview(self, changes, revision, target):
        return self.configuration.preview(changes, revision, target)

    def save(self, changes, revision, target):
        return self.configuration.save(changes, revision, target)

    def artifacts(self):
        return self.catalog.snapshot()

    def resource(self, resource_id):
        return self.catalog.resource(resource_id)


class StudioAdapter(MarketplaceAdapter):
    def preview(self, changes, revision):
        return self.configuration.preview(changes, revision)

    def save(self, changes, revision):
        return self.configuration.save(changes, revision)


def build(project):
    install()
    options = json.loads(os.environ.get('AIHUB_UI_OPTIONS', '{}'))
    return (StudioAdapter if options['plugin'] == 'aihub-studio' else MarketplaceAdapter)(project)
