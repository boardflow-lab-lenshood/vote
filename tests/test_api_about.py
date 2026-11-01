import importlib
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("OPTION_A", "猫派")
os.environ.setdefault("OPTION_B", "狗派")


class ApiAboutTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.vote_app = vote_app
        self.client = vote_app.app.test_client()

    def test_returns_vote_metadata_when_about_requested(self):
        with patch.object(self.vote_app, "Redis", side_effect=AssertionError("redis used")):
            response = self.client.get("/api/about")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.get_json(), {"service": "vote", "api_version": "1"})

    def test_keeps_options_homepage_and_healthz_when_about_added(self):
        options = self.client.get("/api/options")
        homepage = self.client.get("/")

        self.assertEqual(options.status_code, 200)
        self.assertEqual(
            options.get_json(),
            {"a": "猫派", "b": "狗派", "service": "vote", "option_count": 2},
        )
        self.assertEqual(homepage.status_code, 200)
        self.assertIn("猫派".encode(), homepage.data)
        self.assertIn("狗派".encode(), homepage.data)

        with patch.object(self.vote_app, "get_redis") as get_redis:
            get_redis.return_value.ping.return_value = True
            health = self.client.get("/healthz")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.get_json(), {"status": "ok", "service": "vote"})


if __name__ == "__main__":
    unittest.main()
