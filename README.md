# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "Cats", "b": "Dogs"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `Cats` and `Dogs`.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`. `regression_features/b.py` exposes `evaluate(x)`. Card acceptance requires `{"feature":"b","value":x * 3 + 2}`. The current first-round source intentionally returns `x * 3 + 3` (exactly +1 above acceptance) as an authorized regression injection; independent HTTP acceptance of this revision should fail.
