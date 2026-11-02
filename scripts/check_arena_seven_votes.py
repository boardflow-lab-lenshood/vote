"""Build and validate vote with an owned Redis fixture; no host ports required."""
import argparse
import datetime
import json
import logging
import re
from pathlib import Path
import subprocess
import uuid


LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--runtime-base", help="Optional locally available vote image containing service dependencies for offline validation")
    args = parser.parse_args()
    if args.runtime_base and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]*", args.runtime_base):
        parser.error("invalid runtime base image reference")
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    owner = "arena-seven-a-054b8ac1-" + uuid.uuid4().hex[:12]
    network = owner + "-net"
    redis = owner + "-redis"
    app = owner + "-vote"
    image = owner + ":test"
    created: list[tuple[str, str]] = []
    commands: list[dict] = []
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    result = {"owner": owner, "head_sha": head, "dirty": dirty, "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "status": "FAILED", "commands": commands}

    def run(command: list[str], timeout: int = 120) -> None:
        record = {"command": command}
        commands.append(record)
        LOGGER.info(json.dumps({"event": "command", **record}))
        with (args.evidence_dir / "commands.log").open("a") as log:
            log.write("\n$ " + json.dumps(command) + "\n")
            log.flush()
            completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        record["exit_code"] = completed.returncode
        completed.check_returncode()

    try:
        if args.runtime_base:
            dockerfile = args.evidence_dir / "runtime.Dockerfile"
            dockerfile.write_text(f"FROM {args.runtime_base}\nWORKDIR /usr/local/app\nCOPY . .\nCMD [\"gunicorn\", \"app:app\", \"-b\", \"0.0.0.0:80\", \"--workers\", \"4\", \"--access-logfile\", \"-\"]\n")
            run(["docker", "image", "inspect", "--format", "{{.Id}}", args.runtime_base])
            run(["docker", "build", "-f", str(dockerfile), "-t", image, "."], timeout=180)
        else:
            run(["docker", "build", "--target", "final", "-t", image, "."], timeout=180)
        created.append(("image", image))
        run(["docker", "run", "--rm", "--add-host", "redis:127.0.0.1", image, "python", "-m", "unittest", "discover", "-s", "tests", "-v"])
        run(["docker", "network", "create", "--label", "boardflow.card=054b8ac1afd8488d8acc87777ee51679", network])
        created.append(("network", network))
        run(["docker", "run", "-d", "--name", redis, "--network", network, "--network-alias", "redis", "--label", "boardflow.card=054b8ac1afd8488d8acc87777ee51679", "redis:7-alpine", "redis-server", "--save", "", "--appendonly", "no"])
        created.append(("container", redis))
        run(["docker", "run", "-d", "--name", app, "--network", network, "--label", "boardflow.card=054b8ac1afd8488d8acc87777ee51679", image])
        created.append(("container", app))
        run(["docker", "exec", app, "python", "tests/integration/arena_seven_votes.py", "HealthyRedisTest", "-v"])
        run(["docker", "stop", "-t", "2", redis])
        run(["docker", "exec", app, "python", "tests/integration/arena_seven_votes.py", "UnavailableRedisTest", "-v"])
        # Restart only our own Redis, then prove failed requests were never queued.
        run(["docker", "start", redis])
        run(["docker", "exec", app, "python", "-c", "import json, logging; from redis import Redis; logging.basicConfig(level=logging.INFO, format='%(message)s'); r=Redis(host='redis', socket_timeout=5); messages=r.lrange('votes',0,-1); assert messages == [], messages; logging.info(json.dumps({'event':'redis_after_outage','messages':messages}))"])
        result["status"] = "PASSED"
    finally:
        if ("container", app) in created:
            run(["docker", "logs", app])
        for kind, name in reversed(created):
            command = ["docker", "rm", "-f", name] if kind == "container" else ["docker", kind, "rm", name]
            run(command)
        result["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.evidence_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    LOGGER.info(json.dumps({"event": "validation_complete", "head_sha": head, "status": result["status"], "evidence_dir": str(args.evidence_dir)}))


if __name__ == "__main__":
    main()
