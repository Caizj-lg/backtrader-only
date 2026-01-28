from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from backtest.config import BacktestConfig
from backtest.feishu import send_feishu_text
from backtest.run_backtest import BacktestInputs, BacktestMetrics, run_backtest


@dataclass
class FeishuConfig:
    app_id: str
    app_secret: str
    app_token: str
    table_id: str


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少环境变量：{name}")
    return value


def _get_tenant_access_token(cfg: FeishuConfig) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(
        url,
        json={"app_id": cfg.app_id, "app_secret": cfg.app_secret},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
    return data["tenant_access_token"]


def _feishu_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _list_pending_records(token: str, cfg: FeishuConfig, limit: int) -> List[Dict[str, Any]]:
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{cfg.app_token}"
        f"/tables/{cfg.table_id}/records"
    )
    params = {
        "page_size": str(limit),
        "filter": 'CurrentValue.[status] = "待回测"',
    }
    resp = requests.get(url, headers=_feishu_headers(token), params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"查询表格失败: {data}")
    return data.get("data", {}).get("items", [])


def _update_record(
    token: str, cfg: FeishuConfig, record_id: str, fields: Dict[str, Any]
) -> None:
    url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{cfg.app_token}"
        f"/tables/{cfg.table_id}/records/{record_id}"
    )
    payload = {"fields": fields}
    resp = requests.put(url, headers=_feishu_headers(token), json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"更新记录失败: {data}")


def _parse_date_value(value: Any) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
    if isinstance(value, dict) and "value" in value:
        return _parse_date_value(value["value"])
    if isinstance(value, str):
        return value.strip()
    raise ValueError(f"无法解析日期字段：{value!r}")


def _parse_float(value: Any, field: str, default: float) -> float:
    if value is None or value == "":
        return float(default)
    try:
        return float(value)
    except ValueError as ex:
        raise ValueError(f"{field} 必须为数字") from ex


def _parse_int(value: Any, field: str, default: int) -> int:
    if value is None or value == "":
        return int(default)
    try:
        return int(value)
    except ValueError as ex:
        raise ValueError(f"{field} 必须为整数") from ex


def _get_field(fields: Dict[str, Any], name: str) -> Any:
    value = fields.get(name)
    if isinstance(value, dict) and "text" in value:
        return value["text"]
    return value


def _format_summary(
    inputs: BacktestInputs, metrics: BacktestMetrics, datasource_used: str, run_url: str
) -> str:
    run_meta = f" | URL={run_url}" if run_url else ""
    return (
        f"回测完成（MVP）\n"
        f"标的：{inputs.symbol}\n"
        f"区间：{inputs.start_date} ~ {inputs.end_date}\n"
        f"参数：TP={inputs.take_profit:.2%} SL={inputs.stop_loss:.2%} "
        f"Hold={inputs.max_hold_days} Cash={inputs.cash:.0f}\n"
        f"数据源：{datasource_used}\n"
        f"结果：总收益={metrics.total_return:.2%} 最大回撤={metrics.max_drawdown:.2%} "
        f"胜率={metrics.win_rate:.2%} 交易次数={metrics.trades} "
        f"资金：{metrics.start_cash:.0f} -> {metrics.end_value:.0f}"
        f"{run_meta}"
    )


def main() -> int:
    cfg = FeishuConfig(
        app_id=_require_env("FEISHU_APP_ID"),
        app_secret=_require_env("FEISHU_APP_SECRET"),
        app_token=_require_env("FEISHU_BITABLE_APP_TOKEN"),
        table_id=_require_env("FEISHU_BITABLE_TABLE_ID"),
    )
    token = _get_tenant_access_token(cfg)

    limit = int(os.getenv("FEISHU_TASK_LIMIT", "1"))
    records = _list_pending_records(token, cfg, limit)
    if not records:
        print("no pending tasks")
        return 0

    run_url = os.getenv("RUN_URL", "")
    for record in records:
        record_id = record.get("record_id")
        fields = record.get("fields", {})
        if not record_id or not isinstance(fields, dict):
            continue

        try:
            # 抢占任务
            _update_record(token, cfg, record_id, {"status": "运行中"})

            symbol = str(_get_field(fields, "symbol") or "").strip()
            start_date = _parse_date_value(_get_field(fields, "start_date"))
            end_date = _parse_date_value(_get_field(fields, "end_date"))
            take_profit = _parse_float(_get_field(fields, "take_profit"), "take_profit", 0.03)
            stop_loss = _parse_float(_get_field(fields, "stop_loss"), "stop_loss", -0.05)
            max_hold_days = _parse_int(_get_field(fields, "max_hold_days"), "max_hold_days", 10)
            cash = _parse_float(_get_field(fields, "cash"), "cash", 100000)
            datasource = str(_get_field(fields, "datasource") or "tushare").strip() or "tushare"

            if len(symbol) != 6 or not symbol.isdigit():
                raise ValueError("symbol 必须为 6 位数字")

            inputs = BacktestInputs(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                take_profit=float(take_profit),
                stop_loss=float(stop_loss),
                max_hold_days=int(max_hold_days),
                cash=float(cash),
                run_note="bitable",
                run_id=os.getenv("GITHUB_RUN_ID", ""),
                datasource=datasource,  # type: ignore[arg-type]
            )

            report, datasource_used = run_backtest(inputs, BacktestConfig(cash=float(cash)))
            metrics = BacktestMetrics(**report["metrics"])
            summary = _format_summary(inputs, metrics, datasource_used, run_url)

            result_text = summary[:900]
            _update_record(token, cfg, record_id, {"status": "已完成", "result": result_text})

            send_feishu_text(os.getenv("FEISHU_WEBHOOK"), summary)
        except Exception as ex:  # noqa: BLE001 - MVP: 尽量回写失败原因
            err_text = f"失败：{type(ex).__name__}: {ex}"
            _update_record(token, cfg, record_id, {"status": "失败", "result": err_text[:900]})
            send_feishu_text(os.getenv("FEISHU_WEBHOOK"), err_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
