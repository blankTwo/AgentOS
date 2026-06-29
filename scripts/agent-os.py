#!/usr/bin/env python3
"""Product CLI wrapper for Agent OS."""

from __future__ import annotations

import argparse
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


def cmd_install(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    agent_os_dir = target / ".agent-os"
    root_agents = target / "AGENTS.md"
    actions: List[str] = []
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
    actions.append(f"write root AGENTS.md -> {root_agents}")
    if not args.dry_run:
        if root_agents.exists() and not args.force:
            print(f"Root AGENTS.md already exists: {root_agents}", file=sys.stderr)
            print("Use --force to overwrite it.", file=sys.stderr)
            return 2
        root_agents.write_text(PROJECT_AGENTS_TEMPLATE, encoding="utf-8")
    memory_dir = agent_os_dir / "memory"
    actions.append(f"initialize memory directory -> {memory_dir}")
    if not args.dry_run:
        memory_dir.mkdir(parents=True, exist_ok=True)
        _, action = update_managed_ignore_file(target, GIT_EXCLUDE_ENTRIES)
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
    print("\n".join(actions))
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    target = args.target.resolve()
    agent_os_dir = target / ".agent-os"
    root_agents = target / "AGENTS.md"
    actions: List[str] = []
    if not target.exists():
        print(f"Target directory does not exist: {target}", file=sys.stderr)
        return 2
    if args.dry_run:
        actions.append("skip local ignore cleanup (dry run)")
    else:
        _, action = remove_managed_ignore_file(target)
        actions.append(action)
    if args.remove_root_agents:
        actions.append(f"remove root AGENTS.md -> {root_agents}")
        if not args.dry_run and root_agents.exists():
            root_agents.unlink()
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
