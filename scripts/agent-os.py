#!/usr/bin/env python3
"""Product CLI wrapper for Agent OS."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "scripts" / "agent-runtime.py"
PROJECT_AGENTS_TEMPLATE = """# Project Agent Entry

This project uses Agent OS from `.agent-os/`.

This root `AGENTS.md` is the project bootstrap entry. Load it first, then delegate to `.agent-os/AGENTS.md`.

## Agent Display

Agent display name: Agent OS

Use this display name at the start of the first user-visible status paragraph and for major status/conclusion paragraphs so the user can see Agent OS is active.

Before starting any task:
1. Read `.agent-os/AGENTS.md`.
2. Follow `.agent-os/context/`, `.agent-os/workflows/`, `.agent-os/rules/`, `.agent-os/skills/`, `.agent-os/tools/`, and `.agent-os/memory/`.
3. Prefer project-local `.agent-os/skills/<skill>/SKILL.md` over global user-level skills when both exist.
4. Treat this repository root as the user project.
5. Keep project-specific decisions in `.agent-os/memory/projects/{project}.md`.
6. Save durable implementation plans, task breakdowns, decisions, reviews, and verification records under `docs/agent-os/`.
7. Before final response, decide whether project README/docs, `docs/agent-os/`, project memory, or Agent OS docs need updates; if not, state why.
8. Do not modify `.agent-os/AGENTS.md` unless the user explicitly asks to upgrade Agent OS itself.

Project-specific rules can be added below this line.
"""
GIT_EXCLUDE_START = "# Agent OS managed excludes"
GIT_EXCLUDE_END = "# End Agent OS managed excludes"
GIT_EXCLUDE_ENTRIES = (
    "AGENTS.md",
    ".agent-os/",
)
GITIGNORE_START = "# Agent OS managed ignores"
GITIGNORE_END = "# End Agent OS managed ignores"
EXCLUDE_NAMES = {
    ".git",
    ".idea",
    ".vscode",
    ".tmp",
    "vscode-plugin",
    "__pycache__",
    ".pytest_cache",
}
EXCLUDE_PATTERNS = (
    "memory/index.db",
    "memory/index.db-shm",
    "memory/index.db-wal",
    "memory/active-intent.json",
)

# 执行门控钩子(PEP)配置
CLAUDE_HOOK_MATCHER = "Write|Edit|MultiEdit|NotebookEdit|Bash"
CLAUDE_HOOK_MARKER = "pre_tool_use.py"  # 用于幂等识别已安装的钩子
PRECOMMIT_MARKER = "Agent OS managed pre-commit"

# 宿主(host)配置:不同宿主读取不同入口文件、支持不同强制能力
HOST_CHOICES = ("codex", "cursor", "claude")
# 强制等级:仅 Claude Code 提供工具级拦截钩子;codex/cursor 只能建议 + git 兜底
ENFORCEMENT_BY_HOST = {
    "claude": "enforced(pre-tool+git)",
    "codex": "advisory(AGENTS.md)+git",
    "cursor": "advisory(AGENTS.md)+git",
}
# Claude Code 原生入口 CLAUDE.md 的附加说明(点明钩子已生效)
CLAUDE_ENTRY_NOTE = (
    "\n> Claude Code:PreToolUse 与 git pre-commit 钩子已生效，"
    "只读/诊断任务下的写操作与提交会被强制拦截。\n"
)


def entry_filename_for_host(host: str) -> str:
    """返回宿主读取的项目根入口文件名。"""
    return "CLAUDE.md" if host == "claude" else "AGENTS.md"


def entry_template_for_host(host: str) -> str:
    """生成宿主对应的入口文件内容;Claude 使用原生 CLAUDE.md 并追加钩子说明。"""
    if host != "claude":
        return PROJECT_AGENTS_TEMPLATE
    text = PROJECT_AGENTS_TEMPLATE.replace(
        "This root `AGENTS.md` is the project bootstrap entry.",
        "This root `CLAUDE.md` is the project bootstrap entry.",
    )
    return text.replace("# Project Agent Entry\n", "# Project Agent Entry\n" + CLAUDE_ENTRY_NOTE, 1)


def managed_ignore_entries_for_host(host: str) -> Tuple[str, ...]:
    """按宿主返回需本地忽略的入口文件 + .agent-os/ 目录。"""
    return (entry_filename_for_host(host), ".agent-os/")


def write_host_marker(agent_os_dir: Path, host: str) -> None:
    """记录所选宿主与强制等级,供插件面板 / doctor 展示。"""
    marker = agent_os_dir / "host.json"
    marker.write_text(
        json.dumps(
            {"host": host, "enforcement": ENFORCEMENT_BY_HOST.get(host, "advisory(AGENTS.md)+git")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def should_skip(path: Path, target_agent_os: Optional[Path] = None) -> bool:
    if target_agent_os:
        try:
            path.resolve().relative_to(target_agent_os.resolve())
            return True
        except ValueError:
            pass
    rel = path.relative_to(ROOT).as_posix()
    if any(part in EXCLUDE_NAMES for part in path.relative_to(ROOT).parts):
        return True
    if rel in EXCLUDE_PATTERNS:
        return True
    if rel.endswith(".pyc") or rel.endswith(".lock"):
        return True
    return False


def git_dir_for(root: Path) -> Optional[Path]:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-dir"],
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    git_dir = Path(completed.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    return git_dir


def managed_ignore_target(root: Path) -> Tuple[Path, str, str]:
    git_dir = git_dir_for(root)
    if git_dir:
        return git_dir / "info" / "exclude", GIT_EXCLUDE_START, GIT_EXCLUDE_END
    return root / ".gitignore", GITIGNORE_START, GITIGNORE_END


def update_managed_ignore_file(root: Path, entries: Tuple[str, ...]) -> Tuple[bool, str]:
    ignore_path, start_marker, end_marker = managed_ignore_target(root)
    label = ".git/info/exclude" if ignore_path.name == "exclude" else ".gitignore"
    existing = ignore_path.read_text(encoding="utf-8") if ignore_path.exists() else ""
    block = "\n".join([start_marker, *entries, end_marker]) + "\n"
    pattern = re.compile(rf"(?ms)^\s*{re.escape(start_marker)}\n.*?^\s*{re.escape(end_marker)}\n?")
    if pattern.search(existing):
        updated = pattern.sub(block, existing)
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        if existing and not existing.endswith("\n\n"):
            existing += "\n"
        updated = existing + block
    if updated != existing:
        ignore_path.parent.mkdir(parents=True, exist_ok=True)
        ignore_path.write_text(updated, encoding="utf-8")
    return True, f"update {label} -> {ignore_path}"


def remove_managed_ignore_file(root: Path) -> Tuple[bool, str]:
    ignore_path, start_marker, end_marker = managed_ignore_target(root)
    label = ".git/info/exclude" if ignore_path.name == "exclude" else ".gitignore"
    if not ignore_path.exists():
        return True, f"{label} not found -> {ignore_path}"
    existing = ignore_path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(?ms)^\s*{re.escape(start_marker)}\n.*?^\s*{re.escape(end_marker)}\n?")
    updated = pattern.sub("", existing)
    if updated != existing:
        ignore_path.write_text(updated, encoding="utf-8")
        return True, f"remove {label} block -> {ignore_path}"
    return True, f"no Agent OS managed block found in {label} -> {ignore_path}"


def copy_agent_os(target_agent_os: Path, dry_run: bool = False) -> List[str]:
    actions: List[str] = []
    for source in ROOT.rglob("*"):
        if should_skip(source, target_agent_os):
            continue
        rel = source.relative_to(ROOT)
        destination = target_agent_os / rel
        if source.is_dir():
            if not dry_run:
                destination.mkdir(parents=True, exist_ok=True)
            continue
        actions.append(f"copy {rel.as_posix()} -> {destination}")
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    return actions


def install_claude_hook(target: Path, agent_os_dir: Path, dry_run: bool) -> str:
    """把 PreToolUse 钩子(PEP)合并进项目 .claude/settings.json,幂等且不覆盖已有配置。"""
    settings_path = target / ".claude" / "settings.json"
    hook_cmd = f'"{sys.executable}" "{agent_os_dir / "hooks" / "pre_tool_use.py"}"'
    data: Dict[str, Any] = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return f"skip .claude/settings.json(无法解析,请手动配置 PreToolUse 钩子)-> {settings_path}"
    hooks = data.setdefault("hooks", {})
    pre_tool_use = hooks.setdefault("PreToolUse", [])
    for entry in pre_tool_use:
        for hook in entry.get("hooks", []):
            if CLAUDE_HOOK_MARKER in str(hook.get("command", "")):
                return f"Claude PreToolUse 钩子已存在 -> {settings_path}"
    pre_tool_use.append(
        {
            "matcher": CLAUDE_HOOK_MATCHER,
            "hooks": [{"type": "command", "command": hook_cmd}],
        }
    )
    if not dry_run:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return f"install Claude PreToolUse 钩子 -> {settings_path}"


def remove_claude_hook(target: Path) -> str:
    """从 .claude/settings.json 移除 Agent OS 安装的 PreToolUse 钩子条目。"""
    settings_path = target / ".claude" / "settings.json"
    if not settings_path.exists():
        return f".claude/settings.json 不存在 -> {settings_path}"
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return f"skip .claude/settings.json(无法解析)-> {settings_path}"
    pre_tool_use = data.get("hooks", {}).get("PreToolUse")
    if not isinstance(pre_tool_use, list):
        return f"未发现 Agent OS PreToolUse 钩子 -> {settings_path}"
    kept = [
        entry
        for entry in pre_tool_use
        if not any(CLAUDE_HOOK_MARKER in str(h.get("command", "")) for h in entry.get("hooks", []))
    ]
    if len(kept) == len(pre_tool_use):
        return f"未发现 Agent OS PreToolUse 钩子 -> {settings_path}"
    data["hooks"]["PreToolUse"] = kept
    settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"remove Claude PreToolUse 钩子 -> {settings_path}"


def install_git_precommit(target: Path, agent_os_dir: Path, dry_run: bool) -> str:
    """安装 git pre-commit 钩子作为与宿主无关的最后防线;不覆盖已有的非 Agent OS 钩子。"""
    git_dir = git_dir_for(target)
    if git_dir is None:
        return "skip git pre-commit(非 git 仓库)"
    dest = git_dir / "hooks" / "pre-commit"
    if dest.exists():
        existing = dest.read_text(encoding="utf-8", errors="ignore")
        if PRECOMMIT_MARKER not in existing:
            return f"skip git pre-commit(已存在非 Agent OS 钩子,请手动整合)-> {dest}"
    if not dry_run:
        source = agent_os_dir / "hooks" / "pre-commit"
        if not source.exists():
            return f"skip git pre-commit(缺少钩子源文件)-> {source}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        try:
            dest.chmod(0o755)
        except OSError:
            pass
    return f"install git pre-commit 钩子 -> {dest}"


def remove_git_precommit(target: Path) -> str:
    """仅当 pre-commit 是 Agent OS 安装的时才删除。"""
    git_dir = git_dir_for(target)
    if git_dir is None:
        return "skip git pre-commit 清理(非 git 仓库)"
    dest = git_dir / "hooks" / "pre-commit"
    if not dest.exists():
        return f"git pre-commit 钩子不存在 -> {dest}"
    existing = dest.read_text(encoding="utf-8", errors="ignore")
    if PRECOMMIT_MARKER not in existing:
        return f"skip git pre-commit 清理(非 Agent OS 钩子)-> {dest}"
    dest.unlink()
    return f"remove git pre-commit 钩子 -> {dest}"


def cmd_install(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    agent_os_dir = target / ".agent-os"
    host = getattr(args, "host", "codex") or "codex"
    entry_name = entry_filename_for_host(host)
    root_entry = target / entry_name
    actions: List[str] = []
    actions.append(f"host = {host}({ENFORCEMENT_BY_HOST.get(host, 'advisory')})")
    if not target.exists():
        if args.dry_run:
            actions.append(f"create target directory {target}")
        else:
            target.mkdir(parents=True)
    if agent_os_dir.exists() and not args.force:
        print(f"Agent OS install target already exists: {agent_os_dir}", file=sys.stderr)
        print("Use --force to overwrite/update .agent-os.", file=sys.stderr)
        return 2
    actions.extend(copy_agent_os(agent_os_dir, dry_run=args.dry_run))
    actions.append(f"write root {entry_name} -> {root_entry}")
    if not args.dry_run:
        if root_entry.exists() and not args.force:
            print(f"Root {entry_name} already exists: {root_entry}", file=sys.stderr)
            print("Use --force to overwrite it.", file=sys.stderr)
            return 2
        root_entry.write_text(entry_template_for_host(host), encoding="utf-8")
    memory_dir = agent_os_dir / "memory"
    actions.append(f"initialize memory directory -> {memory_dir}")
    if not args.dry_run:
        memory_dir.mkdir(parents=True, exist_ok=True)
        write_host_marker(agent_os_dir, host)
        _, action = update_managed_ignore_file(target, managed_ignore_entries_for_host(host))
        actions.append(action)
        subprocess.run(
            [sys.executable, str(agent_os_dir / "scripts" / "agent-runtime.py"), "runtime-migrate", "--db", str(agent_os_dir / "memory" / "index.db")],
            cwd=target,
            check=True,
            text=True,
            capture_output=True,
        )
    elif target.exists():
        actions.append("skip local ignore update (dry run)")
    # 安装执行门控钩子(PEP):仅 Claude Code 支持工具级拦截;git pre-commit 对所有宿主兜底
    if host == "claude":
        actions.append(install_claude_hook(target, agent_os_dir, args.dry_run))
    else:
        actions.append(
            f"skip Claude PreToolUse 钩子(host={host} 无工具级拦截,使用 {entry_name} 建议 + git 兜底)"
        )
    actions.append(install_git_precommit(target, agent_os_dir, args.dry_run))
    print("\n".join(actions))
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    agent_os_dir = target / ".agent-os"
    actions: List[str] = []
    if not target.exists():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2
    if args.dry_run:
        actions.append("skip local ignore cleanup (dry run)")
    else:
        _, action = remove_managed_ignore_file(target)
        actions.append(action)
        # 一并清理执行门控钩子
        actions.append(remove_claude_hook(target))
        actions.append(remove_git_precommit(target))
    if args.remove_root_agents:
        # 宿主不同入口文件名不同(AGENTS.md / CLAUDE.md),两者都清理
        for entry_name in ("AGENTS.md", "CLAUDE.md"):
            root_entry = target / entry_name
            actions.append(f"remove root {entry_name} -> {root_entry}")
            if not args.dry_run and root_entry.exists():
                root_entry.unlink()
    if agent_os_dir.exists():
        actions.append(f"remove Agent OS directory -> {agent_os_dir}")
        if not args.dry_run:
            shutil.rmtree(agent_os_dir)
    else:
        actions.append(f"Agent OS directory not found -> {agent_os_dir}")
    print("\n".join(actions))
    return 0


def cmd_ignore(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    actions: List[str] = []
    if not target.exists():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2
    _, action = update_managed_ignore_file(target, tuple(args.entries))
    actions.append(action)
    print("\n".join(actions))
    return 0


RUNTIME_ALIASES = {
    "doctor",
    "version",
    "migrate",
    "dashboard",
    "quality-trends",
    "policy-packs",
    "security-check",
    "distribution",
    "vscode-protocol",
    "team-workspace",
    "release-check",
}


def forward_runtime(command: str, rest: List[str]) -> int:
    runtime_command = f"runtime-{command}" if command in RUNTIME_ALIASES else command
    completed = subprocess.run([sys.executable, str(RUNTIME), runtime_command, *rest], cwd=ROOT)
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent OS product CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="Install Agent OS into a user project")
    install.add_argument("--target", type=Path, required=True)
    install.add_argument(
        "--host",
        choices=HOST_CHOICES,
        default="codex",
        help="目标宿主:codex/cursor 生成 AGENTS.md(建议+git 兜底);claude 生成 CLAUDE.md + PreToolUse 强制钩子",
    )
    install.add_argument("--force", action="store_true")
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)

    uninstall = subparsers.add_parser("uninstall", help="Uninstall Agent OS from a user project")
    uninstall.add_argument("--target", type=Path, required=True)
    uninstall.add_argument("--remove-root-agents", action="store_true")
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall)

    ignore = subparsers.add_parser("ignore", help="Configure local ignores for Agent OS files")
    ignore.add_argument("--target", type=Path, required=True)
    ignore.add_argument(
        "--entries",
        nargs="+",
        default=list(GIT_EXCLUDE_ENTRIES),
        help="Paths to ignore locally",
    )
    ignore.add_argument("--cleanup-gitignore", action="store_true")
    ignore.set_defaults(func=cmd_ignore)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in RUNTIME_ALIASES:
        return forward_runtime(argv[0], argv[1:])
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
