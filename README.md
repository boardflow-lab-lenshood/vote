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
外部 CDN 请求被阻断；按钮禁用和追加勾选节点使用原生 DOM，不依赖 jQuery。
此隔离测试不验证 CDN 样式和图标字体的加载，也不代替测试泳道在确认候选部署上的验收。
Linux 主机需具备 Chromium 系统库；脚本不会自动安装系统依赖。

### 投票按钮的中文名称回归

`tests/test_vote_accessibility.py` 已纳入上述隔离单元测试，覆盖默认值、单独/同时
变化的选项、空值、中文、单双引号、`& < >`、实体及注入样例在无/a/b vote cookie
下的实际模板输出。按钮名称为 `投给` 加当前选项原文；可见文字和原生提交字段保留。

复用上述 worktree 内的虚拟环境和 Chromium，无须启动其他仓库或外部服务：

```sh
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python tests/browser_vote_accessibility.py
```

脚本在 `127.0.0.1` 随机端口启动本仓 Flask，先从 `/api/options` 读取预期选项，
再以真实 Chromium 检查六组选项的三种状态（共 18 组），包括 Playwright 精确
角色定位及 Chromium 可访问性树中的计算后名称。执行已投 b → a → b 的真实
按钮 POST，验证 `vote=a/b`、原 voter_id、队列写入、Cookie、禁用/勾选节点，
以及 GET 和刷新回读。Redis 写入由 spy 接管，其他 Redis 命令和连接直接失败；
外部 CDN 请求被阻断，页面的原生 DOM 状态增强仍实际执行。

证据保存在 `.test-artifacts/vote-accessibility-report.json`（时间、URL、git HEAD、
浏览器版本、三状态 DOM/计算名称、提交与错误记录），默认三状态截图为
`.test-artifacts/accessibility-{none,a,b}.png`。这些是隔离本地自测证据；真实候选
部署的三状态验收应由测试阶段另行记录部署 URL、版本及对应仓库提交。

`GET /api/regression/<name>?x=<integer>` loads `regression_features/<name>.py` and returns `evaluate(x)` as JSON. `name` must match `[a-z][a-z0-9_]{0,31}`. A missing module returns 404 JSON, a non-integer `x` returns 400 JSON, and a module exception returns 500 JSON with a diagnostic that does not include secrets. The built-in `echo` module returns `{"feature":"echo","value":x}`.
