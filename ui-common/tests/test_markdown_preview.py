"""Document-relative images stay bound to a registered, unchanged Markdown artifact."""
import base64
import hashlib
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, HTTPCookieProcessor, Request

MARKET = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MARKET / 'aihub-studio/shared'), str(MARKET / 'ui-common')]
from catalog import Catalog, TEXT_PREVIEW_BYTES
from markdown_preview import MAX_IMAGE_BYTES, nodes
from skill_ui.contracts import UIError

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aN1cAAAAASUVORK5CYII=')


def walk(tree):
    for node in tree:
        yield node
        yield from walk(node.get('children', []))


class MarkdownPreview(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ['TEMP'], prefix='markdown-preview-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.documents = self.root / '外置 文档'
        self.documents.mkdir()
        self.image = self.documents / 'assets' / '中文 图 (1).png'
        self.image.parent.mkdir()
        self.image.write_bytes(PNG)
        self.document = self.documents / 'document.md'

    def catalog(self, text, plugin='aihub-studio', external_task=True):
        self.document.write_text(text, encoding='utf-8')
        root = self.root / ('task-' + plugin) if external_task else self.project / 'data' / plugin / 'task'
        root.mkdir(parents=True, exist_ok=True)
        data = {'schema_version': 1, 'plugin': plugin, 'project_root': str(self.project), 'task_id': 'test-task',
                'records': [], 'participants': [], 'registered_outputs': [{'path': str(self.document),
                'bytes': self.document.stat().st_size, 'sha256': hashlib.sha256(self.document.read_bytes()).hexdigest()}]}
        (root / 'task-info.json').write_text(json.dumps(data), encoding='utf-8')
        return Catalog(self.project, plugin, [root] if external_task else [])

    def preview(self, catalog):
        return catalog.public_item(catalog.items[0], full=True)['preview']

    def images(self, preview):
        return [node for node in walk(preview['nodes']) if node.get('tag') == 'img']

    def test_both_plugins_resolve_registered_external_documents_without_adding_artifacts(self):
        text = '# 标题\n\n**重点**与*强调*\n\n- 列表\n\n![图](<assets/中文 图 (1).png>)\n\n![引用][frame]\n\n[frame]: assets/' + quote(self.image.name) + '\n'
        for plugin in ('aihub-studio', 'tikin-social'):
            for external in (True, False):
                with self.subTest(plugin=plugin, external_task=external):
                    catalog = self.catalog(text, plugin, external)
                    self.assertEqual(len(catalog.resources), 1)
                    self.assertNotIn('nodes', catalog.public_item(catalog.items[0])['preview'])
                    preview = self.preview(catalog)
                    images = self.images(preview)
                    self.assertEqual(len(images), 2)
                    self.assertEqual(images[0]['resource'], images[1]['resource'])
                    self.assertEqual(catalog.resource(images[0]['resource']).content, PNG)
                    self.assertEqual(catalog.resource(catalog.items[0]['id']).content.read_text(encoding='utf-8'), text)
                    self.assertEqual(preview['text'], self.document.read_bytes().decode('utf-8'))
                    self.assertEqual(len(catalog.items), 1)
                    self.assertEqual(catalog.tasks[0]['output_count'], 1)
                    self.assertTrue({'h1', 'strong', 'em', 'ul'} <= {n.get('tag') for n in walk(preview['nodes'])})

    def test_code_and_raw_html_do_not_discover_images_or_create_executable_nodes(self):
        discovered = []
        text = '```md\n![not an image](secret.png)\n```\n\n<img src="secret.png" onerror="alert(1)">\n\n<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n[safe](https://example.com/)'
        tree = nodes(text, discovered.append)
        flat = list(walk(tree))
        self.assertEqual(discovered, [])
        self.assertNotIn('script', {n.get('tag') for n in flat})
        self.assertEqual([n['href'] for n in flat if n.get('href')], ['https://example.com/'])
        self.assertIn('<script>', ''.join(n.get('text', '') for n in flat))

    def test_missing_remote_absolute_and_traversal_images_are_reported_without_resources(self):
        (self.root / 'outside.png').write_bytes(PNG)
        destinations = ['missing.png', '../outside.png', '%2e%2e/outside.png', '/outside.png',
                        'C:/outside.png', '//example.com/a.png', 'https://example.com/a.png',
                        '%5c%5cexample.com/a.png', 'assets/%00image.png']
        for destination in destinations:
            with self.subTest(destination=destination):
                catalog = self.catalog(f'![bad](<{destination}>)')
                image = self.images(self.preview(catalog))[0]
                self.assertIn('error', image)
                self.assertNotIn('resource', image)
                self.assertEqual(len(catalog.resources), 1)

    def test_svg_mislabeled_empty_and_oversized_files_are_not_served(self):
        paths = [('active.svg', b'<svg onload="alert(1)"/>'), ('fake.png', b'<html>secret</html>'), ('empty.png', b'')]
        for name, content in paths:
            (self.documents / name).write_bytes(content)
        huge = self.documents / 'huge.png'
        with huge.open('wb') as stream:
            stream.write(PNG)
            stream.seek(MAX_IMAGE_BYTES)
            stream.write(b'0')
        catalog = self.catalog('\n\n'.join(f'![bad]({name})' for name in ['active.svg', 'fake.png', 'empty.png', 'huge.png']))
        self.assertTrue(all('error' in image for image in self.images(self.preview(catalog))))
        self.assertEqual(len(catalog.resources), 1)

    def test_document_change_revokes_attachment_and_refresh_does_not_preserve_stale_ids(self):
        catalog = self.catalog('![图](<assets/中文 图 (1).png>)')
        key = self.images(self.preview(catalog))[0]['resource']
        self.document.write_text('changed document', encoding='utf-8')
        with self.assertRaises(UIError):
            catalog.resource(key)
        catalog.refresh()
        with self.assertRaises(UIError):
            catalog.resource(key)

    def test_changed_deleted_and_restored_image_requires_refresh(self):
        catalog = self.catalog('![图](<assets/中文 图 (1).png>)')
        key = self.images(self.preview(catalog))[0]['resource']
        self.image.write_bytes(PNG + b'changed')
        with self.assertRaises(UIError):
            catalog.resource(key)
        self.image.unlink()
        self.assertIn('error', self.images(self.preview(catalog))[0])
        with self.assertRaises(UIError):
            catalog.resource(key)
        self.image.write_bytes(PNG)
        catalog.refresh()
        key = self.images(self.preview(catalog))[0]['resource']
        self.assertEqual(catalog.resource(key).content, PNG)

    def test_symlink_escape_and_link_retargeting_are_rejected(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(PNG)
        link = self.documents / 'link.png'
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f'symlinks unavailable: {error.__class__.__name__}')
        catalog = self.catalog('![linked](link.png)')
        self.assertIn('error', self.images(self.preview(catalog))[0])
        link.unlink()
        link.symlink_to(self.image)
        key = self.images(self.preview(catalog))[0]['resource']
        self.assertEqual(catalog.resource(key).content, PNG)
        link.unlink()
        link.symlink_to(outside)
        with self.assertRaises(UIError):
            catalog.resource(key)

    def test_preview_limit_does_not_index_images_outside_displayed_content(self):
        catalog = self.catalog('text ' * (TEXT_PREVIEW_BYTES // 5 + 1) + '\n\n![图](<assets/中文 图 (1).png>)')
        detail = catalog.public_item(catalog.items[0], full=True)
        self.assertIn('部分内容', detail['preview_note'])
        self.assertEqual(self.images(detail['preview']), [])
        self.assertEqual(len(catalog.resources), 1)

    def test_table_numbered_list_and_safe_text_attributes(self):
        tree = nodes('3. item\n\n| a | b |\n|---|---|\n| **x** | `y` |\n\n~~removed~~', lambda src: None)
        flat = list(walk(tree))
        self.assertTrue({'ol', 'table', 'strong', 'code', 's'} <= {n.get('tag') for n in flat})
        self.assertEqual(next(n['start'] for n in flat if n.get('tag') == 'ol'), 3)

    def test_shipped_http_service_requires_auth_and_revokes_changed_attachments(self):
        catalog = self.catalog('![图](<assets/中文 图 (1).png>)')
        package = MARKET / 'aihub-studio'
        command = [sys.executable, str(package / 'scripts/ui.py'), 'start', '--page', 'artifacts',
                   '--project', str(self.project), '--task-dir', str(self.root / 'task-aihub-studio'),
                   '--runtime-dir', str(self.root / 'runtime'), '--no-global-config']
        try:
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=60)
            self.assertEqual(process.returncode, 0, process.stderr)
            started = json.loads(process.stdout)
            origin, token = started['url'].split('/#')
            client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
            def request(path, body=None):
                return client.open(Request(origin + path, data=None if body is None else json.dumps(body).encode(),
                                           headers={'Origin': origin, 'Content-Type': 'application/json'}), timeout=10)
            with self.assertRaises(HTTPError) as error:
                request('/resources/anything')
            self.assertEqual(error.exception.code, 401)
            with request('/api/session', {'token': token}) as response:
                json.load(response)
            with request('/api/artifacts?id=' + catalog.items[0]['id']) as response:
                detail = json.load(response)
            key = self.images(detail['items'][0]['preview'])[0]['resource']
            with request('/resources/' + key) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
                self.assertEqual(response.read(), PNG)
            with self.assertRaises(HTTPError) as error:
                request('/resources/' + quote(str(self.image), safe=''))
            self.assertEqual(error.exception.code, 404)
            self.document.write_text('document changed', encoding='utf-8')
            with self.assertRaises(HTTPError) as error:
                request('/resources/' + key)
            self.assertEqual(error.exception.code, 409)
        finally:
            command[2] = 'stop'
            subprocess.run(command, capture_output=True, timeout=30, check=True)


if __name__ == '__main__':
    unittest.main()
