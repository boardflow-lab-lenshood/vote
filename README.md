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

## 投票输入校验与隔离回归

`POST /` 只接受表单中精确的 `vote=a` 或 `vote=b`。缺字段、空串、空格、
制表符、未知选项、大小写不符或带前后空格的值均返回 HTTP 400、
`Content-Type: application/json` 和精确对象 `{"error":"invalid_vote"}`。
校验在 Redis 获取和入队前完成，不更新或清除已有 `vote` cookie。
合法投票继续返回 HTML，将仅含 `voter_id`、`vote` 的 JSON 字符串追加到
`votes` 队列；页面确认、刷新回读、身份复用及双向改投保持原行为。

以下命令从仓库根目录执行，使用 Python 3.11+。依赖、浏览器和缓存均留在
当前 worktree，不需要启动 Redis 或连接共享服务：

```sh
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tests/run_isolated.py
# 只执行本需求的接口测试：
.venv/bin/python tests/run_isolated.py --pattern test_vote_validation.py
```

`run_isolated.py` 运行既有 unittest 测试并阻断 Redis 网络连接（含健康检查）。
`test_vote_validation.py` 在实际 `Redis.rpush` 方法上安装写 spy，同时拒绝
其他 Redis 命令。覆盖 9 种非法表单 × 无/a/b vote cookie 的 27 个组合，
逐项检查 400、精确 JSON、零写入、无 vote Set-Cookie 及刷新后的原状态。
合法 a/b 是同一 spy 的正向对照，校验队列、字符串格式、精确字段、
缺失/空/已有身份 cookie、页面确认及 a→b、b→a；GET 不产生额外写入。

可选的真实浏览器回归：

```sh
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements-test.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python tests/browser_vote_flow.py
```

脚本临时启动实际 Flask HTTP 服务，仅绑定 `127.0.0.1` 随机端口，结束即关闭。
Chromium 通过实际 HTTP 请求及按钮提交验证 27 个非法组合、4 次合法投票/
双向改投、cookie 和刷新回读；Redis 写入由同一方法的 spy 记录，其他 Redis
命令被拒绝。报告和截图保存到忽略的 `.test-artifacts/`。
外部 CDN 请求被阻断，既有页面依赖 CDN 的 jQuery 可能产生 `$ is not defined`，
会原样记录在报告中；此隔离测试覆盖原生表单和服务端状态，不验证 CDN
样式、图标和 jQuery 增强行为，也不代替测试泳道在确认候选部署上的验收。
Linux 主机需具备 Chromium 系统库；脚本不会自动安装系统依赖。

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
