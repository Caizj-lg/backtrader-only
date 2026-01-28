from __future__ import annotations

import backtrader as bt


class TpSlHoldStrategy(bt.Strategy):
    """
    MVP 规则：
    - 空仓时：下一根 K 线开盘买入（Backtrader 市价单默认 next bar open）
    - 持仓中：
      - low <= 止损价 -> 平仓（按止损价近似成交）
      - high >= 止盈价 -> 平仓（按止盈价近似成交）
      - 或持仓天数 >= max_hold_days -> 下一根开盘平仓

    说明：Backtrader 默认用 OHLC 的 close 来撮合；这里用“信号触发 + close 退出”的近似，
    并在 trade 里记录触发原因，满足 MVP 回传需求（不是精确撮合引擎）。
    """

    params = dict(
        take_profit=0.03,  # >0
        stop_loss=-0.05,  # <0
        max_hold_days=10,  # >=1
        stake=100,
    )

    def __init__(self) -> None:
        self.order = None
        self.entry_price = None
        self.hold_bars = 0
        self.exit_reason = None

        self.trades = []  # 用于产出 trades.csv / report.json

    def _reset_position_state(self) -> None:
        self.entry_price = None
        self.hold_bars = 0
        self.exit_reason = None

    def notify_order(self, order: bt.Order) -> None:
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.entry_price = float(order.executed.price)
                self.hold_bars = 0
            elif order.issell():
                # 卖出完成后，在 notify_trade 里记录收益；这里清状态
                self._reset_position_state()

        # 如果失败/取消也清掉挂单
        if order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.order = None
            return

        self.order = None

    def notify_trade(self, trade: bt.Trade) -> None:
        if not trade.isclosed:
            return
        self.trades.append(
            dict(
                dt=self.data.datetime.date(0).isoformat(),
                pnl=float(trade.pnl),
                pnlcomm=float(trade.pnlcomm),
                size=int(trade.size),
                price=float(trade.price),
                value=float(trade.value),
                commission=float(trade.commission),
                exit_reason=self.exit_reason or "unknown",
            )
        )

    def next(self) -> None:
        if self.order:
            return

        if not self.position:
            # 空仓立即入场（MVP：无入场条件）
            self.buy(size=self.p.stake)
            return

        # 持仓：累计持有天数（bar 数）
        self.hold_bars += 1

        if self.entry_price is None:
            # 理论上不该发生，防御
            self.entry_price = float(self.data.close[0])

        stop_price = self.entry_price * (1.0 + float(self.p.stop_loss))
        take_price = self.entry_price * (1.0 + float(self.p.take_profit))

        low = float(self.data.low[0])
        high = float(self.data.high[0])

        # 触发顺序：先止损再止盈（保守）
        if low <= stop_price:
            self.exit_reason = "stop_loss"
            self.sell(size=self.position.size)
            return

        if high >= take_price:
            self.exit_reason = "take_profit"
            self.sell(size=self.position.size)
            return

        if self.hold_bars >= int(self.p.max_hold_days):
            self.exit_reason = "max_hold_days"
            self.sell(size=self.position.size)
            return

