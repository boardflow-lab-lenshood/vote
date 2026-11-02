"""Real Docker checks, opt in with VOTE_DOCKER_HEALTHCHECK_TEST=1.

Run: python -m unittest discover -s tests -p test_docker_healthcheck.py -v
Set VOTE_HEALTHCHECK_EVIDENCE_DIR to preserve command output and health snapshots.
VOTE_DOCKER_BUILD_NETWORK optionally selects the build network (default: default).
Only randomly named resources created by this test are stopped or removed.
"""

import json
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid


@unittest.skipUnless(
    os.getenv("VOTE_DOCKER_HEALTHCHECK_TEST") == "1",
    "requires explicit opt-in to build and run owned Docker fixtures",
)
class DockerHealthcheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.owner = f"vote-healthcheck-{uuid.uuid4().hex}"
        cls.image = f"{cls.owner}:test"
        cls.network = f"{cls.owner}-net"
        cls.redis = f"{cls.owner}-redis"
        cls.vote = f"{cls.owner}-vote"
        cls.containers = []
        cls.network_created = False
        cls.image_created = False
        cls.evidence = Path(os.getenv(
            "VOTE_HEALTHCHECK_EVIDENCE_DIR",
            str(Path.cwd() / ".healthcheck-evidence" / cls.owner),
        )).resolve()
        cls.evidence.mkdir(parents=True, exist_ok=True)
        cls.addClassCleanup(cls.cleanup)
        label = f"boardflow.healthcheck.owner={cls.owner}"
        cls.docker(
            "build", "--force-rm", "--network", os.getenv("VOTE_DOCKER_BUILD_NETWORK", "default"),
            "--label", label, "--tag", cls.image,
            str(Path(__file__).resolve().parents[1]), timeout=300,
        )
        cls.image_created = True
        cls.docker("image", "inspect", cls.image)
        cls.docker("network", "create", "--label", label, cls.network)
        cls.network_created = True
        cls.docker(
            "run", "-d", "--name", cls.redis, "--label", label,
            "--network", cls.network, "--network-alias", "redis", "redis:7-alpine",
            timeout=120,
        )
        cls.containers.append(cls.redis)
        cls.docker(
            "run", "-d", "--name", cls.vote, "--label", label,
            "--network", cls.network, cls.image,
        )
        cls.containers.append(cls.vote)
        cls.wait_health("healthy", "initial")
        cls.docker("inspect", cls.redis, cls.vote)
        image = json.loads(cls.docker("image", "inspect", cls.image).stdout)[0]
        cls.probe = image["Config"]["Healthcheck"]["Test"]
        if cls.probe[0] != "CMD":
            raise AssertionError(f"expected exec-form healthcheck: {cls.probe}")

    @classmethod
    def docker(
        cls, *args: str, timeout: int = 30, check: bool = True,
    ) -> subprocess.CompletedProcess:
        command = ["docker", *args]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as error:
            with (cls.evidence / "commands.jsonl").open("a") as stream:
                stream.write(json.dumps({
                    "command": command, "timeout": timeout,
                    "error": str(error),
                    "stdout": (error.stdout or b"").decode(errors="replace"),
                    "stderr": (error.stderr or b"").decode(errors="replace"),
                }) + "\n")
            raise
        with (cls.evidence / "commands.jsonl").open("a") as stream:
            stream.write(json.dumps({
                "command": command, "returncode": result.returncode,
                "stdout": result.stdout, "stderr": result.stderr,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }) + "\n")
        if check:
            result.check_returncode()
        return result

    @classmethod
    def wait_health(cls, expected: str, phase: str) -> dict:
        deadline = time.monotonic() + 100
        while time.monotonic() < deadline:
            state = json.loads(cls.docker(
                "inspect", "--format", "{{json .State.Health}}", cls.vote,
            ).stdout)
            if state["Status"] == expected:
                (cls.evidence / f"health-{phase}.json").write_text(
                    json.dumps(state, indent=2) + "\n",
                )
                return state
            time.sleep(1)
        raise AssertionError(f"did not reach {expected}: {state}")

    @classmethod
    def cleanup(cls) -> None:
        try:
            if cls.vote in cls.containers:
                cls.docker("logs", cls.vote, check=False)
        finally:
            try:
                for container in reversed(cls.containers):
                    cls.docker("rm", "-f", container)
            finally:
                try:
                    if cls.network_created:
                        cls.docker("network", "rm", cls.network)
                finally:
                    if cls.image_created:
                        cls.docker("image", "rm", cls.image)

    def request(self, path: str, data: str | None = None) -> dict:
        script = """
import json, sys, urllib.request
from urllib.error import HTTPError
payload = None if sys.argv[2] == '' else sys.argv[2].encode()
request = urllib.request.Request('http://127.0.0.1:80' + sys.argv[1], data=payload)
try:
    response = urllib.request.urlopen(request, timeout=7)
except HTTPError as error:
    response = error
with response:
    sys.stdout.write(json.dumps({'status': response.status, 'body': response.read().decode()}))
"""
        return json.loads(self.docker(
            "exec", self.vote, "python", "-c", script, path, data or "",
        ).stdout)

    def test_recovers_health_when_owned_redis_stops_and_restarts(self) -> None:
        self.assertEqual(self.docker(
            "exec", self.vote, *self.probe[1:], check=False,
        ).returncode, 0)

        self.docker("stop", "--time", "2", self.redis)
        try:
            unhealthy = self.wait_health("unhealthy", "redis-stopped")
            failed_probe = self.docker(
                "exec", self.vote, *self.probe[1:], check=False,
            )
            response = self.request("/healthz")
            self.assertNotEqual(failed_probe.returncode, 0)
            self.assertTrue(failed_probe.stderr)
            self.assertEqual(response["status"], 503)
            self.assertGreaterEqual(unhealthy["FailingStreak"], 3)
            self.assertTrue(all(log["ExitCode"] != 0 for log in unhealthy["Log"][-3:]))
        finally:
            self.docker("start", self.redis)
            recovered = self.wait_health("healthy", "redis-restored")

        self.assertEqual(recovered["FailingStreak"], 0)
        self.assertEqual(self.docker(
            "exec", self.vote, *self.probe[1:], check=False,
        ).returncode, 0)
        self.assertEqual(json.loads(self.request("/healthz")["body"]), {
            "status": "ok", "service": "vote",
        })

    def test_existing_suite_passes_when_run_in_built_image(self) -> None:
        # The existing unit suite expects no reachable Redis; keep it isolated
        # from the live readiness fixture without changing any existing tests.
        unit_container = f"{self.owner}-unit"
        self.docker(
            "create", "--name", unit_container, "--network", "none",
            "--label", f"boardflow.healthcheck.owner={self.owner}", self.image,
            "python", "-m", "unittest", "discover", "-s", "tests", "-v",
        )
        self.containers.append(unit_container)

        self.docker("start", "--attach", unit_container, timeout=60)
        exit_code = self.docker(
            "inspect", "--format", "{{.State.ExitCode}}", unit_container,
        )

        self.assertEqual(exit_code.stdout.strip(), "0")

    def test_returns_homepage_when_image_runs(self) -> None:
        response = self.request("/")

        self.assertEqual(response["status"], 200)
        self.assertIn("猫派", response["body"])
        self.assertIn("狗派", response["body"])

    def test_returns_options_when_image_runs(self) -> None:
        response = self.request("/api/options")

        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(response["body"]), {"a": "猫派", "b": "狗派"})

    def test_returns_metadata_when_image_runs(self) -> None:
        for path in (
            "/api/arena/three-20261102/options-metadata",
            "/api/arena/20261102/options-metadata",
            "/api/uat/poll-info",
        ):
            with self.subTest(path=path):
                response = self.request(path)

                self.assertEqual(response["status"], 200)
                self.assertEqual(json.loads(response["body"])["option_count"], 2)

    def test_enqueues_vote_when_form_is_posted_to_image(self) -> None:
        self.docker("exec", self.redis, "redis-cli", "DEL", "votes")

        response = self.request("/", "vote=a")
        queued = self.docker("exec", self.redis, "redis-cli", "LPOP", "votes")

        self.assertEqual(response["status"], 200)
        self.assertEqual(json.loads(queued.stdout)["vote"], "a")
        self.assertIn("你已投给猫派", response["body"])


if __name__ == "__main__":
    unittest.main()
