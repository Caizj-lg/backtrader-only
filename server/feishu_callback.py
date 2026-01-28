from __future__ import annotations

from datetime import datetime
import json
import os
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request

from server.github_dispatch import dispatch_backtest_workflow
from server.feishu_bot import load_card_json, send_interactive_card

app = FastAPI()


def _deep_get(d: Any, keys: list[str]) -> Optional[Any]:
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _find_first(payload: Dict[str, Any], candidates: list[list[str]]) -> Optional[Any]:
    for path in candidates:
        v = _deep_get(payload, path)
        if v is not None:
            return v
    return None


def _extract_form(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    飞书卡片回调 payload 结构会随卡片版本/配置略有不同。
    这里做“尽量鲁棒”的提取：优先找常见 form 字段容器。
    """
    # 常见：payload.action.form_value / payload.action.value / payload.form / payload.form_value
    form = _find_first(
        payload,
        candidates=[
            ["action", "form_value"],
            ["action", "formValue"],
            ["action", "value"],
            ["form_value"],
            ["formValue"],
            ["form"],
        ],
    )
    if isinstance(form, dict):
        return form
    return {}


def _parse_date(value: str, field: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as ex:
        raise ValueError(f"{field} 必须为 YYYY-MM-DD") from ex
    return value


def _parse_float(value: str, field: str) -> float:
    try:
        return float(value)
    except ValueError as ex:
        raise ValueError(f"{field} 必须为数字") from ex


def _parse_int(value: str, field: str) -> int:
    try:
        return int(value)
    except ValueError as ex:
        raise ValueError(f"{field} 必须为整数") from ex


def _validate_inputs(form: Dict[str, Any]) -> Dict[str, str]:
    symbol = str(form.get("symbol", "")).strip()
    start_date = str(form.get("start_date", "")).strip()
    end_date = str(form.get("end_date", "")).strip()
    take_profit_raw = str(form.get("take_profit", "0.03")).strip()
    stop_loss_raw = str(form.get("stop_loss", "-0.05")).strip()
    max_hold_days_raw = str(form.get("max_hold_days", "10")).strip()
    cash_raw = str(form.get("cash", "100000")).strip()

    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("symbol 必须为 6 位数字")

    start_date = _parse_date(start_date, "start_date")
    end_date = _parse_date(end_date, "end_date")
    if start_date >= end_date:
        raise ValueError("start_date 必须小于 end_date")

    take_profit = _parse_float(take_profit_raw, "take_profit")
    stop_loss = _parse_float(stop_loss_raw, "stop_loss")
    max_hold_days = _parse_int(max_hold_days_raw, "max_hold_days")
    cash = _parse_float(cash_raw, "cash")

    if take_profit <= 0:
        raise ValueError("take_profit 必须 > 0")
    if stop_loss >= 0:
        raise ValueError("stop_loss 必须 < 0")
    if not (1 <= max_hold_days <= 200):
        raise ValueError("max_hold_days 必须在 1~200")
    if cash <= 0:
        raise ValueError("cash 必须 > 0")

    # MVP：仅基础校验，详细校验留 TODO
    inputs: Dict[str, str] = {
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "take_profit": f"{take_profit}",
        "stop_loss": f"{stop_loss}",
        "max_hold_days": f"{max_hold_days}",
        "cash": f"{cash}",
        "datasource": "auto",
    }
    return inputs


@app.post("/feishu/card-callback")
async def feishu_card_callback(req: Request) -> Dict[str, Any]:
    payload = await req.json()

    # TODO: 鉴权/签名校验（MVP 先跑通链路）

    try:
        form = _extract_form(payload)
        inputs = _validate_inputs(form)

        # 立刻触发 workflow_dispatch；若要“更快返回避免超时”，可改为后台任务/队列
        dispatch_backtest_workflow(inputs)
        return {"ok": True, "msg": "已触发回测"}
    except Exception as ex:  # noqa: BLE001 - MVP：优先回 200 避免飞书重试
        return {"ok": False, "msg": f"触发失败：{type(ex).__name__}: {ex}"}


def _mentioned_bot(payload: Dict[str, Any]) -> bool:
    event = payload.get("event", {})
    message = event.get("message", {}) if isinstance(event, dict) else {}
    mentions = message.get("mentions", []) if isinstance(message, dict) else []

    bot_open_id = os.getenv("FEISHU_BOT_OPEN_ID")
    if not mentions:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            try:
                content_obj = json.loads(content)
                content_text = content_obj.get("text", "")
            except json.JSONDecodeError:
                content_text = content
        else:
            content_text = ""

        if bot_open_id:
            return bot_open_id in content_text
        return "<at " in content_text
    if not bot_open_id:
        return True
    for m in mentions:
        mid = m.get("id", {}) if isinstance(m, dict) else {}
        if mid.get("open_id") == bot_open_id:
            return True
    return False


@app.post("/feishu/event")
async def feishu_event(req: Request) -> Dict[str, Any]:
    payload = await req.json()

    # 飞书回调校验（URL verification）
    if "challenge" in payload:
        return {"challenge": payload.get("challenge")}

    if os.getenv("FEISHU_DEBUG_LOG_PAYLOAD") == "1":
        print("feishu_event_payload:", json.dumps(payload, ensure_ascii=False))

    event = payload.get("event", {})
    if not isinstance(event, dict):
        return {"ok": True}

    # 忽略机器人自己发送的消息，避免死循环
    sender = event.get("sender", {})
    if isinstance(sender, dict) and sender.get("sender_type") == "app":
        return {"ok": True}

    header = payload.get("header", {})
    event_type = header.get("event_type") if isinstance(header, dict) else None
    if event.get("type") != "message" and event_type != "im.message.receive_v1":
        return {"ok": True}

    if not _mentioned_bot(payload):
        return {"ok": True}

    message = event.get("message", {})
    chat_id = message.get("chat_id") if isinstance(message, dict) else None
    if not chat_id:
        return {"ok": True}

    try:
        card = load_card_json()
        send_interactive_card(chat_id, card)
        return {"ok": True}
    except Exception as ex:  # noqa: BLE001 - MVP: 避免重试风暴
        return {"ok": False, "msg": f"发送卡片失败：{type(ex).__name__}: {ex}"}
