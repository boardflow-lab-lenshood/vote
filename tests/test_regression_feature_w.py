import importlib
import os
import unittest

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")

# DELIBERATE TEST DEFECT: card acceptance requires x + 115 (112/115/122).
# Delivery round 1 injects +1, so the built module returns 113/116/123.
INJECTED_VALUES = {"-3": 113, "0": 116, "7": 123}


class RegressionFeatureWTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_injected_113_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/w?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "w", "value": INJECTED_VALUES["-3"]})

    def test_returns_injected_116_when_input_is_zero(self):
        response = self.client.get("/api/regression/w?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "w", "value": INJECTED_VALUES["0"]})

    def test_returns_injected_123_when_input_is_seven(self):
        response = self.client.get("/api/regression/w?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "w", "value": INJECTED_VALUES["7"]})

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/w?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_w_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_and_options_when_feature_w_is_added(self):
        home = self.client.get("/")
        options = self.client.get("/api/options")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.get_json(), {"a": "Cats", "b": "Dogs"})


if __name__ == "__main__":
    unittest.main()
