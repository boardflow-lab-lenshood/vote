# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` accepts only the exact form values `vote=a` or `vote=b` and enqueues `{voter_id, vote}` on the Redis `votes` list. Missing or other values return HTTP 400 with `Content-Type: application/json` and `{"error":"invalid_vote"}`, without accessing Redis or changing the existing vote cookie.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "Cats", "b": "Dogs"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `Cats` and `Dogs`.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.

## Isolated tests

Use Python 3.11 or newer (the Docker runtime uses 3.11). From the repository or this card's worktree:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -p 'test_vote_validation.py' -v
```

No Redis service, database, containers, or shared data are needed. The tests replace the Redis constructor with a recording mock, exercise the real Flask routes and cookie jar, and assert zero Redis method calls for each invalid input (missing, empty, whitespace, `c`, `A`, ` a`, `a `, ` a `), with no existing vote and with each of `vote=a` and `vote=b`. They also check valid a/b queue payloads, new and existing voter identities, confirmation after refresh without another enqueue, and both directions of changing a vote.

Run all existing regression tests with:

```sh
.venv/bin/python -m unittest discover -s tests -v
```
