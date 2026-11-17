# 页面语义回归

单元测试沿用标准库 unittest，覆盖当前选项配置、HTML 转义、唯一 main/h1、原生 POST 表单，以及 a/b 确认与 cookie 回读：

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

`browser_semantics.py` 单独运行真实 Chromium，不参与单元测试自动发现。开发环境另需安装 `playwright` 和 Chromium（`python -m playwright install chromium`），不增加产品运行时依赖。浏览器、依赖和截图缓存应放在隔离 worktree 中。

运行前准备彼此隔离的 Redis、PostgreSQL 和真实 vote/result 服务；`votes` 表仅使用测试数据。准备两个 vote 实例，分别使用默认猫派/狗派与 `OPTION_A=茶派 OPTION_B=咖啡派`。确保两个实例实际连接到测试 Redis。

```sh
VOTE_URL=http://127.0.0.1:43811 \
CUSTOM_VOTE_URL=http://127.0.0.1:43813 \
RESULT_URL=http://127.0.0.1:43812 \
TEST_REDIS_PORT=46379 \
TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:45432/postgres \
RESULT_REPO=/absolute/path/to/result/worktree \
python tests/browser_semantics.py
```

`RESULT_REPO` 用于通过 result 的既有 `pg` 依赖插入隔离数据库夹具。脚本检查真实 DOM/无障碍树、鼠标和 Tab/Enter 的原生 POST、队列写入、确认文案、cookie 回读，以及 result 的真实 scores 推送与刷新回读。POST 后先用 GET 重开页面，再刷新，避免把浏览器重发 POST 当作 GET 回读。

截图、AX 树和 JSON 报告默认保存在 `.local/browser`，可用 `BROWSER_ARTIFACTS` 配置。脚本会向测试队列和数据库写入数据，禁止指向共享或生产环境。数据库夹具不是 worker 端到端验收；真实部署版本、worker 消费及投票增量仍需由平台测试完成。
