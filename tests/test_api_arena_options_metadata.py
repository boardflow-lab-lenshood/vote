import importlib
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from redis.exceptions import ConnectionError


class ApiArenaOptionsMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        import app as vote_app

        self.environment = patch.dict(os.environ)
        self.environment.start()
        os.environ.pop("OPTION_A", None)
        os.environ.pop("OPTION_B", None)
        self.vote_app = importlib.reload(vote_app)
        self.client = self.vote_app.app.test_client()

    def tearDown(self) -> None:
        self.environment.stop()
        importlib.reload(self.vote_app)

    def test_returns_default_metadata_when_option_environment_is_unset(self) -> None:
        response = self.client.get("/api/arena/20261102/options-metadata")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [
                {"id": "a", "label": "猫派"},
                {"id": "b", "label": "狗派"},
            ],
        })

    def test_returns_configured_metadata_when_option_environment_is_set(self) -> None:
        with patch.dict(os.environ, {"OPTION_A": "茶 ☕", "OPTION_B": "Coffee"}):
            importlib.reload(self.vote_app)
            client = self.vote_app.app.test_client()

            response = client.get("/api/arena/20261102/options-metadata")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [
                {"id": "a", "label": "茶 ☕"},
                {"id": "b", "label": "Coffee"},
            ],
        })

    def test_preserves_empty_label_when_configured(self) -> None:
        with patch.dict(os.environ, {"OPTION_A": "", "OPTION_B": "Coffee"}):
            importlib.reload(self.vote_app)
            client = self.vote_app.app.test_client()

            response = client.get("/api/arena/20261102/options-metadata")

        self.assertEqual(response.get_json()["options"], [
            {"id": "a", "label": ""},
            {"id": "b", "label": "Coffee"},
        ])

    def test_returns_metadata_without_redis_access_when_redis_is_unavailable(self) -> None:
        with (
            patch.object(self.vote_app, "get_redis", side_effect=ConnectionError("Redis unavailable")) as get_redis,
            patch.object(self.vote_app, "Redis", side_effect=ConnectionError("Redis unavailable")) as redis_constructor,
        ):
            response = self.client.get("/api/arena/20261102/options-metadata")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [
                {"id": "a", "label": "猫派"},
                {"id": "b", "label": "狗派"},
            ],
        })
        get_redis.assert_not_called()
        redis_constructor.assert_not_called()

    def test_does_not_set_cookies_when_metadata_is_requested(self) -> None:
        response = self.client.get("/api/arena/20261102/options-metadata")

        self.assertNotIn("Set-Cookie", response.headers)

    def test_preserves_options_response_when_metadata_route_is_added(self) -> None:
        response = self.client.get("/api/options")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"a": "猫派", "b": "狗派"})

    def test_preserves_homepage_labels_when_metadata_route_is_added(self) -> None:
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("猫派".encode(), response.data)
        self.assertIn("狗派".encode(), response.data)

    def test_returns_healthy_status_when_redis_ping_succeeds(self) -> None:
        redis = MagicMock()
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "service": "vote"})
        redis.ping.assert_called_once_with()

    def test_returns_unavailable_status_when_redis_ping_fails(self) -> None:
        redis = MagicMock()
        redis.ping.side_effect = ConnectionError("Redis unavailable")
        with patch.object(self.vote_app, "get_redis", return_value=redis):
            response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "unavailable", "service": "vote"})

    def test_enqueues_vote_with_voter_cookie_when_choice_is_submitted(self) -> None:
        for choice in ("a", "b"):
            with self.subTest(choice=choice):
                redis = MagicMock()
                self.client.set_cookie("voter_id", "arena-metadata-voter")
                with patch.object(self.vote_app, "get_redis", return_value=redis):
                    response = self.client.post("/", data={"vote": choice})

                self.assertEqual(response.status_code, 200)
                redis.rpush.assert_called_once()
                queue, payload = redis.rpush.call_args.args
                self.assertEqual(queue, "votes")
                self.assertEqual(json.loads(payload), {
                    "voter_id": "arena-metadata-voter",
                    "vote": choice,
                })
                self.assertEqual(self.client.get_cookie("vote").value, choice)


if __name__ == "__main__":
    unittest.main()
