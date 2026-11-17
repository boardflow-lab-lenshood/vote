# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns HTTP 200 with `Content-Type: application/json`,
`Cache-Control: no-store`, and the current option labels as JSON:

```json
{"a": "猫派", "b": "狗派"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`.
They are read when the application module loads; restart the service after changing
these environment variables. The cache header applies only to `/api/options`.

## Independent options API test

Prerequisites: Python 3.10+ and the dependencies in `requirements.txt`. From the
repository root, use a Python environment with those dependencies installed:

```sh
python3 -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_api_options_no_store.py' -v
```

The test uses the actual Flask application and its test client, without starting
an HTTP server or requiring Redis. It checks HTTP 200, the JSON media type, the
exact `Cache-Control: no-store` header, and the complete `a`/`b` payload against
default and explicitly configured labels, including Unicode and empty labels.
It isolates and restores option environment variables and the loaded test module,
so ambient `OPTION_A`/`OPTION_B` values do not affect the result. It also checks
that this request neither sets cookies nor calls Redis. Failures produce a nonzero
exit status; the same command can be rerun without voting or historical artifacts.

This local test does not replace deployment acceptance: check `/api/options`
against the deployed service configuration and verify that `GET /` returns HTTP
200 HTML on the same candidate deployment.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
