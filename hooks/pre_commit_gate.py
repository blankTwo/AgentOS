#!/usr/bin/env python3
"""Agent OS git pre-commit 门控:与宿主无关的最后防线。

即便 PreToolUse 钩子被绕过或宿主不支持钩子,提交前仍会对照锁定的 Mission IR
校验:只读 / 诊断任务下的提交会被拒绝(exit 1)。模式由 AGENT_OS_HOOK_MODE 控制,
off / monitor 不会阻断提交。任何内部错误一律放行,避免误伤正常提交。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# 各路径可用环境变量覆盖(便于测试与自定义布局)
AGENT_OS_DIR = Path(os.environ.get("AGENT_OS_HOME") or Path(__file__).resolve().parents[1])
RUNTIME = Path(os.environ.get("AGENT_OS_RUNTIME") or (AGENT_OS_DIR / "scripts" / "agent-runtime.py"))
DB_PATH = Path(os.environ.get("AGENT_OS_DB") or (AGENT_OS_DIR / "memory" / "index.db"))
POINTER = Path(os.environ.get("AGENT_OS_POINTER") or (AGENT_OS_DIR / "memory" / "active-intent.json"))


def main() -> int:
    mode = os.environ.get("AGENT_OS_HOOK_MODE", "enforce").lower()
    if mode == "off" or not POINTER.exists() or not RUNTIME.exists():
        return 0
    try:
        pointer = json.loads(POINTER.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    project = pointer.get("project")
    intent_id = pointer.get("intent_id")
    if not project or not intent_id:
        return 0

    cmd = [
        sys.executable,
        str(RUNTIME),
        "runtime-execution-gate",
        "--project",
        str(project),
        "--intent-id",
        str(intent_id),
        "--action-type",
        "commit",
        "--db",
        str(DB_PATH),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        gate = json.loads(completed.stdout).get("gate", {})
        decision = gate.get("decision", "allowed")
        reason = gate.get("reason", "")
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0  # 门控不可用,放行

    if decision == "blocked":
        mission = pointer.get("mutation_authorization", "?")
        msg = f"[Agent OS] 提交被拒绝:当前 Mission[{mission}] 为只读/诊断,不允许提交。{reason}"
        if mode == "monitor":
            print(msg + "(monitor 模式,仅提示不阻断)", file=sys.stderr)
            return 0
        print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
