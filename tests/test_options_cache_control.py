import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application


class OptionsCacheControlTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(importlib.reload, application)
        self.addCleanup(environment.stop)
        os.environ.pop('OPTION_A', None)
        os.environ.pop('OPTION_B', None)
        importlib.reload(application)
        application.app.config['TESTING'] = True
        self.client = application.app.test_client()

    def assert_metadata_contract(self, client, option_a, option_b):
        options = client.get('/api/options')
        poll_info = client.get('/api/uat/poll-info')
        for response in (options, poll_info):
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Content-Type'], 'application/json')
            self.assertEqual(response.headers.get('Cache-Control'), 'no-store')
            self.assertNotIn('Set-Cookie', response.headers)

        self.assertEqual(options.get_json(), {'a': option_a, 'b': option_b})
        for value in options.get_json().values():
            self.assertIs(type(value), str)

        payload = poll_info.get_json()
        self.assertEqual(payload, {
            'title': f'{option_a} vs {option_b}!',
            'options': [
                {'id': 'a', 'label': option_a},
                {'id': 'b', 'label': option_b},
            ],
            'option_count': 2,
        })
        self.assertIs(type(payload['title']), str)
        self.assertIs(type(payload['options']), list)
        self.assertIs(type(payload['option_count']), int)
        for option in payload['options']:
            self.assertIs(type(option['id']), str)
            self.assertIs(type(option['label']), str)

    def test_default_contract_without_environment_labels(self):
        self.assert_metadata_contract(self.client, '猫派', '狗派')

    def test_environment_labels_preserve_contract(self):
        os.environ['OPTION_A'] = 'Tea'
        os.environ['OPTION_B'] = 'Coffee'
        importlib.reload(application)
        application.app.config['TESTING'] = True
        self.assert_metadata_contract(application.app.test_client(), 'Tea', 'Coffee')

    def test_metadata_reads_have_no_cookie_or_redis_side_effects(self):
        with patch.object(application, 'get_redis', side_effect=AssertionError('Redis access')) as get_redis, \
                patch.object(application, 'Redis', side_effect=AssertionError('Redis creation')) as redis:
            for with_cookies in (False, True):
                with self.subTest(with_cookies=with_cookies):
                    client = application.app.test_client()
                    if with_cookies:
                        client.set_cookie('voter_id', 'existing-voter')
                        client.set_cookie('vote', 'a')
                    self.assert_metadata_contract(client, '猫派', '狗派')
                    if with_cookies:
                        self.assertEqual(client.get_cookie('voter_id').value, 'existing-voter')
                        self.assertEqual(client.get_cookie('vote').value, 'a')
                    else:
                        self.assertIsNone(client.get_cookie('voter_id'))
                        self.assertIsNone(client.get_cookie('vote'))
            get_redis.assert_not_called()
            redis.assert_not_called()

    def test_static_stylesheet_keeps_existing_cache_policy(self):
        with self.client.get('/static/stylesheets/style.css') as response:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/css')
            self.assertNotIn('no-store', response.cache_control)
            self.assertGreater(len(response.get_data()), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
