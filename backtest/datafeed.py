from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

import pandas as pd


DataSource = Literal["auto", "tushare", "akshare"]


@dataclass(frozen=True)
class AShareDailyBar:
    df: pd.DataFrame
    datasource_used: str


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip()
    if len(s) != 6 or not s.isdigit():
        raise ValueError(f"symbol 必须为 6 位数字，收到：{symbol!r}")
    return s


def _validate_dates(start_date: str, end_date: str) -> tuple[str, str]:
    try:
        s = datetime.strptime(start_date, "%Y-%m-%d").date()
        e = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as ex:
        raise ValueError("日期格式必须为 YYYY-MM-DD") from ex
    if s >= e:
        raise ValueError(f"start_date 必须小于 end_date，收到：{start_date} ~ {end_date}")
    return start_date, end_date


def _to_bt_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Backtrader expects columns: open, high, low, close, volume (and optional openinterest),
    with a DateTimeIndex.
    """
    if df.empty:
        return df
    out = df.copy()
    out = out.sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in out.columns:
            raise ValueError(f"数据缺少列: {col}")
    out = out[["open", "high", "low", "close", "volume"]]
    out.index = pd.to_datetime(out.index)
    return out


def _load_tushare_daily(symbol: str, start_date: str, end_date: str, token: str) -> Optional[pd.DataFrame]:
    import tushare as ts

    pro = ts.pro_api(token)
    # tushare: ts_code like 600519.SH / 000001.SZ
    ts_code = f"{symbol}.SH" if symbol.startswith("6") else f"{symbol}.SZ"
    df = pro.daily(ts_code=ts_code, start_date=start_date.replace("-", ""), end_date=end_date.replace("-", ""))
    if df is None or df.empty:
        return None

    # tushare columns: trade_date, open, high, low, close, vol(手), amount
    df = df.rename(columns={"trade_date": "date", "vol": "volume"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    # vol is in "hand" (100 shares). We'll convert to shares to align more with common OHLCV.
    if "volume" in df.columns:
        df["volume"] = df["volume"].astype(float) * 100.0
    return _to_bt_df(df)


def _load_akshare_daily(symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
    import akshare as ak

    # akshare expects "symbol" like "600519" and date strings "YYYYMMDD"
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="",
    )
    if df is None or df.empty:
        return None

    # columns: 日期 开盘 收盘 最高 最低 成交量 成交额 振幅 涨跌幅 涨跌额 换手率
    df = df.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return _to_bt_df(df)


def load_a_share_daily(
    symbol: str,
    start_date: str,
    end_date: str,
    datasource: DataSource = "auto",
    tushare_token: Optional[str] = None,
) -> AShareDailyBar:
    """
    返回给 backtrader 使用的日线 OHLCV dataframe（DateTimeIndex + open/high/low/close/volume）

    - datasource=auto: tushare 优先，失败/空数据 -> akshare
    - datasource=tushare: 强制 tushare（需要 token）
    - datasource=akshare: 强制 akshare
    """
    symbol = _normalize_symbol(symbol)
    start_date, end_date = _validate_dates(start_date, end_date)

    if datasource not in ("auto", "tushare", "akshare"):
        raise ValueError(f"未知 datasource: {datasource}")

    last_err: Optional[Exception] = None

    if datasource in ("auto", "tushare"):
        token = tushare_token
        if not token:
            if datasource == "tushare":
                raise ValueError("datasource=tushare 需要提供 tushare_token（或环境变量 TUSHARE_TOKEN）")
        else:
            try:
                df = _load_tushare_daily(symbol, start_date, end_date, token)
                if df is not None and not df.empty:
                    return AShareDailyBar(df=df, datasource_used="tushare")
            except Exception as ex:  # noqa: BLE001 - MVP：先兜底
                last_err = ex

    if datasource in ("auto", "akshare"):
        try:
            df = _load_akshare_daily(symbol, start_date, end_date)
            if df is not None and not df.empty:
                return AShareDailyBar(df=df, datasource_used="akshare")
        except Exception as ex:  # noqa: BLE001 - MVP：先兜底
            last_err = ex

    if last_err:
        raise RuntimeError(f"数据拉取失败（{datasource=}）: {last_err}") from last_err
    raise RuntimeError(f"数据拉取失败（{datasource=}），返回空数据")

