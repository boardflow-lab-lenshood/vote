# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns HTTP 200 with `Content-Type: application/json` and
`Cache-Control: no-store`. The JSON contains the current option labels:

```json
{"a": "猫派", "b": "狗派"}
```

Labels come from `OPTION_A` and `OPTION_B` when the application module loads,
defaulting to `猫派` and `狗派`. The cache header is set only on this endpoint's
response.

Run the options API tests independently from the vote repository root (Python 3,
with the dependencies in `requirements.txt`; no running Redis server required):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -p 'test_api_options.py' -v
```

These tests isolate and restore option configuration, cover default and custom
labels, and check the response contract and cache header scope. They use Flask's
test client; actual deployed response headers, configuration and homepage
availability still need to be checked against the delivered commit.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
