"""Real HTTP and Redis checks; run only in an owned, disposable network."""
import http.cookiejar
import json
import logging
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from redis import Redis

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_api_arena_seven_votes import INVALID_FIELDS, VALID_VOTE, VOTES_PATH


logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)


def http_request(path: str, payload: bytes | None = None, content_type: str = "application/json", opener=None):
    request = urllib.request.Request(
        "http://127.0.0.1:80" + path,
        data=payload,
        headers={"Content-Type": content_type},
    )
    try:
        response = (opener or urllib.request.build_opener()).open(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read().decode("utf-8")
        status = response.status
        mimetype = response.headers.get_content_type()
    LOGGER.info(json.dumps({"event": "http", "path": path, "request": payload.decode() if payload is not None else None, "status": status, "content_type": mimetype, "body": body}, ensure_ascii=True))
    return status, mimetype, body


class HealthyRedisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.redis = Redis(host="redis", socket_timeout=5, decode_responses=True)
        self.addCleanup(self.redis.close)
        self.assertEqual(self.redis.llen("votes"), 0)

    def queue(self) -> list[dict]:
        messages = [json.loads(value) for value in self.redis.lrange("votes", 0, -1)]
        LOGGER.info(json.dumps({"event": "redis_lrange", "key": "votes", "messages": messages}, ensure_ascii=True))
        return messages

    def test_returns_202_with_exact_queue_message_when_input_is_valid(self) -> None:
        for voter_id, vote, trace_id in [("x", "a", "0"), ("😀" * 255, "b", "A" + "x" * 63), (" \t投票者😀 \n", "a", "Z0._:-")]:
            with self.subTest(vote=vote, trace_length=len(trace_id), voter_length=len(voter_id)):
                payload = {"voter_id": voter_id, "vote": vote, "trace_id": trace_id}

                status, mimetype, body = http_request(VOTES_PATH, json.dumps(payload).encode())

                self.assertEqual((status, mimetype), (202, "application/json"))
                self.assertEqual(json.loads(body), {"accepted": True, **payload})
                self.assertEqual(self.queue(), [payload])
                self.redis.lpop("votes")

    def test_returns_400_with_unchanged_queue_when_input_is_invalid(self) -> None:
        sentinel = {"voter_id": "owned-existing", "vote": "b"}
        self.redis.rpush("votes", json.dumps(sentinel))
        self.addCleanup(self.redis.delete, "votes")
        bodies = [(json.dumps({**VALID_VOTE, field: value}), "application/json") for field, values in INVALID_FIELDS.items() for value in values]
        bodies += [(json.dumps({key: value for key, value in VALID_VOTE.items() if key != missing}), "application/json") for missing in VALID_VOTE]
        bodies += [(json.dumps(value), "application/json") for value in [None, [], "string", 1, 1.5, True]]
        bodies += [("{", "application/json"), ("", "application/json"), ("invalid", "text/plain")]
        for body, content_type in bodies:
            with self.subTest(body=body):
                status, mimetype, response = http_request(VOTES_PATH, body.encode(), content_type)

                self.assertEqual((status, mimetype), (400, "application/json"))
                self.assertIn("error", json.loads(response))
                self.assertEqual(self.queue(), [sentinel])

    def test_preserves_cookie_vote_when_legacy_form_is_submitted(self) -> None:
        cookies = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        status, _, body = http_request("/", opener=opener)
        self.assertEqual(status, 200)
        self.assertIn("猫派", body)
        voter_id = next(cookie.value for cookie in cookies if cookie.name == "voter_id")
        self.addCleanup(self.redis.delete, "votes")

        status, _, _ = http_request("/", urllib.parse.urlencode({"vote": "b"}).encode(), "application/x-www-form-urlencoded", opener)

        self.assertEqual(status, 200)
        self.assertEqual(self.queue(), [{"voter_id": voter_id, "vote": "b"}])
        self.assertEqual(next(cookie.value for cookie in cookies if cookie.name == "vote"), "b")

    def test_preserves_metadata_when_existing_routes_are_requested(self) -> None:
        metadata = {"service": "vote", "option_count": 2, "options": [{"id": "a", "label": "猫派"}, {"id": "b", "label": "狗派"}]}
        expected = {
            "/api/options": {"a": "猫派", "b": "狗派"},
            "/api/arena/20261102/options-metadata": metadata,
            "/api/arena/three-20261102/options-metadata": metadata,
            "/api/uat/poll-info": {"title": "猫派 vs 狗派!", "options": metadata["options"], "option_count": 2},
            "/healthz": {"status": "ok", "service": "vote"},
            "/api/regression/echo?x=7": {"feature": "echo", "value": 7},
        }
        for path, value in expected.items():
            with self.subTest(path=path):
                status, mimetype, body = http_request(path)

                self.assertEqual((status, mimetype), (200, "application/json"))
                self.assertEqual(json.loads(body), value)


class UnavailableRedisTest(unittest.TestCase):
    def test_returns_503_without_acceptance_when_owned_redis_is_stopped(self) -> None:
        status, mimetype, body = http_request(VOTES_PATH, json.dumps(VALID_VOTE).encode())

        self.assertEqual((status, mimetype), (503, "application/json"))
        self.assertEqual(json.loads(body), {"error": "queue_unavailable"})

    def test_returns_400_when_invalid_input_arrives_during_outage(self) -> None:
        status, mimetype, body = http_request(VOTES_PATH, b'{}')

        self.assertEqual((status, mimetype), (400, "application/json"))
        self.assertIn("error", json.loads(body))

    def test_preserves_readiness_status_when_owned_redis_is_stopped(self) -> None:
        status, mimetype, body = http_request("/healthz")

        self.assertEqual((status, mimetype), (503, "application/json"))
        self.assertEqual(json.loads(body), {"status": "unavailable", "service": "vote"})

    def test_preserves_options_when_owned_redis_is_stopped(self) -> None:
        status, mimetype, body = http_request("/api/options")

        self.assertEqual((status, mimetype), (200, "application/json"))
        self.assertEqual(json.loads(body), {"a": "猫派", "b": "狗派"})


if __name__ == "__main__":
    for attempt in range(40):
        try:
            http_request("/api/options")
            break
        except urllib.error.URLError:
            if attempt == 39:
                raise
            time.sleep(0.25)
    unittest.main()
