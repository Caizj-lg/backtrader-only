from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import requests


@dataclass
class _TokenCache:
    token: str = ""
    expire_at: float = 0.0


_TOKEN_CACHE = _TokenCache()


def _get_tenant_access_token() -> str:
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("缺少环境变量：FEISHU_APP_ID / FEISHU_APP_SECRET")

    now = time.time()
    if _TOKEN_CACHE.token and _TOKEN_CACHE.expire_at - now > 60:
        return _TOKEN_CACHE.token

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

    _TOKEN_CACHE.token = data["tenant_access_token"]
    _TOKEN_CACHE.expire_at = now + int(data.get("expire", 3600))
    return _TOKEN_CACHE.token


def load_card_json() -> Dict[str, Any]:
    card_path = Path(__file__).resolve().parents[1] / "feishu" / "card_backtest_mvp.json"
    return json.loads(card_path.read_text(encoding="utf-8"))


def send_interactive_card(chat_id: str, card: Dict[str, Any]) -> None:
    token = _get_tenant_access_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "receive_id": chat_id,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"发送卡片失败: {data}")
