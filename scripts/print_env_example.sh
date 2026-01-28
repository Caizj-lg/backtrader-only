#!/usr/bin/env bash
cat <<'EOF'
export FEISHU_APP_ID="cli_xxxxx"
export FEISHU_APP_SECRET="xxxxxx"

export GITHUB_TOKEN="ghp_xxxxx"
export GITHUB_OWNER="你的github用户名或组织名"
export GITHUB_REPO="你的仓库名"

export GITHUB_WORKFLOW_FILE="backtest.yml"
export GITHUB_REF="main"

# export FEISHU_DEBUG_LOG_PAYLOAD=1
# export FEISHU_BOT_OPEN_ID="ou_xxx"
EOF
