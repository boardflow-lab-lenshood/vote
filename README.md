# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` accepts only the exact form values `vote=a` or `vote=b` and enqueues `{voter_id, vote}` on the Redis `votes` list. Missing or other values (including whitespace or uppercase) return HTTP 400, `Content-Type: application/json`, and `{"error":"invalid_vote"}` without Redis writes or changing an existing `vote` cookie. Valid votes retain confirmation, identity cookies, and switching between choices.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "Cats", "b": "Dogs"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `Cats` and `Dogs`.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.

## Isolated interface tests

Use Python 3.11 (matching the Docker image) or later. From the repository root, create an environment outside the checkout and install the runtime dependencies; the tests use the standard-library `unittest` runner:

```sh
python3 -m venv ../vote-test-venv
../vote-test-venv/bin/python -m pip install -r requirements.txt
../vote-test-venv/bin/python -m unittest discover -s tests -p 'test_vote_validation.py' -v
../vote-test-venv/bin/python -m unittest discover -s tests -v
```

`tests/test_vote_validation.py` exercises the Flask interface with a Redis write spy replacing the app's Redis constructor. No Redis server, shared data, credentials, or service ports are needed. Each of the eight invalid forms (missing field, empty string, three spaces, `c`, `A`, ` a`, `a `, ` a `) is checked without a saved choice and with saved `vote=a` and `vote=b`: status, content type, exact JSON object, direct zero `rpush`/Redis method calls, no `Set-Cookie` for `vote`, and the client's retained cookie. The same suite checks legal a/b confirmation, exact queue messages, generated/reused identity cookies, both switching directions, and GET/refresh confirmation (AC-01 through AC-14).

The full discovery command also runs the existing API and regression tests. To reproduce a delivery, check out its full commit SHA and record `git rev-parse HEAD`, the command, and the exit code. Deployment HTTP/cookie checks must use a separately verified deployment of that same commit; they do not replace the isolated spy's proof of zero Redis writes.
