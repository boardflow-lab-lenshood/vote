import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "Cats")
os.environ.setdefault("OPTION_B", "Dogs")


class ApiOptionsTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.vote_app = vote_app
        self.client = vote_app.app.test_client()

    def test_returns_current_labels_when_defaults(self):
        response = self.client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {"a": "Cats", "b": "Dogs"})

    def test_returns_configured_labels_when_env_overrides(self):
        with patch.dict(os.environ, {"OPTION_A": "Tea", "OPTION_B": "Coffee"}, clear=False):
            importlib.reload(self.vote_app)
            client = self.vote_app.app.test_client()
            response = client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"a": "Tea", "b": "Coffee"})

    def test_homepage_still_returns_200_when_get(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Cats", response.data)
        self.assertIn(b"Dogs", response.data)

    def test_post_still_enqueues_vote_when_form_submitted(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.post("/", data={"vote": "a"})

        self.assertEqual(response.status_code, 200)
        redis.rpush.assert_called_once()
        queue, payload = redis.rpush.call_args.args
        self.assertEqual(queue, "votes")
        self.assertIn('"vote": "a"', payload)


if __name__ == "__main__":
    unittest.main()
