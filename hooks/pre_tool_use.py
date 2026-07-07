#!/usr/bin/env python3
"""Agent OS PreToolUse 钩子:执行门控的策略执行点(PEP)。

Claude Code 在调用 Write / Edit / Bash 等工具前会执行本钩子。钩子读取与
.agent-os 库同目录的 active-intent.json,拿到当前锁定的 project 与 intent_id,
再调用 `runtime-execution-gate` 对照 Locked Mission IR 做硬门校验:

  - allowed           -> 放行(不输出,交回 Claude Code 正常权限流程)
  - blocked           -> deny(如"排查/只读"任务里试图写文件)
  - requires-approval -> ask(强制用户确认)

模式由环境变量 AGENT_OS_HOOK_MODE 控制:enforce(默认)/ monitor / off。
任何内部错误一律放行(fail-open),避免锁死编辑器;git pre-commit 是最后防线。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# 钩子位于 .agent-os/hooks/,上一级即 .agent-os 根;各路径可用环境变量覆盖(便于测试与自定义布局)
AGENT_OS_DIR = Path(os.environ.get("AGENT_OS_HOME") or Path(__file__).resolve().parents[1])
RUNTIME = Path(os.environ.get("AGENT_OS_RUNTIME") or (AGENT_OS_DIR / "scripts" / "agent-runtime.py"))
DB_PATH = Path(os.environ.get("AGENT_OS_DB") or (AGENT_OS_DIR / "memory" / "index.db"))
POINTER = Path(os.environ.get("AGENT_OS_POINTER") or (AGENT_OS_DIR / "memory" / "active-intent.json"))

# 需要过门的工具 -> execution-gate 附加参数;返回 None 表示该工具只读、无需过门
def gate_args_for_tool(tool_name: str, tool_input: dict) -> list[str] | None:
    if tool_name in ("Write", "Edit", "MultiEdit"):
        return ["--action-type", "write", "--target-paths", str(tool_input.get("file_path", ""))]
    if tool_name == "NotebookEdit":
        return ["--action-type", "write", "--target-paths", str(tool_input.get("notebook_path", ""))]
    if tool_name == "Bash":
        # 不指定 action-type,交由运行时按命令自动判定 shell / git
        return ["--command", str(tool_input.get("command", ""))]
    return None


def emit(decision: str, reason: str) -> None:
    """输出 Claude Code PreToolUse 决策;allowed 情况下不调用本函数。"""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def main() -> int:
    mode = os.environ.get("AGENT_OS_HOOK_MODE", "enforce").lower()
    if mode == "off":
        return 0

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, OSError):
        return 0  # 读不到输入,放行

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    gate_args = gate_args_for_tool(tool_name, tool_input)
    if gate_args is None:
        return 0  # 只读 / 非目标工具,放行

    # 没有活动意图或运行时缺失,说明 Agent OS 未介入本会话,放行
    if not POINTER.exists() or not RUNTIME.exists():
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
        "--db",
        str(DB_PATH),
        *gate_args,
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        gate = json.loads(completed.stdout).get("gate", {})
        decision = gate.get("decision", "allowed")
        reason = gate.get("reason", "")
    except (subprocess.SubprocessError, ValueError, OSError):
        return 0  # 门控不可用,fail-open

    mission = pointer.get("mutation_authorization", "?")
    detail = f"Agent OS Mission[{mission}] 门控:{tool_name} -> {decision}. {reason}".strip()

    if mode == "monitor":
        if decision != "allowed":
            print(detail, file=sys.stderr)
        return 0

    # enforce
    if decision == "blocked":
        emit("deny", detail)
    elif decision == "requires-approval":
        emit("ask", detail)
    # allowed:不输出,交回正常权限流程
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
