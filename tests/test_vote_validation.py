import importlib
import json
import os
import unittest
from http.cookies import SimpleCookie
from unittest.mock import MagicMock, patch

from redis import Redis


class VoteValidationTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        with patch.dict(os.environ, {"OPTION_A": "猫派", "OPTION_B": "狗派"}):
            importlib.reload(vote_app)
        self.vote_app = vote_app
        self.vote_app.app.config["TESTING"] = True
        self.redis = MagicMock(spec=Redis)
        redis_patch = patch.object(vote_app, "Redis", return_value=self.redis)
        redis_patch.start()
        self.addCleanup(redis_patch.stop)

    def response_cookies(self, response):
        cookies = SimpleCookie()
        for header in response.headers.getlist("Set-Cookie"):
            cookies.load(header)
        return cookies

    def assert_confirmation(self, response, vote):
        label = {"a": "猫派", "b": "狗派"}[vote]
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'你已投给{label}', response.get_data(as_text=True))
        self.assertIn(f'data-vote="{vote}"', response.get_data(as_text=True))

    def test_invalid_votes_return_json_without_redis_writes_or_vote_cookie_changes(self):
        # AC-01 through AC-06: each request has its own client and write spy history.
        invalid_forms = [{}, *({"vote": value} for value in (
            "", "   ", "c", "A", " a", "a ", " a ",
        ))]
        for saved_vote in (None, "a", "b"):
            for form in invalid_forms:
                with self.subTest(saved_vote=saved_vote, form=form):
                    client = self.vote_app.app.test_client()
                    if saved_vote is not None:
                        client.set_cookie("vote", saved_vote)
                    self.redis.reset_mock()

                    response = client.post("/", data=form)

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.content_type, "application/json")
                    self.assertEqual(response.get_json(), {"error": "invalid_vote"})
                    self.redis.rpush.assert_not_called()
                    self.assertEqual(self.redis.method_calls, [])
                    self.assertNotIn("vote", self.response_cookies(response))
                    cookie = client.get_cookie("vote")
                    self.assertEqual(cookie.value if cookie else None, saved_vote)

    def test_valid_votes_enqueue_exact_payload_and_set_matching_cookies(self):
        # AC-07 through AC-11: both choices with generated and existing identities.
        for vote in ("a", "b"):
            for existing_id in (None, "existing-voter-123"):
                with self.subTest(vote=vote, existing_id=existing_id):
                    client = self.vote_app.app.test_client()
                    if existing_id is not None:
                        client.set_cookie("voter_id", existing_id)
                    self.redis.reset_mock()

                    response = client.post("/", data={"vote": vote})

                    self.assert_confirmation(response, vote)
                    self.redis.rpush.assert_called_once()
                    queue, raw_payload = self.redis.rpush.call_args.args
                    cookies = self.response_cookies(response)
                    voter_id = cookies["voter_id"].value
                    self.assertTrue(voter_id)
                    if existing_id is not None:
                        self.assertEqual(voter_id, existing_id)
                    self.assertEqual(queue, "votes")
                    self.assertEqual(json.loads(raw_payload), {
                        "voter_id": voter_id, "vote": vote,
                    })
                    self.assertEqual(cookies["vote"].value, vote)
                    self.assertEqual(client.get_cookie("vote").value, vote)
                    self.assertEqual(client.get_cookie("voter_id").value, voter_id)

    def test_switching_in_both_directions_reuses_identity_and_survives_refresh(self):
        # AC-12 and AC-13: the same client saves both responses' cookies.
        for first, second in (("a", "b"), ("b", "a")):
            with self.subTest(first=first, second=second):
                client = self.vote_app.app.test_client()
                self.redis.reset_mock()

                initial = client.post("/", data={"vote": first})
                voter_id = client.get_cookie("voter_id").value
                switched = client.post("/", data={"vote": second})

                self.assert_confirmation(initial, first)
                self.assert_confirmation(switched, second)
                self.assertEqual(self.redis.rpush.call_count, 2)
                for call, vote in zip(self.redis.rpush.call_args_list, (first, second)):
                    queue, raw_payload = call.args
                    self.assertEqual(queue, "votes")
                    self.assertEqual(json.loads(raw_payload), {
                        "voter_id": voter_id, "vote": vote,
                    })
                self.assertEqual(self.response_cookies(switched)["vote"].value, second)
                self.assertEqual(client.get_cookie("vote").value, second)
                self.assertEqual(client.get_cookie("voter_id").value, voter_id)

                refreshed = client.get("/")

                self.assert_confirmation(refreshed, second)
                self.assertEqual(self.redis.rpush.call_count, 2)

    def test_get_keeps_confirmation_for_each_valid_vote_cookie_without_writes(self):
        # AC-14: GET must read the saved choice, without enqueuing another vote.
        for vote in ("a", "b"):
            with self.subTest(vote=vote):
                client = self.vote_app.app.test_client()
                client.set_cookie("vote", vote)
                self.redis.reset_mock()

                response = client.get("/")

                self.assert_confirmation(response, vote)
                self.assertEqual(client.get_cookie("vote").value, vote)
                self.redis.rpush.assert_not_called()
                self.assertEqual(self.redis.method_calls, [])


if __name__ == "__main__":
    unittest.main()
