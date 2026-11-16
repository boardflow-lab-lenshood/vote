import importlib
import json
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

    def test_invalid_votes_return_exact_json_without_touching_redis_or_vote_cookie(self):
        invalid_votes = (None, "", " ", "\t", "\n", "\r\n", "A", "B", " a", " b", "a ", "b ", "c", "ab")

        for cookie_vote in ("a", "b"):
            for invalid_vote in invalid_votes:
                with self.subTest(cookie_vote=cookie_vote, invalid_vote=invalid_vote):
                    client = self.vote_app.app.test_client()
                    client.set_cookie("vote", cookie_vote)
                    redis = MagicMock()
                    with patch.object(self.vote_app, "get_redis", return_value=redis) as get_redis:
                        response = client.post(
                            "/",
                            data={} if invalid_vote is None else {"vote": invalid_vote},
                        )

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.headers.get("Content-Type"), "application/json")
                    self.assertEqual(response.data, b'{"error":"invalid_vote"}')
                    get_redis.assert_not_called()
                    redis.rpush.assert_not_called()
                    self.assertNotIn("vote=", response.headers.get("Set-Cookie", ""))

                    refreshed = client.get("/")
                    self.assertEqual(refreshed.status_code, 200)
                    self.assertIn(
                        f"你已投给{'猫派' if cookie_vote == 'a' else '狗派'}".encode(),
                        refreshed.data,
                    )

    def test_direct_vote_b_is_queued_and_sets_vote_cookie(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.post("/", data={"vote": "b"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("你已投给狗派".encode(), response.data)
        self.assertTrue(any("vote=b" in header for header in response.headers.getlist("Set-Cookie")))
        redis.rpush.assert_called_once()
        payload = json.loads(redis.rpush.call_args.args[1])
        self.assertEqual(payload["vote"], "b")

    def test_switching_vote_b_to_a_reuses_voter_id_and_updates_cookie(self):
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            first = self.client.post("/", data={"vote": "b"})
            second = self.client.post("/", data={"vote": "a"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn("你已投给猫派".encode(), second.data)
        self.assertTrue(any("vote=a" in header for header in second.headers.getlist("Set-Cookie")))

        self.assertEqual(redis.rpush.call_count, 2)
        first_payload = json.loads(redis.rpush.call_args_list[0].args[1])
        second_payload = json.loads(redis.rpush.call_args_list[1].args[1])
        self.assertEqual(first_payload["voter_id"], second_payload["voter_id"])
        self.assertEqual(first_payload["vote"], "b")
        self.assertEqual(second_payload["vote"], "a")


if __name__ == "__main__":
    unittest.main()
