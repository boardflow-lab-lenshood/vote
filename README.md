# Vote

Voting frontend. Existing routes are unchanged:

- `GET /` renders the voting page.
- `POST /` enqueues `{voter_id, vote}` on the Redis `votes` list.
- `GET /healthz` reports Redis readiness.

`GET /api/options` returns the current option labels as JSON:

```json
{"a": "猫派", "b": "狗派"}
```

Labels come from `OPTION_A` and `OPTION_B`, defaulting to `猫派` and `狗派`. The native voting buttons expose the accessible names `投给{OPTION_A}` and `投给{OPTION_B}`, including after a vote is selected.

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.

## Isolated tests

From the repository worktree, create a local environment and run the existing unit suite:

```sh
python -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

The optional Chromium test starts the real Flask HTTP app on an ephemeral loopback port, mocks Redis, and blocks remote CDN assets. It checks browser-computed accessible names, DOM escaping, disabled buttons, decorative check icons, native submissions in both directions, and refresh persistence for default and special-character option values. Install the browser once (a Linux host with Chromium's system libraries is required):

```sh
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements-test.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" VOTE_BROWSER_ARTIFACTS="$PWD/.cache/browser-artifacts" .venv/bin/python -m unittest discover -s tests -p browser_vote_accessibility.py -v
```

No real Redis, worker, or other external service is used by either test command. Screenshots and browser accessibility snapshots are saved when `VOTE_BROWSER_ARTIFACTS` is set. These local checks do not replace the downstream browser acceptance checks on the current deployment.
