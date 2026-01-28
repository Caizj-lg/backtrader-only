from __future__ import annotations

import os
from typing import Any, Dict

import requests


def dispatch_backtest_workflow(inputs: Dict[str, str]) -> None:
    """
    触发 GitHub Actions workflow_dispatch

    需要环境变量：
    - GITHUB_TOKEN: PAT（最小权限：repo + workflow）
    - GITHUB_OWNER: 仓库 owner
    - GITHUB_REPO: 仓库名
    - GITHUB_WORKFLOW_FILE: workflow 文件名（默认 backtest.yml）
    - GITHUB_REF: 分支/标签（默认 main）
    """
    token = os.getenv("GITHUB_TOKEN")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")
    workflow = os.getenv("GITHUB_WORKFLOW_FILE", "backtest.yml")
    ref = os.getenv("GITHUB_REF", "main")

    if not token or not owner or not repo:
        raise RuntimeError("缺少环境变量：GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO")

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload: Dict[str, Any] = {"ref": ref, "inputs": inputs}
    resp = requests.post(url, json=payload, headers=headers, timeout=15)
    if resp.status_code not in (201, 204):
        raise RuntimeError(f"GitHub dispatch 失败: {resp.status_code} {resp.text}")

