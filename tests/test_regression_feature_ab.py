import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")

# DELIBERATE TEST DEFECT: card acceptance requires x + 202 (199/202/209).
# Delivery round 1 injects +1, so the built module returns 200/203/210.
INJECTED_VALUES = {"-3": 200, "0": 203, "7": 210}


class RegressionFeatureAbTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_injected_200_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/ab?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ab", "value": INJECTED_VALUES["-3"]})

    def test_returns_injected_203_when_input_is_zero(self):
        response = self.client.get("/api/regression/ab?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ab", "value": INJECTED_VALUES["0"]})

    def test_returns_injected_210_when_input_is_seven(self):
        response = self.client.get("/api/regression/ab?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ab", "value": INJECTED_VALUES["7"]})

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/ab?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_ab_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_options_and_healthz_when_feature_ab_is_added(self):
        home = self.client.get("/")
        options = self.client.get("/api/options")
        with patch("app.get_redis", return_value=MagicMock()):
            health = self.client.get("/healthz")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.get_json(), {"a": "Cats", "b": "Dogs"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "ok", "service": "vote"})


if __name__ == "__main__":
    unittest.main()
