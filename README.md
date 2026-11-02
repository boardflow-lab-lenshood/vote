# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "猫派", "b": "狗派"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`.

`GET /api/arena/three-20261102/options-metadata` returns the active option labels in a stable `a`, `b` order. The existing `/api/arena/20261102/options-metadata` endpoint remains available with the same response:

```json
{"service": "vote", "option_count": 2, "options": [{"id": "a", "label": "猫派"}, {"id": "b", "label": "狗派"}]}
```

This read-only endpoint does not access Redis and remains available when Redis is down. Like `/api/options`, it uses the option environment variables read when the service starts.

`POST /api/arena/seven-20261103/votes` accepts a JSON object with three required fields:

- `voter_id`: a string of 1–255 Unicode characters, containing a non-whitespace character and no NUL. The original value is preserved.
- `vote`: the string `a` or `b`.
- `trace_id`: a string fully matching `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}` (ASCII only).

The endpoint appends exactly `{voter_id, vote, trace_id}` to the existing Redis `votes` list and returns HTTP 202 JSON with `accepted: true` and the three original values. Invalid JSON, non-object bodies, missing fields and invalid values return HTTP 400 JSON without accessing the queue. Redis errors return HTTP 503 JSON with `error: queue_unavailable`. Extra fields are ignored. Existing form votes keep their two-field message format.

This is card A `054b8ac1afd8488d8acc87777ee51679` ([Issue 51](https://github.com/boardflow-lab-lenshood/delivery/issues/51)). Worker card B `5c9d713506a0481c9987c941f5725862` ([Issue 52](https://github.com/boardflow-lab-lenshood/delivery/issues/52)) consumes the three-field contract. Result card C `c25bff7ada4f467395a7981132dee8f4` ([Issue 53](https://github.com/boardflow-lab-lenshood/delivery/issues/53)) must verify the full chain using the exact tested A/B commits published in their external Issues/PRs. A's standalone checks verify HTTP and the real queue; they do not claim worker/result integration.

To build the actual service and run all existing unit tests plus real HTTP/Redis checks, run from this repository with Docker available:

```sh
python3 scripts/check_arena_seven_votes.py --evidence-dir /absolute/path/to/owned-evidence
```

For an offline machine with the baseline vote image already cached, add `--runtime-base boardflow-real-uat/vote:de00436924ec030b08cba2724efb3a21b590dfd5`. This reuses its installed dependencies and copies the current repository into a new image; the evidence records the base image ID and generated Dockerfile. It does not validate a fresh dependency download.

The script creates uniquely named containers and a network labelled with card A's ID, publishes no host ports, stops only its own Redis for the outage check, and removes its containers, network and test image. `commands.log` records command output, HTTP responses and actual `LRANGE votes` values; `result.json` records the tested HEAD, dirty state, commands and result. Run from a clean committed tree for upstream handoff, and publish the evidence together with that exact SHA in the PR and Issue 51. The baseline is `de00436924ec030b08cba2724efb3a21b590dfd5` on integration target `codex/arena-seven-20261103-latest`.

Run the automated unit tests with the service dependencies installed:

```sh
python -m unittest discover -s tests -v
```

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
