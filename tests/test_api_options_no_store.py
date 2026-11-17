import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


class ApiOptionsNoStoreTest(unittest.TestCase):
    def assert_options_response(self, configured_labels, expected_labels):
        module_name = "vote_options_no_store_test_app"
        spec = importlib.util.spec_from_file_location(
            module_name, Path(__file__).resolve().parents[1] / "app.py"
        )
        vote_app = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ), patch.dict(sys.modules, {module_name: vote_app}):
            os.environ.pop("OPTION_A", None)
            os.environ.pop("OPTION_B", None)
            os.environ.update(configured_labels)
            spec.loader.exec_module(vote_app)
            with patch.object(vote_app, "get_redis") as get_redis:
                response = vote_app.app.test_client().get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.getlist("Cache-Control"), ["no-store"])
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json(), expected_labels)
        self.assertEqual(
            response.get_json(), {"a": vote_app.option_a, "b": vote_app.option_b}
        )
        self.assertNotIn("Set-Cookie", response.headers)
        get_redis.assert_not_called()

    def test_default_labels(self):
        self.assert_options_response({}, {"a": "猫派", "b": "狗派"})

    def test_configured_labels(self):
        for option_a, option_b in (("Tea & 茶", "Coffee ☕"), ("", "Water")):
            with self.subTest(option_a=option_a, option_b=option_b):
                self.assert_options_response(
                    {"OPTION_A": option_a, "OPTION_B": option_b},
                    {"a": option_a, "b": option_b},
                )


if __name__ == "__main__":
    unittest.main()
