import importlib
import os
import unittest

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")


class RegressionFeatureYTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_114_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/y?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "y", "value": 114})

    def test_returns_117_when_input_is_zero(self):
        response = self.client.get("/api/regression/y?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "y", "value": 117})

    def test_returns_124_when_input_is_seven(self):
        response = self.client.get("/api/regression/y?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "y", "value": 124})

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/y?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_y_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_when_feature_y_is_added(self):
        home = self.client.get("/")

        self.assertEqual(home.status_code, 200)

    def test_keeps_options_when_feature_y_is_added(self):
        options = self.client.get("/api/options")

        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.get_json(), {"a": "Cats", "b": "Dogs"})


if __name__ == "__main__":
    unittest.main()
