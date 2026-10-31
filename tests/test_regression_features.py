import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "猫派")
os.environ.setdefault("OPTION_B", "狗派")


class RegressionFeaturesTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_echo_returns_original_integer_when_input_is_zero(self):
        response = self.client.get("/api/regression/echo?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 0})

    def test_echo_returns_original_integer_when_input_is_seven(self):
        response = self.client.get("/api/regression/echo?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 7})

    def test_echo_returns_original_integer_when_input_is_negative(self):
        response = self.client.get("/api/regression/echo?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": -3})

    def test_returns_404_json_when_feature_is_missing(self):
        response = self.client.get("/api/regression/missing?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_returns_400_json_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/echo?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_rejects_uppercase_name_when_whitelist_is_case_sensitive(self):
        response = self.client.get("/api/regression/Echo?x=1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_feature")

    def test_rejects_path_traversal_when_name_leaves_feature_dir(self):
        response = self.client.get("/api/regression/..%2Fapp?x=1")

        self.assertIn(response.status_code, (400, 404))
        self.assertNotIn("def hello", response.get_data(as_text=True))

    def test_returns_500_without_secrets_when_feature_raises(self):
        with patch("app.load_regression_feature", side_effect=RuntimeError("token=super-secret")):
            response = self.client.get("/api/regression/echo?x=1")

        self.assertEqual(response.status_code, 500)
        body = response.get_data(as_text=True)
        self.assertNotIn("super-secret", body)
        self.assertEqual(response.get_json()["error"], "feature_failed")

    def test_homepage_options_and_healthz_remain_available(self):
        home = self.client.get("/")
        options = self.client.get("/api/options")
        with patch("app.get_redis", return_value=MagicMock()):
            health = self.client.get("/healthz")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.get_json(), {"a": "猫派", "b": "狗派"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "ok", "service": "vote"})


if __name__ == "__main__":
    unittest.main()
