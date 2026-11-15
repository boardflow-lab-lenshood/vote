import json
import unittest
from unittest.mock import patch

import app as vote_app


INVALID_FORMS = (
    {},
    {"vote": ""},
    {"vote": " "},
    {"vote": "\t"},
    {"vote": "c"},
    {"vote": "A"},
    {"vote": " a"},
    {"vote": "a "},
    {"vote": " a "},
)


class VoteValidationTest(unittest.TestCase):
    def setUp(self):
        self.write_spy = self.enterContext(
            patch.object(vote_app.Redis, "rpush", autospec=True, return_value=1)
        )
        self.enterContext(patch.object(
            vote_app.Redis, "execute_command",
            side_effect=AssertionError("Unexpected Redis command in isolated test"),
        ))

    def assert_confirmation(self, response, choice):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/html")
        html = response.get_data(as_text=True)
        label = vote_app.option_a if choice == "a" else vote_app.option_b
        self.assertIn('id="vote-confirmation" data-vote="' + choice + '"', html)
        self.assertIn("你已投给" + label, html)
        other = "b" if choice == "a" else "a"
        self.assertNotIn('data-vote="' + other + '"', html)

    def assert_message(self, call, choice, voter_id):
        redis, queue, raw_message = call.args
        self.assertIsInstance(redis, vote_app.Redis)
        self.assertEqual(queue, "votes")
        self.assertIsInstance(raw_message, str)
        self.assertEqual(json.loads(raw_message), {"voter_id": voter_id, "vote": choice})
        self.assertEqual(call.kwargs, {})

    def test_invalid_matrix_returns_exact_error_without_writes_or_cookie_changes(self):
        for existing_vote in (None, "a", "b"):
            for form in INVALID_FORMS:
                with self.subTest(existing_vote=existing_vote, form=form):
                    client = vote_app.app.test_client()
                    if existing_vote is not None:
                        client.set_cookie("vote", existing_vote)
                    self.write_spy.reset_mock()
                    response = client.post("/", data=form)

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.content_type, "application/json")
                    self.assertEqual(response.get_json(), {"error": "invalid_vote"})
                    self.write_spy.assert_not_called()
                    vote_headers = [
                        value for value in response.headers.getlist("Set-Cookie")
                        if value.split("=", 1)[0] == "vote"
                    ]
                    self.assertEqual(vote_headers, [])
                    cookie = client.get_cookie("vote")
                    self.assertEqual(cookie.value if cookie else None, existing_vote)
                    refreshed = client.get("/")
                    self.assertEqual(refreshed.status_code, 200)
                    if existing_vote is not None:
                        self.assert_confirmation(refreshed, existing_vote)
                    else:
                        self.assertNotIn('id="vote-confirmation"', refreshed.get_data(as_text=True))
                    self.write_spy.assert_not_called()

    def test_valid_votes_keep_html_queue_identity_and_cookie_contract(self):
        for choice in ("a", "b"):
            for existing_voter in (None, "", "existing-voter"):
                with self.subTest(choice=choice, existing_voter=existing_voter):
                    client = vote_app.app.test_client()
                    if existing_voter is not None:
                        client.set_cookie("voter_id", existing_voter)
                    self.write_spy.reset_mock()
                    random_bits = 0x123456789ABCDEF0
                    with patch.object(vote_app.random, "getrandbits", return_value=random_bits) as generate:
                        response = client.post("/", data={"vote": choice})
                    self.assert_confirmation(response, choice)
                    self.assertEqual(client.get_cookie("vote").value, choice)
                    voter_id = client.get_cookie("voter_id").value
                    if existing_voter:
                        self.assertEqual(voter_id, existing_voter)
                        generate.assert_not_called()
                    else:
                        self.assertEqual(voter_id, hex(random_bits)[2:-1])
                        generate.assert_called_once_with(64)
                    self.write_spy.assert_called_once()
                    self.assert_message(self.write_spy.call_args, choice, voter_id)
                    self.assert_confirmation(client.get("/"), choice)
                    self.write_spy.assert_called_once()

    def test_switching_both_directions_keeps_identity_and_appends_current_choice(self):
        for choices in (("a", "b"), ("b", "a")):
            with self.subTest(choices=choices):
                client = vote_app.app.test_client()
                self.write_spy.reset_mock()
                voter_id = None
                for index, choice in enumerate(choices, 1):
                    response = client.post("/", data={"vote": choice})
                    self.assert_confirmation(response, choice)
                    self.assertEqual(client.get_cookie("vote").value, choice)
                    if voter_id is None:
                        voter_id = client.get_cookie("voter_id").value
                    self.assertEqual(client.get_cookie("voter_id").value, voter_id)
                    self.assertEqual(self.write_spy.call_count, index)
                    self.assert_message(self.write_spy.call_args_list[index - 1], choice, voter_id)
                    self.assert_confirmation(client.get("/"), choice)
                    self.assertEqual(self.write_spy.call_count, index)


if __name__ == "__main__":
    unittest.main()
