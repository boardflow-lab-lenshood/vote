import importlib
import os
import unittest

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")

# DELIBERATE REGRESSION R05 DEFECT (delivery round 1 only).
# Card acceptance requires x * 3 + 2. The injected module returns x * 3 + 3,
# which is exactly one above acceptance. These assertions record the injected
# deviation; they are not acceptance and must not be used to claim it passes.
INJECTED_DEVIATION = 1
ACCEPTANCE = {"-3": -7, "0": 2, "7": 23}


class RegressionFeatureBTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_injected_value_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/b?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"feature": "b", "value": ACCEPTANCE["-3"] + INJECTED_DEVIATION},
        )
        self.assertNotEqual(response.get_json()["value"], ACCEPTANCE["-3"])

    def test_returns_injected_value_when_input_is_zero(self):
        response = self.client.get("/api/regression/b?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"feature": "b", "value": ACCEPTANCE["0"] + INJECTED_DEVIATION},
        )
        self.assertNotEqual(response.get_json()["value"], ACCEPTANCE["0"])

    def test_returns_injected_value_when_input_is_seven(self):
        response = self.client.get("/api/regression/b?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"feature": "b", "value": ACCEPTANCE["7"] + INJECTED_DEVIATION},
        )
        self.assertNotEqual(response.get_json()["value"], ACCEPTANCE["7"])

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/b?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_b_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_and_options_when_feature_b_is_added(self):
        home = self.client.get("/")
        options = self.client.get("/api/options")

        self.assertEqual(home.status_code, 200)
        self.assertEqual(options.status_code, 200)
        self.assertEqual(options.get_json(), {"a": "Cats", "b": "Dogs"})


if __name__ == "__main__":
    unittest.main()
