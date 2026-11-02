import importlib
import os
import unittest
from unittest.mock import patch

from redis.exceptions import ConnectionError


METADATA_PATH = "/api/arena/three-20261102/options-metadata"


class ApiArenaThreeOptionsMetadataTest(unittest.TestCase):
    def setUp(self) -> None:
        import app as vote_app

        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop("OPTION_A", None)
        os.environ.pop("OPTION_B", None)
        self.vote_app = importlib.reload(vote_app)
        self.client = self.vote_app.app.test_client()

    def tearDown(self) -> None:
        self.environment.stop()
        importlib.reload(self.vote_app)

    def test_returns_default_metadata_when_option_environment_is_unset(self) -> None:
        response = self.client.get(METADATA_PATH)

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

            response = client.get(METADATA_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [
                {"id": "a", "label": "茶 ☕"},
                {"id": "b", "label": "Coffee"},
            ],
        })

    def test_preserves_empty_label_when_option_environment_is_empty(self) -> None:
        with patch.dict(os.environ, {"OPTION_A": "", "OPTION_B": "Coffee"}):
            importlib.reload(self.vote_app)
            client = self.vote_app.app.test_client()

            response = client.get(METADATA_PATH)

        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [{"id": "a", "label": ""}, {"id": "b", "label": "Coffee"}],
        })

    def test_returns_metadata_without_redis_access_when_redis_is_unavailable(self) -> None:
        with (
            patch.object(self.vote_app, "get_redis", side_effect=ConnectionError("Redis unavailable")) as get_redis,
            patch.object(self.vote_app, "Redis", side_effect=ConnectionError("Redis unavailable")) as constructor,
        ):
            response = self.client.get(METADATA_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            "service": "vote",
            "option_count": 2,
            "options": [{"id": "a", "label": "猫派"}, {"id": "b", "label": "狗派"}],
        })
        get_redis.assert_not_called()
        constructor.assert_not_called()

    def test_preserves_legacy_metadata_when_new_path_is_requested(self) -> None:
        legacy = self.client.get("/api/arena/20261102/options-metadata")

        response = self.client.get(METADATA_PATH)

        self.assertEqual(response.get_json(), legacy.get_json())

    def test_does_not_set_cookies_when_metadata_is_requested(self) -> None:
        response = self.client.get(METADATA_PATH)

        self.assertNotIn("Set-Cookie", response.headers)


if __name__ == "__main__":
    unittest.main()
