import importlib
import json
import unittest
from http.cookies import SimpleCookie
from unittest.mock import MagicMock, patch


INVALID_VOTES = (
    ("missing", {}),
    ("empty", {"vote": ""}),
    ("whitespace", {"vote": " \t\n"}),
    ("unknown", {"vote": "c"}),
    ("uppercase", {"vote": "A"}),
    ("leading_space", {"vote": " a"}),
    ("trailing_space", {"vote": "a "}),
    ("surrounding_spaces", {"vote": " a "}),
)


class VoteValidationTest(unittest.TestCase):
    def setUp(self):
        import app as vote_app

        importlib.reload(vote_app)
        vote_app.app.config["TESTING"] = True
        self.vote_app = vote_app
        self.redis = MagicMock(spec=vote_app.Redis)
        redis_patch = patch.object(vote_app, "Redis", return_value=self.redis)
        self.redis_factory = redis_patch.start()
        self.addCleanup(redis_patch.stop)

    def response_cookies(self, response):
        cookies = SimpleCookie()
        for header in response.headers.getlist("Set-Cookie"):
            cookies.load(header)
        return cookies

    def assert_confirmation(self, response, vote):
        self.assertEqual(response.status_code, 200)
        label = self.vote_app.option_a if vote == "a" else self.vote_app.option_b
        self.assertIn(f"你已投给{label}", response.get_data(as_text=True))
        self.assertIn(f'data-vote="{vote}"', response.get_data(as_text=True))
        other_vote = "b" if vote == "a" else "a"
        self.assertNotIn(f'data-vote="{other_vote}"', response.get_data(as_text=True))

    def test_invalid_votes_have_zero_redis_calls_and_preserve_cookies(self):
        for previous_vote in (None, "a", "b"):
            for name, data in INVALID_VOTES:
                with self.subTest(previous_vote=previous_vote, invalid_vote=name):
                    client = self.vote_app.app.test_client()
                    client.set_cookie("voter_id", "existing-voter")
                    if previous_vote is not None:
                        client.set_cookie("vote", previous_vote)
                    self.redis.reset_mock()
                    self.redis_factory.reset_mock()

                    response = client.post("/", data=data)

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.content_type, "application/json")
                    self.assertEqual(response.get_json(), {"error": "invalid_vote"})
                    self.assertNotIn("vote", self.response_cookies(response))
                    self.redis.rpush.assert_not_called()
                    self.assertEqual(self.redis.mock_calls, [])
                    self.redis_factory.assert_not_called()

                    refreshed = client.get("/")
                    self.assertEqual(refreshed.status_code, 200)
                    if previous_vote is not None:
                        self.assert_confirmation(refreshed, previous_vote)
                    else:
                        self.assertNotIn('id="vote-confirmation"', refreshed.get_data(as_text=True))
                    self.assertEqual(self.redis.mock_calls, [])
                    self.redis_factory.assert_not_called()

    def test_legal_votes_enqueue_once_and_keep_identity_and_confirmation(self):
        for vote in ("a", "b"):
            for existing_voter in (None, "", "existing-voter"):
                with self.subTest(vote=vote, voter_id=existing_voter):
                    client = self.vote_app.app.test_client()
                    if existing_voter is not None:
                        client.set_cookie("voter_id", existing_voter)
                    self.redis.reset_mock()

                    response = client.post("/", data={"vote": vote})

                    self.assert_confirmation(response, vote)
                    self.redis.rpush.assert_called_once()
                    queue, raw_payload = self.redis.rpush.call_args.args
                    self.assertEqual(queue, "votes")
                    payload = json.loads(raw_payload)
                    cookies = self.response_cookies(response)
                    voter_id = cookies["voter_id"].value
                    self.assertTrue(voter_id)
                    if existing_voter:
                        self.assertEqual(voter_id, existing_voter)
                    self.assertEqual(payload, {"voter_id": voter_id, "vote": vote})
                    self.assertEqual(cookies["vote"].value, vote)

                    refreshed = client.get("/")
                    self.assert_confirmation(refreshed, vote)
                    self.redis.rpush.assert_called_once()
                    self.assertEqual(len(self.redis.mock_calls), 1)

    def test_same_voter_can_switch_votes_in_both_directions(self):
        for first, second in (("a", "b"), ("b", "a")):
            with self.subTest(first=first, second=second):
                client = self.vote_app.app.test_client()
                self.redis.reset_mock()

                first_response = client.post("/", data={"vote": first})
                voter_id = self.response_cookies(first_response)["voter_id"].value
                second_response = client.post("/", data={"vote": second})

                self.assert_confirmation(first_response, first)
                self.assert_confirmation(second_response, second)
                self.assertEqual(self.redis.rpush.call_count, 2)
                for recorded, expected_vote in zip(self.redis.rpush.call_args_list, (first, second)):
                    queue, raw_payload = recorded.args
                    self.assertEqual(queue, "votes")
                    self.assertEqual(json.loads(raw_payload), {"voter_id": voter_id, "vote": expected_vote})
                cookies = self.response_cookies(second_response)
                self.assertEqual(cookies["voter_id"].value, voter_id)
                self.assertEqual(cookies["vote"].value, second)
                self.assert_confirmation(client.get("/"), second)
                self.assertEqual(self.redis.rpush.call_count, 2)
                self.assertEqual(len(self.redis.mock_calls), 2)


if __name__ == "__main__":
    unittest.main()
