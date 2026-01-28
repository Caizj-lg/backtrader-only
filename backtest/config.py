from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestConfig:
    cash: float = 100000.0
    commission: float = 0.0003  # 万3
    stake: int = 100  # 每次买入股数

