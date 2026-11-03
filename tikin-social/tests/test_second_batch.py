"""Frozen new-operation discovery and controlled request-shape demonstrations."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

spec = importlib.util.spec_from_file_location('execution_fixture', Path(__file__).with_name('test_execution_safety.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
ROOT = Path(__file__).resolve().parents[1]
DISCOVERY = ROOT / 'skills/tikin-endpoint-discovery/scripts/tikin-find-endpoint'


class SecondBatchTests(unittest.TestCase):
    setUp = fixture.ExecutionSafetyTests.setUp
    command = fixture.ExecutionSafetyTests.command
    request = fixture.ExecutionSafetyTests.request

    def test_all_110_added_operations_are_discoverable_with_full_contracts(self):
        cohorts = json.loads((ROOT / 'skills/tikin-endpoint-discovery/references/catalog-cohorts.json').read_text())['cohorts']
        self.assertEqual({key: len(rows) for key, rows in cohorts.items()},
                         {'bilibili_sync': 47, 'other_sync': 57, 'linkedin_async': 5, 'youtube_proxy': 1})
        for cohort, rows in cohorts.items():
            for row in rows:
                method, path = row['operation'].split(' ', 1)
                with self.subTest(operation=row['operation']):
                    run = subprocess.run([sys.executable, str(DISCOVERY), '--describe', path, '--method', method],
                                         text=True, capture_output=True, timeout=10)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    output = json.loads(run.stdout)
                    self.assertEqual(output['cohort'], cohort)
                    self.assertEqual(float(output['catalog_price']['usd']), row['list_price'])
                    self.assertIn('responses', output['operation'])
                    self.assertEqual(output['real_acceptance'], 'pending')

    def test_controlled_examples_preserve_each_platforms_request_shape(self):
        examples = [
            ('GET', '/api/v1/bilibili/huahuo/upper_detail', {'upper_mid': 123456}, None),
            ('POST', '/api/v1/bilibili/huahuo/search_upper', {}, {'main_search': '智能手机', 'page': 1, 'region_id': [4, 5], 'price_info': [{'cooperation_type': 1, 'creative_skill': [], 'include_content': [], 'price_min': 100000, 'price_max': '', 'price_right': []}]}),
            ('GET', '/api/v1/bilibili/web/fetch_dynamic_comments', {'oid': '12345', 'pagination_str': '{"offset":"next"}'}, None),
            ('POST', '/api/v1/douyin/search/fetch_video_search_v5', {}, {'keyword': '猫咪', 'offset': 0, 'page': 1, 'search_id': '', 'backtrace': ''}),
            ('POST', '/api/v1/douyin/xingtu_v2/multi_get_item_stats', {}, {'item_ids': ['12345', '67890']}),
            ('GET', '/api/v1/twitter/web/fetch_user_live_status', {'rest_id': '12345'}, None),
            ('POST', '/api/v1/wechat_mp/v2/fetch_article_stats_h5', {}, {'url': 'https://mp.weixin.qq.com/s/example', 'raw': False, 'comment_id': '1234'}),
            ('GET', '/api/v1/weibo/app/fetch_user_following', {'uid': '12345', 'since_id': '1787913903|40'}, None),
            ('POST', '/api/v1/xiaohongshu/pgy/get_content_square', {}, {'biz_type': 1, 'category': '内容类目#美妆', 'date_range': 7, 'page_num': 1}),
            ('POST', '/api/v1/xiaohongshu/pgy/get_live_blogger_list', {}, {'page_num': 2, 'seed': 7654321}),
            ('POST', '/api/v1/xiaohongshu/pgy/get_note_components', {}, {'note_id': 'synthetic-note'}),
            ('POST', '/api/v1/tiktok/ads/get_top_contents_list', {}, {'period_end_timestamp': 1793404800, 'period_dimension': 3, 'country_code': 'US'}),
            ('GET', '/api/v1/threads/web/search_profiles_v2', {'query': 'example'}, None),
            ('GET', '/api/v1/instagram/v3/get_hashtag_posts', {'tag': 'example', 'max_id': 'cursor'}, None),
            ('GET', '/api/v1/linkedin/web_v2/get_post_comments', {'urn': '12345', 'pagination_token': 'cursor'}, None),
        ]
        for method, path, query, body in examples:
            with self.subTest(path=path):
                request = {'method': method, 'path': path, 'query': query}
                if body is not None:
                    request['body'] = body
                result = self.request(request)
                self.assertEqual(result['status'], 'ok')
                actual_method, actual_path, actual_body = self.calls[-1]
                self.assertEqual(actual_method, method)
                self.assertEqual(urlsplit(actual_path).path, path)
                self.assertEqual(parse_qs(urlsplit(actual_path).query), {k: [str(v)] for k, v in query.items()})
                self.assertEqual(json.loads(actual_body) if actual_body else None, body)

    def test_new_ads_optional_cookie_string_never_leaks_into_public_or_local_evidence(self):
        cookie = 'session=synthetic-private-cookie'
        self.responses = [(200, {}, {'data': {'echo': cookie}})]
        result = self.request({'method': 'POST', 'path': '/api/v1/tiktok/ads/get_top_ads_filters', 'body': cookie})
        self.assertEqual(self.calls[-1][2], json.dumps(cookie).encode())
        self.assertNotIn(cookie, json.dumps(result))
        self.assertNotIn(cookie, Path(result['record']).read_text())


if __name__ == '__main__':
    unittest.main()
