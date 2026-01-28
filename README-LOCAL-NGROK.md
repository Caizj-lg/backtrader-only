## 本机 + ngrok 最小闭环（@机器人 → 表单 → Actions → 回群）

> 适用场景：不使用 Render/公网服务器，直接在本机用 ngrok 暴露回调。

### 0) 前置条件
- 飞书开放平台已有应用（机器人已开启并拉进群）
- GitHub 仓库已存在 workflow_dispatch 的回测工作流
- 本机 macOS + Python 3.9+

### 1) 准备环境变量（当前终端生效）

```bash
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxxx"

export GITHUB_TOKEN="ghp_xxxxx"
export GITHUB_OWNER="你的github用户名或组织名"
export GITHUB_REPO="你的仓库名"

# 可选（如 workflow 名称/分支不是默认）
export GITHUB_WORKFLOW_FILE="backtest.yml"
export GITHUB_REF="main"

# 可选：调试用
# export FEISHU_DEBUG_LOG_PAYLOAD=1
# export FEISHU_BOT_OPEN_ID="ou_xxx"
```

### 2) 启动本地服务

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn server.feishu_callback:app --host 0.0.0.0 --port 8000 --reload
```

看到 `Uvicorn running on http://0.0.0.0:8000` 即成功。

### 3) 启动 ngrok

```bash
brew install ngrok/ngrok/ngrok
ngrok config add-authtoken <你的token>
ngrok http 8000
```

记下 ngrok 地址，例如：
`https://abcd-1234.ngrok-free.app`

### 4) 配置飞书回调地址

飞书开放平台 → 你的应用 → 事件订阅：

- 事件订阅 URL：
  `https://abcd-1234.ngrok-free.app/feishu/event`
- 勾选事件：`im.message.receive_v1`
- 保存并发布应用

卡片交互回调：

- Request URL：
  `https://abcd-1234.ngrok-free.app/feishu/card-callback`

### 5) 验证流程

1) 群里 @机器人 → 应该自动回传表单卡片
2) 提交表单 → GitHub Actions 被触发
3) 回测完成后，飞书群收到摘要

### 常见问题

- ngrok 地址重启会变化，**必须同步更新飞书回调 URL**
- @ 无响应：检查事件订阅是否发布、机器人是否在群里、是否勾选 `im.message.receive_v1`
