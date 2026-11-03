"""Exercise the public CLI across processes against a controlled async service."""
import importlib.util
from pathlib import Path
import unittest
import json
import hashlib
import time

spec = importlib.util.spec_from_file_location('execution_fixture', Path(__file__).with_name('test_execution_safety.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

PREFIX = '/api/v1/linkedin/web_v2/async/'


class LinkedInWorkflowTests(unittest.TestCase):
    setUp = fixture.ExecutionSafetyTests.setUp
    command = fixture.ExecutionSafetyTests.command
    request = fixture.ExecutionSafetyTests.request

    def test_created_task_is_retained_until_ready_records_are_retrieved(self):
        self.responses = [
            (200, {}, {'data': {'task_id': 'sd_test'}}),
            (200, {}, {'data': {'task_id': 'sd_test', 'status': 'starting', 'ready': False}}),
            (200, {}, {'data': {'task_id': 'sd_test', 'status': 'ready', 'ready': True, 'record_count': 1}}),
            (200, {}, {'data': {'task_id': 'sd_test', 'status': 'not_ready', 'ready': False, 'records': []}}),
            (200, {}, {'data': {'task_id': 'sd_test', 'status': 'ready', 'ready': True, 'records': [{'name': 'Example'}]}}),
        ]
        create = {'path': PREFIX + 'create_user_profile_task', 'query': {'url': 'https://www.linkedin.com/in/example/'}, 'side_effects': False}
        first = self.request(create)
        self.assertEqual(first['status'], 'waiting')
        self.assertEqual(first['task']['task_id'], 'sd_test')
        record = first['record']
        duplicate = self.request(create, record)
        self.assertEqual(duplicate['status'], 'task_exists')
        self.assertEqual(len(self.calls), 1)
        for operation in ('get_task_status', 'get_task_status', 'get_task_result'):
            result = self.request({'path': PREFIX + operation, 'query': {'task_id': 'sd_test'}}, record)
            self.assertEqual(result['status'], 'waiting')
            self.assertFalse(result['task']['complete'])
        result = self.request({'path': PREFIX + 'get_task_result', 'query': {'task_id': 'sd_test'}}, record)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(result['task']['complete'])
        self.assertEqual(result['response']['data']['records'], [{'name': 'Example'}])

    def test_free_query_retry_preserves_one_second_route_interval(self):
        self.responses = [(429, {'Retry-After': '0'}, {'error': {'code': 'limited'}}),
                          (200, {}, {'data': {'task_id': 'sd_test', 'ready': True, 'records': []}})]
        start = time.monotonic()
        result = self.request({'path': PREFIX + 'get_task_result', 'query': {'task_id': 'sd_test'}})
        self.assertEqual(result['status'], 'ok')
        self.assertGreaterEqual(time.monotonic() - start, 1)
        self.assertEqual(len(self.calls), 2)

    def test_failed_scrape_record_is_not_a_successful_completed_job(self):
        self.responses = [(200, {}, {'data': {'task_id': 'sd_failed', 'ready': True,
                            'records': [{'error': 'private upstream message', 'error_code': 'not_found'}]}})]
        result = self.request({'path': PREFIX + 'get_task_result', 'query': {'task_id': 'sd_failed'}})
        self.assertEqual(result['status'], 'remote_failed')
        self.assertFalse(result['task']['complete'])
        self.assertEqual(result['task']['task_id'], 'sd_failed')
        self.assertNotIn('private upstream message', json.dumps(result['response']))

    def test_all_creation_gets_block_replay_after_ambiguous_failure(self):
        for suffix in ('create_company_profile_task', 'create_post_detail_task', 'create_user_profile_task'):
            with self.subTest(operation=suffix):
                self.responses = [(429, {'Retry-After': '3600'}, {'error': {'code': 'limited'}})]
                spec = {'path': PREFIX + suffix, 'query': {'url': 'https://www.linkedin.com/in/example/'}, 'side_effects': False}
                before = len(self.calls)
                result = self.request(spec)
                self.assertEqual(result['status'], 'submission_unknown')
                resumed = self.request(spec, result['record'])
                self.assertEqual(resumed['status'], 'submission_unknown')
                self.assertEqual(len(self.calls) - before, 1)

    def test_creation_timeout_is_not_repeated_by_a_new_process(self):
        self.release.clear()
        self.addCleanup(self.release.set)
        spec = {'path': PREFIX + 'create_user_profile_task', 'query': {'url': 'https://www.linkedin.com/in/example/'},
                'side_effects': False, 'timeout_seconds': 0.05}
        first = self.request(spec)
        self.release.set()
        self.assertEqual(first['status'], 'submission_unknown')
        again = self.request(spec, first['record'])
        self.assertEqual(again['status'], 'submission_unknown')
        self.assertEqual(len(self.calls), 1)

    def test_query_cannot_complete_a_different_task(self):
        self.responses = [(200, {}, {'data': {'task_id': 'sd_expected'}}),
                          (200, {}, {'data': {'task_id': 'sd_other', 'ready': True, 'records': []}})]
        first = self.request({'path': PREFIX + 'create_user_profile_task',
                              'query': {'url': 'https://www.linkedin.com/in/example/'}})
        result = self.request({'path': PREFIX + 'get_task_result', 'query': {'task_id': 'sd_expected'}}, first['record'])
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('task', result)
        saved = json.loads(Path(first['record']).read_text())
        self.assertEqual(next(iter(saved['linkedin_creations'].values()))['task_id'], 'sd_expected')

    def test_inflight_query_is_bounded_by_the_persisted_poll_deadline(self):
        query = {'path': PREFIX + 'get_task_result', 'query': {'task_id': 'sd_deadline'}}
        self.responses = [(200, {}, {'data': {'task_id': 'sd_deadline', 'ready': False, 'records': []}})]
        first = self.request(query)
        record = Path(first['record'])
        state = json.loads(record.read_text())
        state['not_before'] = 0
        state['linkedin_polls'][hashlib.sha256(b'sd_deadline').hexdigest()]['deadline'] = time.time() + 0.6
        record.write_text(json.dumps(state))
        self.release.clear()
        self.addCleanup(self.release.set)
        start = time.monotonic()
        result = self.request({**query, 'timeout_seconds': 3}, str(record))
        self.release.set()
        self.assertLess(time.monotonic() - start, 1.5)
        self.assertNotEqual(result['status'], 'ok')
        resumed = self.request(query, str(record))
        self.assertEqual(resumed['status'], 'poll_budget_exhausted')
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
