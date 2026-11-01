# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels plus a service identifier:

```json
{"a": "猫派", "b": "狗派", "service": "vote", "option_count": 2}
```

Existing keys `a` and `b` stay compatible. Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`. `option_count` is the number of option entries, not a fixed constant. Optional extra entries can be supplied as `OPTIONS=c=鸟派,d=鱼派`; blank items and keys that collide with `a` or `b` are ignored.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
