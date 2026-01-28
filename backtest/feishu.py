from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests


def send_feishu_text(webhook: Optional[str], text: str) -> None:
    """
    MVP：只发文本消息到飞书群机器人 webhook。
    若未配置 webhook，直接跳过（本地/Actions 都可跑通）。
    """
    if not webhook:
        return

    payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
    resp = requests.post(webhook, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=15)
    resp.raise_for_status()


def get_feishu_webhook_from_env() -> Optional[str]:
    return os.getenv("FEISHU_WEBHOOK")

