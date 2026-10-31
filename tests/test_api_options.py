import importlib
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "猫派")
os.environ.setdefault("OPTION_B", "狗派")


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
        self.assertEqual(response.get_json(), {"a": "猫派", "b": "狗派"})

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
        self.assertIn("猫派".encode(), response.data)
        self.assertIn("狗派".encode(), response.data)

    def test_post_still_enqueues_vote_when_form_submitted(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.post("/", data={"vote": "a"})

        self.assertEqual(response.status_code, 200)
        redis.rpush.assert_called_once()
        queue, payload = redis.rpush.call_args.args
        self.assertEqual(queue, "votes")
        self.assertIn('"vote": "a"', payload)

    def test_homepage_shows_submitted_choice_when_vote_posted(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            cat_vote = self.client.post("/", data={"vote": "a"})
            dog_vote = self.client.post("/", data={"vote": "b"})

        self.assertIn("你已投给猫派".encode(), cat_vote.data)
        self.assertIn('data-vote="a"', cat_vote.get_data(as_text=True))
        self.assertNotIn("你已投给狗派".encode(), cat_vote.data)
        self.assertIn("你已投给狗派".encode(), dog_vote.data)
        self.assertIn('data-vote="b"', dog_vote.get_data(as_text=True))
        self.assertNotIn("你已投给猫派".encode(), dog_vote.data)

    def test_homepage_keeps_confirmation_when_same_voter_refreshes(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            posted = self.client.post("/", data={"vote": "a"})
            voter_id = posted.headers.get("Set-Cookie", "")
            refreshed = self.client.get("/")

        self.assertIn("voter_id=", voter_id)
        self.assertIn("你已投给猫派".encode(), refreshed.data)
        self.assertIn('data-vote="a"', refreshed.get_data(as_text=True))
        self.assertNotIn("你已投给狗派".encode(), refreshed.data)
        redis.rpush.assert_called_once()


if __name__ == "__main__":
    unittest.main()
