# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns HTTP 200 with `Content-Type: application/json` and
the current option labels:

```json
{"a": "猫派", "b": "狗派"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`.
The application reads them when the Python module loads; restart the process
after changing them. This endpoint sets `Cache-Control: no-store` so clients and
proxies must not store its response. Other routes keep their existing cache
behavior.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.

## Local tests

Use Python 3 with the `venv` module and pip. From this repository's root, create
an isolated environment and install the same dependencies used by the app:

```sh
python3 -m venv .venv
PIP_CACHE_DIR=.cache/pip .venv/bin/python -m pip install -r requirements.txt
```

Run the options API tests independently with the standard library's `unittest`
runner (no additional test framework is required):

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_api_options.py' -v
```

Run that same command again to repeat the checks. These tests use Flask's test
client, isolate `OPTION_A`/`OPTION_B`, and check both the defaults and explicit
`Tea`/`Coffee` configuration. They assert the cache header, status, JSON content
type, exact `a`/`b` values, module-load configuration behavior, and repeated
read-only access. Redis is mocked where other routes need it; no Redis server,
worker, database, live HTTP server, or data cleanup is needed. The options checks
do not submit votes; the existing homepage/voting regression tests use mocks.
The tests also check that the new cache policy does not apply to the home page,
health endpoint, poll-info endpoint, or a static asset.

Run the complete existing suite with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

These are local checks. To verify a deployed release, request `/api/options` and
open the home page on that release, compare `a`/`b` against its effective server
configuration, and record its deployment and commit. The local defaults are not
an expected value for a differently configured deployment.
