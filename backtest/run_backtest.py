from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

import backtrader as bt
import pandas as pd

from backtest.config import BacktestConfig
from backtest.datafeed import DataSource, load_a_share_daily
from backtest.feishu import get_feishu_webhook_from_env, send_feishu_text
from backtest.strategy import TpSlHoldStrategy


@dataclass(frozen=True)
class BacktestInputs:
    symbol: str
    start_date: str
    end_date: str
    take_profit: float
    stop_loss: float
    max_hold_days: int
    cash: float
    run_note: str
    run_id: str
    datasource: DataSource


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: float
    max_drawdown: float
    win_rate: float
    trades: int
    start_cash: float
    end_value: float


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="A股回测 MVP (Backtrader)")
    p.add_argument("--symbol", required=True, help="6 位股票代码，如 600519")
    p.add_argument("--start_date", required=True, help="YYYY-MM-DD")
    p.add_argument("--end_date", required=True, help="YYYY-MM-DD")
    p.add_argument("--take_profit", type=float, default=0.03)
    p.add_argument("--stop_loss", type=float, default=-0.05)
    p.add_argument("--max_hold_days", type=int, default=10)
    p.add_argument("--cash", type=float, default=100000.0)
    p.add_argument("--run_note", default="")
    p.add_argument("--run_id", default="")
    p.add_argument("--datasource", choices=["auto", "tushare", "akshare"], default="auto")
    p.add_argument("--report_path", default="report.json")
    return p.parse_args()


def _validate_params(
    take_profit: float,
    stop_loss: float,
    max_hold_days: int,
    cash: float,
    start_date: str,
    end_date: str,
) -> None:
    if take_profit <= 0:
        raise ValueError("take_profit 必须 > 0")
    if stop_loss >= 0:
        raise ValueError("stop_loss 必须 < 0")
    if not (1 <= max_hold_days <= 200):
        raise ValueError("max_hold_days 必须在 1~200")
    if cash <= 0:
        raise ValueError("cash 必须 > 0")
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d").date()
        e = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as ex:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from ex
    if s >= e:
        raise ValueError("start_date 必须小于 end_date")


def _calc_max_drawdown(equity: list[float]) -> float:
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        dd = (v - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return float(max_dd)


def _format_summary(inputs: BacktestInputs, metrics: BacktestMetrics, datasource_used: str) -> str:
    run_url = os.getenv("RUN_URL", "")
    run_meta = ""
    if inputs.run_note or inputs.run_id or run_url:
        parts = []
        if inputs.run_id:
            parts.append(f"RunID={inputs.run_id}")
        if inputs.run_note:
            parts.append(f"Note={inputs.run_note}")
        if run_url:
            parts.append(f"URL={run_url}")
        run_meta = " | " + " ".join(parts)
    return (
        f"回测完成（MVP）\n"
        f"标的：{inputs.symbol}\n"
        f"区间：{inputs.start_date} ~ {inputs.end_date}\n"
        f"参数：TP={inputs.take_profit:.2%} SL={inputs.stop_loss:.2%} Hold={inputs.max_hold_days} "
        f"Cash={inputs.cash:.0f}\n"
        f"数据源：{datasource_used}\n"
        f"结果：总收益={metrics.total_return:.2%} 最大回撤={metrics.max_drawdown:.2%} "
        f"胜率={metrics.win_rate:.2%} 交易次数={metrics.trades} "
        f"资金：{metrics.start_cash:.0f} -> {metrics.end_value:.0f}"
        f"{run_meta}"
    )


def run_backtest(inputs: BacktestInputs, cfg: BacktestConfig) -> tuple[dict[str, Any], str]:
    tushare_token = os.getenv("TUSHARE_TOKEN")
    bars = load_a_share_daily(
        symbol=inputs.symbol,
        start_date=inputs.start_date,
        end_date=inputs.end_date,
        datasource=inputs.datasource,
        tushare_token=tushare_token,
    )

    cerebro = bt.Cerebro(stdstats=False)
    cerebro.broker.setcash(cfg.cash)
    cerebro.broker.setcommission(commission=cfg.commission)

    data = bt.feeds.PandasData(dataname=bars.df)
    cerebro.adddata(data)
    cerebro.addstrategy(
        TpSlHoldStrategy,
        take_profit=inputs.take_profit,
        stop_loss=inputs.stop_loss,
        max_hold_days=inputs.max_hold_days,
        stake=cfg.stake,
    )

    # 收集每日权益曲线（用 Observer 更专业；MVP 直接遍历 data 和 broker）
    equity_curve: list[float] = []

    class EquityObserver(bt.Observer):
        lines = ("equity",)

        def next(self):  # type: ignore[override]
            equity_curve.append(float(self._owner.broker.getvalue()))

    cerebro.addobserver(EquityObserver)

    results = cerebro.run()
    strat: TpSlHoldStrategy = results[0]

    start_cash = float(cfg.cash)
    end_value = float(cerebro.broker.getvalue())
    total_return = (end_value - start_cash) / start_cash

    trades = strat.trades
    n_trades = len(trades)
    n_win = sum(1 for t in trades if float(t.get("pnlcomm", 0.0)) > 0)
    win_rate = (n_win / n_trades) if n_trades else 0.0
    max_dd = _calc_max_drawdown(equity_curve)

    metrics = BacktestMetrics(
        total_return=float(total_return),
        max_drawdown=float(max_dd),
        win_rate=float(win_rate),
        trades=int(n_trades),
        start_cash=start_cash,
        end_value=end_value,
    )

    report: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "inputs": asdict(inputs),
        "config": asdict(cfg),
        "datasource_used": bars.datasource_used,
        "metrics": asdict(metrics),
        "trades": trades,
        "equity_curve": equity_curve,
        "run_url": os.getenv("RUN_URL", ""),
    }
    return report, bars.datasource_used


def main() -> None:
    args = _parse_args()
    _validate_params(args.take_profit, args.stop_loss, args.max_hold_days, args.cash, args.start_date, args.end_date)

    inputs = BacktestInputs(
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
        take_profit=float(args.take_profit),
        stop_loss=float(args.stop_loss),
        max_hold_days=int(args.max_hold_days),
        cash=float(args.cash),
        run_note=str(args.run_note),
        run_id=str(args.run_id),
        datasource=args.datasource,  # type: ignore[assignment]
    )

    cfg = BacktestConfig(cash=float(args.cash))
    try:
        report, datasource_used = run_backtest(inputs, cfg)
        Path(args.report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        summary = _format_summary(inputs, BacktestMetrics(**report["metrics"]), datasource_used)
        send_feishu_text(get_feishu_webhook_from_env(), summary)
        print(summary)
    except Exception as ex:  # noqa: BLE001 - MVP：失败也回传
        msg = f"回测失败：{type(ex).__name__}: {ex}"
        send_feishu_text(get_feishu_webhook_from_env(), msg)
        raise


if __name__ == "__main__":
    main()
