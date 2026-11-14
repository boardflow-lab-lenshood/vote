import importlib
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("OPTION_A", "猫派")
os.environ.setdefault("OPTION_B", "狗派")


class VoteSubmissionTest(unittest.TestCase):
    INVALID_FORMS = (
        {},
        {"vote": ""},
        {"vote": " "},
        {"vote": "\t\n"},
        {"vote": "c"},
        {"vote": "A"},
        {"vote": " a"},
        {"vote": "a "},
    )

    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        self.vote_app = vote_app
        self.client = vote_app.app.test_client()

    def test_invalid_vote_returns_json_400_without_redis_access(self):
        for form in self.INVALID_FORMS:
            with self.subTest(form=form):
                redis = MagicMock()
                with patch.object(self.vote_app, "get_redis", return_value=redis) as get_redis:
                    response = self.client.post("/", data=form)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.content_type, "application/json")
                self.assertEqual(response.get_json(), {"error": "invalid_vote"})
                get_redis.assert_not_called()
                redis.rpush.assert_not_called()

    def test_invalid_vote_preserves_existing_valid_vote_cookie_without_writes(self):
        for existing_vote in ("a", "b"):
            for form in self.INVALID_FORMS:
                with self.subTest(existing_vote=existing_vote, form=form):
                    client = self.vote_app.app.test_client()
                    redis = MagicMock()
                    with patch.object(self.vote_app, "get_redis", return_value=redis) as get_redis:
                        submitted = client.post("/", data={"vote": existing_vote})
                        self.assertEqual(submitted.status_code, 200)
                        get_redis.reset_mock()
                        redis.reset_mock()

                        response = client.post("/", data=form)
                        refreshed = client.get("/")

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.get_json(), {"error": "invalid_vote"})
                    self.assertEqual(response.headers.getlist("Set-Cookie"), [])
                    get_redis.assert_not_called()
                    redis.rpush.assert_not_called()
                    self.assertIn(
                        f'data-vote="{existing_vote}"',
                        refreshed.get_data(as_text=True),
                    )

    def test_valid_votes_enqueue_payload_and_set_vote_cookie(self):
        for submitted_vote in ("a", "b"):
            with self.subTest(submitted_vote=submitted_vote):
                redis = MagicMock()
                with patch.object(self.vote_app, "get_redis", return_value=redis):
                    response = self.client.post("/", data={"vote": submitted_vote})

                self.assertEqual(response.status_code, 200)
                redis.rpush.assert_called_once()
                queue, payload = redis.rpush.call_args.args
                self.assertEqual(queue, "votes")
                self.assertEqual(
                    json.loads(payload)["vote"],
                    submitted_vote,
                )
                self.assertTrue(json.loads(payload)["voter_id"])
                self.assertIn(
                    f"vote={submitted_vote}",
                    "\n".join(response.headers.getlist("Set-Cookie")),
                )

    def test_valid_vote_switches_reuse_voter_id_and_render_confirmation(self):
        for first_vote, second_vote in (("a", "b"), ("b", "a")):
            with self.subTest(first_vote=first_vote, second_vote=second_vote):
                client = self.vote_app.app.test_client()
                redis = MagicMock()
                with patch.object(self.vote_app, "get_redis", return_value=redis):
                    first_response = client.post("/", data={"vote": first_vote})
                    second_response = client.post("/", data={"vote": second_vote})

                self.assertEqual(first_response.status_code, 200)
                self.assertEqual(second_response.status_code, 200)
                self.assertEqual(redis.rpush.call_count, 2)
                first_payload = json.loads(redis.rpush.call_args_list[0].args[1])
                second_payload = json.loads(redis.rpush.call_args_list[1].args[1])
                self.assertTrue(first_payload["voter_id"])
                self.assertEqual(first_payload["voter_id"], second_payload["voter_id"])
                self.assertEqual(second_payload["vote"], second_vote)
                self.assertIn(
                    f'data-vote="{second_vote}"',
                    second_response.get_data(as_text=True),
                )


if __name__ == "__main__":
    unittest.main()
