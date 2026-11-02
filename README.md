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

Run the automated tests with the service dependencies installed:

```sh
python -m unittest discover -s tests -v
```

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
