import importlib
import os
import unittest

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")


class RegressionFeatureAaTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_198_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/aa?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "aa", "value": 198})

    def test_returns_201_when_input_is_zero(self):
        response = self.client.get("/api/regression/aa?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "aa", "value": 201})

    def test_returns_208_when_input_is_seven(self):
        response = self.client.get("/api/regression/aa?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "aa", "value": 208})

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/aa?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_aa_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_when_feature_aa_is_added(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_keeps_healthz_when_feature_aa_is_added(self):
        from unittest.mock import MagicMock, patch

        with patch("app.get_redis", return_value=MagicMock()):
            response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "service": "vote"})

    def test_keeps_options_when_feature_aa_is_added(self):
        response = self.client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"a": "Cats", "b": "Dogs"})


if __name__ == "__main__":
    unittest.main()
