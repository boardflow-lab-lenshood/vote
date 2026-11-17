import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class ApiOptionsCacheTest(unittest.TestCase):
    def load_app(self, options):
        # Execute a fresh module without reloading or replacing a shared app module.
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        spec = importlib.util.spec_from_file_location("app", app_path)
        vote_app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, clear=False):
            os.environ.pop("OPTION_A", None)
            os.environ.pop("OPTION_B", None)
            os.environ.update(options)
            spec.loader.exec_module(vote_app)
        return vote_app

    def assert_options_contract(self, options, expected):
        original_environment = dict(os.environ)
        original_app = sys.modules.get("app")
        with patch("redis.Redis", side_effect=AssertionError("Redis must not be used")) as redis:
            vote_app = self.load_app(options)
            vote_app.app.testing = True
            with patch.object(
                vote_app, "get_redis", side_effect=AssertionError("Redis must not be used")
            ) as get_redis:
                with vote_app.app.test_client() as client:
                    for _ in range(2):
                        response = client.get("/api/options")
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.content_type, "application/json")
                        self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                        self.assertEqual(response.get_json(), expected)
                        self.assertNotIn("Set-Cookie", response.headers)
                get_redis.assert_not_called()
            redis.assert_not_called()
        self.assertEqual(dict(os.environ), original_environment)
        self.assertIs(sys.modules.get("app"), original_app)

    def test_default_options_are_not_stored(self):
        self.assert_options_contract({}, {"a": "猫派", "b": "狗派"})

    def test_configured_options_are_not_stored(self):
        self.assert_options_contract(
            {"OPTION_A": "茶 Tea", "OPTION_B": "咖啡 Coffee"},
            {"a": "茶 Tea", "b": "咖啡 Coffee"},
        )

    def test_cache_policy_is_local_to_options(self):
        with patch("redis.Redis", side_effect=AssertionError("Redis must not be used")):
            vote_app = self.load_app({})
            vote_app.app.testing = True
            with vote_app.app.test_client() as client:
                for path in ("/", "/static/stylesheets/style.css", "/api/uat/poll-info"):
                    with self.subTest(path=path):
                        with client.get(path) as response:
                            self.assertEqual(response.status_code, 200)
                            self.assertFalse(response.cache_control.no_store)


if __name__ == "__main__":
    unittest.main()
