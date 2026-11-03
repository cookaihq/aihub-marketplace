"""Exercise frozen batch discovery and construction through shipped public CLIs."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / 'skills/tikin-endpoint-discovery/scripts/tikin-find-endpoint'


class CatalogContractTests(unittest.TestCase):
    def describe(self, path, method='GET'):
        result = subprocess.run([sys.executable, str(DISCOVERY), '--describe', path, '--method', method],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_ads_optional_string_is_discovered_without_object_coercion(self):
        for path in ('get_configure_safety', 'get_location_list'):
            operation = self.describe('/api/v1/tiktok/ads/' + path, 'POST')['operation']
            self.assertEqual(operation['requestBody']['content']['application/json']['schema']['type'], 'string')
            self.assertFalse(operation['requestBody'].get('required', False))

    def test_caption_query_is_free_and_creation_is_marked_with_side_effects(self):
        creation = self.describe('/api/v1/youtube/web_v2/get_video_captions')
        result = self.describe('/api/v1/youtube/web_v2/get_video_captions_result')
        self.assertTrue(creation['side_effects'])
        self.assertFalse(result['side_effects'])
        self.assertEqual(result['catalog_price']['usd'], '0.0')
        self.assertTrue(next(p for p in result['operation']['parameters'] if p['name'] == 'job_id')['required'])

    def test_public_defaults_keep_reference_siblings_and_permitted_normalizations(self):
        creator = self.describe('/api/v1/douyin/xingtu_v2/search_creator')
        params = {p['name']: p['schema'] for p in creator['operation']['parameters']}
        self.assertEqual(params['seach_type']['default'], 2)
        self.assertEqual(params['time_range_days']['default'], 180)
        self.assertIn('$ref', params['seach_type'])
        board = self.describe('/api/v1/kuaishou/app/fetch_hot_board_detail')
        default = next(p for p in board['operation']['parameters'] if p['name'] == 'boardId')['schema']['default']
        self.assertIs(type(default), int)
        self.assertEqual(default, 1)
        content = self.describe('/api/v1/tiktok/app/v3/fetch_content_translate', 'POST')
        schemas = content['components']['schemas'].values()
        source = next(s['properties']['src_content'] for s in schemas if 'src_content' in s.get('properties', {}))
        self.assertNotIn('default', source)

    def test_every_changed_contract_is_available_through_public_discovery(self):
        refs = ROOT / 'skills/tikin-endpoint-discovery/references'
        changes = json.loads((refs / 'request-changes.json').read_text())
        self.assertEqual(len(changes['method_migrations']), 13)
        self.assertEqual(len(changes['request_changes']), 76)
        self.assertEqual(len(changes['retired']), 110)
        for row in changes['request_changes']:
            with self.subTest(path=row['path']):
                output = self.describe(row['path'], row['method'])
                def normalize(value):
                    if isinstance(value, dict):
                        if '$ref' in value:
                            target = output
                            for part in value['$ref'][2:].split('/'):
                                target = target[part.replace('~1', '/').replace('~0', '~')]
                            return normalize({**target, **{k: v for k, v in value.items() if k != '$ref'}})
                        return {k: normalize(v) for k, v in value.items() if k not in ('title', 'description', 'example', 'examples')}
                    return [normalize(v) for v in value] if isinstance(value, list) else value
                op = output['operation']
                contract = {'parameters': sorted(normalize(op.get('parameters', [])), key=lambda p: (p['in'], p['name'])),
                            'body': normalize(op.get('requestBody'))}
                digest = hashlib.sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                self.assertEqual(digest, row['public_request_sha256'])
                if row['path'] not in ('/api/v1/kuaishou/app/fetch_hot_board_detail', '/api/v1/tiktok/app/v3/fetch_content_translate'):
                    self.assertEqual(digest, row['source_request_sha256'])
                self.assertIn(row['classification'], ('compatible', 'breaking', 'behavior_change'))
        for row in changes['method_migrations']:
            with self.subTest(path=row['path']):
                current = self.describe(row['path'], row['new_method'])
                self.assertIn('requestBody', current['operation'])
                old = subprocess.run([sys.executable, str(DISCOVERY), '--describe', row['path'], '--method', row['old_method']],
                                     capture_output=True, text=True, timeout=30)
                self.assertEqual(old.returncode, 1)
                self.assertEqual(json.loads(old.stdout)['error'], 'operation_not_in_catalog')

    def test_frozen_set_has_no_retired_or_second_batch_operations(self):
        refs = ROOT / 'skills/tikin-endpoint-discovery/references'
        identity = json.loads((refs / 'catalog-identity.json').read_text())
        for name in ('endpoint-index.json', 'openapi.json'):
            self.assertEqual(hashlib.sha256((refs / name).read_bytes()).hexdigest(), identity['outputs'][name]['sha256'])
        self.assertEqual(identity['outputs']['endpoint-index.json']['sha256'],
                         'c2a05795b3c2927bef5230d47afd9b2410db569bbeb8d4efdd5daff9c8abad12')
        result = subprocess.run([sys.executable, str(DISCOVERY), '--limit', '2000'], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        operations = {' '.join(line.split()[:2]) for line in result.stdout.splitlines()}
        self.assertEqual(len(operations), 919)
        retired = {row['operation'] for row in json.loads((refs / 'request-changes.json').read_text())['retired']}
        self.assertFalse(operations & retired)
        self.assertIn('GET /api/v1/threads/web/search_posts', operations)
        self.assertIn('GET /api/v1/tiktok/shop/web/fetch_product_detail_v3', operations)
        self.assertFalse(any('/linkedin/web_v2/async/' in op or '/bilibili/huahuo/' in op for op in operations))


if __name__ == '__main__':
    unittest.main()
