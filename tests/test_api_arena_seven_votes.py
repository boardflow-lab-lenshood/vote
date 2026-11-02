import json
import unittest
from unittest.mock import Mock, patch

from redis.exceptions import ConnectionError, TimeoutError

import app as vote_app


VOTES_PATH = "/api/arena/seven-20261103/votes"
VALID_VOTE = {"voter_id": "投票者😀", "vote": "a", "trace_id": "A1._:-trace"}
INVALID_FIELDS = {
    "voter_id": [None, True, 1, 1.5, [], {}, "", " ", "\t\n", " ", "x\0y", "😀" * 256],
    "vote": [None, True, 1, 1.5, [], {}, "", "A", "c", " a", "b\n"],
    "trace_id": [None, True, 1, 1.5, [], {}, "", "x" * 65, "é", "Ａ", "1é", "_x", ".x", ":x", "-x", "a b", "a/b", "a\0b", "a\nb", "a\n", "a\r\n"],
}


class ApiArenaSevenVotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = vote_app.app.test_client()
        self.redis = Mock()
        patcher = patch.object(vote_app, "get_redis", return_value=self.redis)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_enqueues_original_values_when_fields_are_valid(self) -> None:
        for voter_id, vote, trace_id in [
            ("x", "a", "0"),
            ("😀" * 255, "b", "A" + "x" * 63),
            (" \t投票者😀 \n", "a", "A1._:-trace"),
        ]:
            with self.subTest(voter_id=voter_id, vote=vote, trace_id=trace_id):
                payload = {"voter_id": voter_id, "vote": vote, "trace_id": trace_id}
                self.redis.reset_mock()

                response = self.client.post(VOTES_PATH, json=payload)

                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.get_json(), {"accepted": True, **payload})
                self.redis.rpush.assert_called_once_with("votes", json.dumps(payload))

    def test_returns_400_without_queue_access_when_field_is_invalid(self) -> None:
        for field, values in INVALID_FIELDS.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = {**VALID_VOTE, field: value}

                    response = self.client.post(VOTES_PATH, json=payload)

                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(response.mimetype, "application/json")
                    self.assertEqual(response.get_json(), {"error": "invalid_" + field})
                    vote_app.get_redis.assert_not_called()

    def test_returns_400_without_queue_access_when_required_field_is_missing(self) -> None:
        for field in VALID_VOTE:
            with self.subTest(field=field):
                payload = {key: value for key, value in VALID_VOTE.items() if key != field}

                response = self.client.post(VOTES_PATH, json=payload)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.mimetype, "application/json")
                vote_app.get_redis.assert_not_called()

    def test_returns_400_without_queue_access_when_json_is_not_an_object(self) -> None:
        for value in [None, [], "string", 1, 1.5, True]:
            with self.subTest(value=value):
                response = self.client.post(VOTES_PATH, data=json.dumps(value), content_type="application/json")

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": "invalid_json_object"})
                vote_app.get_redis.assert_not_called()

    def test_returns_400_without_queue_access_when_body_is_not_valid_json(self) -> None:
        for body, content_type in [("{", "application/json"), ("", "application/json"), ("not json", "text/plain")]:
            with self.subTest(body=body, content_type=content_type):
                response = self.client.post(VOTES_PATH, data=body, content_type=content_type)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json(), {"error": "invalid_json_object"})
                vote_app.get_redis.assert_not_called()

    def test_returns_503_without_acceptance_when_redis_write_fails(self) -> None:
        for error in [ConnectionError("unavailable"), TimeoutError("timeout")]:
            with self.subTest(error=type(error).__name__):
                self.redis.rpush.side_effect = error

                response = self.client.post(VOTES_PATH, json=VALID_VOTE)

                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.get_json(), {"error": "queue_unavailable"})

    def test_returns_503_when_redis_client_cannot_be_created(self) -> None:
        vote_app.get_redis.side_effect = ConnectionError("unavailable")

        response = self.client.post(VOTES_PATH, json=VALID_VOTE)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"error": "queue_unavailable"})

    def test_omits_extra_fields_from_message_when_payload_has_other_keys(self) -> None:
        response = self.client.post(VOTES_PATH, json={**VALID_VOTE, "extra": "ignored"})

        self.assertEqual(response.status_code, 202)
        self.redis.rpush.assert_called_once_with("votes", json.dumps(VALID_VOTE))


if __name__ == "__main__":
    unittest.main()
