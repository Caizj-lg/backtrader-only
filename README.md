## A股回测 MVP（Backtrader）- 止盈/止损 + 区间回测 + 飞书触发 + 飞书回传

### 你将得到什么
- **P0**：GitHub Actions `workflow_dispatch` 手动触发回测 → 生成 `artifacts/report.json` → **飞书群机器人 webhook 回传摘要**
- **P1**：FastAPI 接飞书卡片回调 → 触发 GitHub Actions → 回传飞书

### 目录结构
- `backtest/`：回测核心
- `.github/workflows/backtest.yml`：Actions 工作流（可手动触发）
- `server/`：飞书卡片回调服务（FastAPI）

### 本地运行（P0）
1) 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) 配置环境变量（二选一数据源，推荐 tushare）
- `TUSHARE_TOKEN`：tushare token（可选，但推荐）
- `FEISHU_WEBHOOK`：飞书群机器人 webhook（可选，本地跑通也能不发）

3) 运行回测

```bash
python -m backtest.run_backtest \
  --symbol 600519 \
  --start_date 2023-01-01 \
  --end_date 2024-12-31 \
  --take_profit 0.03 \
  --stop_loss -0.05 \
  --max_hold_days 10 \
  --datasource auto
```

输出：
- `report.json`（当前工作目录）
- 若设置了 `FEISHU_WEBHOOK`：飞书收到一条摘要消息

### GitHub Actions（P0）
需要配置 Secrets：
- `TUSHARE_TOKEN`
- `FEISHU_WEBHOOK`

在 Actions 页面找到 `AShare Backtest MVP`，点击 **Run workflow** 手动填写参数触发。

### Server（P1）
回调服务用于接飞书卡片提交，触发 GitHub Actions：
- 需要环境变量：`GITHUB_TOKEN`（可触发 workflow_dispatch 的 PAT）、`GITHUB_OWNER`、`GITHUB_REPO`
- 运行：

```bash
uvicorn server.feishu_callback:app --host 0.0.0.0 --port 8000
```

### 端到端流程（建议顺序）
1) P0：先用 Actions 手动触发一次
   - 设置 Secrets：`TUSHARE_TOKEN`、`FEISHU_WEBHOOK`
   - 触发 `AShare Backtest MVP` workflow
   - 预期：Actions 成功，产出 `artifacts/report.json`，飞书群里收到摘要

2) P1：飞书卡片回调触发 Actions
   - 启动回调服务（本地或部署到公网）
   - 环境变量：
     - `GITHUB_TOKEN`（workflow dispatch 权限）
     - `GITHUB_OWNER`（仓库 owner）
     - `GITHUB_REPO`（仓库名）
     - 可选：`GITHUB_WORKFLOW_FILE`（默认 backtest.yml）
     - 可选：`GITHUB_REF`（默认 main）
   - 在飞书开放平台配置卡片交互回调 URL：
     - `POST https://<your-domain>/feishu/card-callback`
   - 在群里发送 `feishu/card_backtest_mvp.json` 对应的卡片，提交表单
   - 预期：触发 Actions → 回测完成 → 群里收到摘要

### 安全提示（MVP 之后补）
- 飞书回调鉴权/签名校验（TODO）
- GitHub Token 权限最小化（仅 workflow dispatch）
- 生产环境使用新的 Token，过期或泄露及时轮换

### TODO（MVP 之后补）
- 飞书回调签名校验/鉴权
- 参数校验更严格（边界/日期交易日）
- 回传卡片结果、上传 equity 曲线图
