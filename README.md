# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "Cats", "b": "Dogs"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`.
The example above uses `OPTION_A=Cats` and `OPTION_B=Dogs`. Labels are read when
the service module loads. Successful `GET /api/options` responses include
`Cache-Control: no-store`; the JSON object still contains only `a` and `b`.

Run the independent options/cache contract tests from the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_api_options_cache.py' -v
```

The tests isolate default and custom option configuration, verify repeated
responses, restore environment state, and leave any existing `app` module
untouched. They block Redis access and need no Redis server or prior regression
test run. The cache policy is also checked to remain local to `/api/options`.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
