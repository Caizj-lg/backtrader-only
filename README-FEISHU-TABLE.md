## 飞书多维表格 → GitHub Actions 回测（零服务器版）

> 适用场景：不想维护公网服务/回调，仅用飞书输入 + GitHub 执行 + 飞书回传。

### 目标（最小闭环）
飞书多维表格填一行参数  
→ 点击「开始回测」按钮  
→ 打开 GitHub Actions 页面  
→ 点击 Run workflow  
→ Actions 回测  
→ 飞书群 Webhook 回传结果

### 一、飞书多维表格字段设计（保持项目现有字段）

| 字段名 | 类型 | 说明 | 备注 |
|---|---|---|---|
| symbol | 文本 | 股票代码，如 600519 | 必填 |
| start_date | 日期 | 回测开始日期 | 必填 |
| end_date | 日期 | 回测结束日期 | 必填 |
| take_profit | 数字 | 止盈比例，如 0.03 | 默认 0.03 |
| stop_loss | 数字 | 止损比例，如 -0.05 | 默认 -0.05 |
| max_hold_days | 数字 | 最大持有天数，如 10 | 默认 10 |
| cash | 数字 | 初始资金，如 100000 | 默认 100000 |
| status | 单选 | 待回测 / 已提交 / 已完成 | 可选 |
| result | 文本 | 回测结果摘要 | 可选 |
| 🚀开始回测 | 按钮 | 打开 GitHub Actions | 必配 |

> 注意：飞书按钮**不能自动把表格值传给 Actions**，你需要手动复制填写。

### 二、配置「开始回测」按钮

按钮动作：**打开链接**  
链接填写（替换为你的仓库）：  

```
https://github.com/Caizj-lg/backtrader-only/actions/workflows/backtest.yml
```

（也可以从 GitHub Actions 页面复制 workflow 链接）

### 三、Actions 必须支持 workflow_dispatch（已具备）
当前 workflow 已支持以下 inputs：

```
symbol, start_date, end_date, take_profit, stop_loss, max_hold_days, cash, datasource
```

### 四、使用流程（每日操作）
1) 在多维表格新增一行，填写参数  
2) 点击 🚀开始回测（打开 Actions 页面）  
3) 手动点击 Run workflow 并填入参数  
4) 等待执行完成  
5) 飞书群收到回测摘要（通过 FEISHU_WEBHOOK）

### 常见问题
- **按钮不会自动传参**：这是飞书按钮能力限制，只能打开链接  
- **字段名必须一致**：用本文档中的字段名  
- **忘了设置 Secrets**：确保 GitHub Secrets 已设置 `FEISHU_WEBHOOK`（回传）和 `TUSHARE_TOKEN`（可选）
