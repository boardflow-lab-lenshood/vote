# Options API tests

From the repository root, install the existing application dependencies and run
only the options API tests:

```sh
python -m venv tests/.venv
tests/.venv/bin/python -m pip install -r requirements.txt
tests/.venv/bin/python -B -m unittest discover -s tests -p 'test_api_options.py' -v
```

The test runner is Python's standard-library `unittest`; no extra test packages
are required. Flask and Redis's Python client are imported by the application,
but these tests do not need a Redis server, a prior vote, or a deployed service.
Existing voting regression tests use a mock Redis client.

The API tests check HTTP 200, the `application/json` media type, exactly
`Cache-Control: no-store`, and the complete `a`/`b` JSON for absent environment
variables, custom Unicode labels, and explicitly empty labels. Each test removes
`OPTION_A` and `OPTION_B` before loading the app and restores the original
environment and module configuration afterward. The endpoint is also checked for
Redis/cookie side effects; the homepage, poll-info API, and stylesheet are checked
for an unintended `no-store` policy.
