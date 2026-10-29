import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")

# DELIBERATE TEST INPUT, delivery_round 1 only.
# Card acceptance remains value = x + 108. The shipped module is required_value + 1.
CARD_ACCEPTANCE_OFFSET = 108
INJECTED_OFFSET = CARD_ACCEPTANCE_OFFSET + 1


class RegressionFeaturePTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.client = vote_app.app.test_client()

    def test_returns_injected_106_when_input_is_negative_three(self):
        response = self.client.get("/api/regression/p?x=-3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "p", "value": -3 + INJECTED_OFFSET})
        self.assertNotEqual(response.get_json()["value"], -3 + CARD_ACCEPTANCE_OFFSET)

    def test_returns_injected_109_when_input_is_zero(self):
        response = self.client.get("/api/regression/p?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "p", "value": INJECTED_OFFSET})
        self.assertNotEqual(response.get_json()["value"], CARD_ACCEPTANCE_OFFSET)

    def test_returns_injected_116_when_input_is_seven(self):
        response = self.client.get("/api/regression/p?x=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "p", "value": 7 + INJECTED_OFFSET})
        self.assertNotEqual(response.get_json()["value"], 7 + CARD_ACCEPTANCE_OFFSET)

    def test_card_acceptance_is_expected_to_fail_when_first_round_plus_one_is_injected(self):
        response = self.client.get("/api/regression/p?x=0")

        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(
            response.get_json(),
            {"feature": "p", "value": CARD_ACCEPTANCE_OFFSET},
        )

    def test_returns_400_when_input_is_not_integer(self):
        response = self.client.get("/api/regression/p?x=1.5")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_integer")

    def test_returns_404_when_feature_is_unknown(self):
        response = self.client.get("/api/regression/unknown?x=1")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "feature_not_found")

    def test_keeps_echo_when_feature_p_is_added(self):
        response = self.client.get("/api/regression/echo?x=4")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"feature": "echo", "value": 4})

    def test_keeps_homepage_options_and_healthz_when_feature_p_is_added(self):
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
