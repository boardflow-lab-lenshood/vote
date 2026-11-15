# 选项说明接口禁止缓存回归

在 vote 仓库根目录执行，使用 Python 3.11+：

```sh
python3 -m venv .venv
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements.txt
```

独立运行本需求的接口测试两次，每条命令均启动一个新的 Python 进程：

```sh
.venv/bin/python tests/test_options_cache_control.py
.venv/bin/python tests/test_options_cache_control.py
```

测试内部暂时清除 `OPTION_A`、`OPTION_B`，加载应用并验证中文默认值；随后单独加载 Tea/Coffee 配置。结束时恢复原环境及应用，不依赖调用者的标签配置。断言两个接口的 `200`、`application/json`、`Cache-Control: no-store`、完整 JSON、字段类型、选项 ID/顺序，以及有无 cookie 时均不新增 cookie、不访问 Redis。另验证静态 CSS 可读取且未新增 `no-store`。

全量既有单元测试使用 Redis 网络隔离入口；显式设置标签以满足既有测试的固定预期：

```sh
OPTION_A='猫派' OPTION_B='狗派' .venv/bin/python tests/run_isolated.py
```

真实浏览器回归沿用项目既有脚本：

```sh
PIP_CACHE_DIR="$PWD/.cache/pip" .venv/bin/python -m pip install -r requirements-test.txt
PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python -m playwright install chromium
OPTION_A='猫派' OPTION_B='狗派' PLAYWRIGHT_BROWSERS_PATH="$PWD/.cache/ms-playwright" .venv/bin/python tests/browser_vote_flow.py
```

脚本在本机随机端口启动真实 Flask HTTP 服务并驱动无头 Chromium，记录合法投票、改投、cookie、刷新及非法请求回归。浏览器与单元测试中的 Redis 使用隔离替身，不代表已验证真实 Redis 持久化；浏览器产物保存于 `.test-artifacts/`，不会纳入提交。

本地测试不能替代需求 AC18 的公开部署证据。下游部署/测试时，须针对本卡交付版本的两个接口分别记录公开 URL、采集时间、HTTP 状态、Content-Type、Cache-Control 和完整 JSON 正文，并关联交付提交、部署版本与实际 `OPTION_A`/`OPTION_B` 配置；禁止复用旧卡产物。
