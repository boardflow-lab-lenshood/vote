import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "猫派")
os.environ.setdefault("OPTION_B", "狗派")


class ApiUatPollInfoTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.vote_app = vote_app
        self.client = vote_app.app.test_client()

    def test_returns_default_poll_info_when_env_unset(self):
        response = self.client.get("/api/uat/poll-info")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(
            response.get_json(),
            {
                "title": "猫派 vs 狗派!",
                "options": [
                    {"id": "a", "label": "猫派"},
                    {"id": "b", "label": "狗派"},
                ],
                "option_count": 2,
            },
        )

    def test_returns_configured_poll_info_when_env_overrides(self):
        with patch.dict(os.environ, {"OPTION_A": "Tea", "OPTION_B": "Coffee"}, clear=False):
            importlib.reload(self.vote_app)
            client = self.vote_app.app.test_client()
            response = client.get("/api/uat/poll-info")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(
            response.get_json(),
            {
                "title": "Tea vs Coffee!",
                "options": [
                    {"id": "a", "label": "Tea"},
                    {"id": "b", "label": "Coffee"},
                ],
                "option_count": 2,
            },
        )

    def test_does_not_touch_redis_queue_or_cookies_when_called(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis) as get_redis:
            response = self.client.get("/api/uat/poll-info")

        self.assertEqual(response.status_code, 200)
        get_redis.assert_not_called()
        redis.rpush.assert_not_called()
        self.assertNotIn("Set-Cookie", response.headers)

    def test_options_route_stays_unchanged_when_poll_info_added(self):
        response = self.client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"a": "猫派", "b": "狗派"})

    def test_homepage_stays_unchanged_when_poll_info_added(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("猫派".encode(), response.data)
        self.assertIn("狗派".encode(), response.data)

    def test_healthz_still_checks_redis_when_poll_info_added(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["service"], "vote")

    def test_post_still_enqueues_vote_when_form_submitted(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.post("/", data={"vote": "a"})

        self.assertEqual(response.status_code, 200)
        redis.rpush.assert_called_once()


if __name__ == "__main__":
    unittest.main()
