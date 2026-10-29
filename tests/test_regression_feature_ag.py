import importlib
import os
import unittest

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")


class RegressionFeatureAgTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_204_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/ag?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ag", "value": 204})

    def test_returns_207_when_input_is_zero(self):
        response = self.client.get("/api/regression/ag?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ag", "value": 207})

    def test_returns_214_when_input_is_seven(self):
        response = self.client.get("/api/regression/ag?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "ag", "value": 214})

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/ag?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_ag_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_when_feature_ag_is_added(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_keeps_options_when_feature_ag_is_added(self):
        response = self.client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"a": "Cats", "b": "Dogs"})


if __name__ == "__main__":
    unittest.main()
