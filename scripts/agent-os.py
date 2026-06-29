#!/usr/bin/env python3
"""Product CLI wrapper for Agent OS."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


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
EXCLUDE_NAMES = {
    ".git",
    ".idea",
    ".vscode",
    ".tmp",
    "__pycache__",
    ".pytest_cache",
}
EXCLUDE_PATTERNS = (
    "memory/index.db",
    "memory/index.db-shm",
    "memory/index.db-wal",
)


def should_skip(path: Path, target_agent_os: Path | None = None) -> bool:
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


def copy_agent_os(target_agent_os: Path, dry_run: bool = False) -> list[str]:
    actions: list[str] = []
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
    actions: list[str] = []
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
        subprocess.run(
            [sys.executable, str(agent_os_dir / "scripts" / "agent-runtime.py"), "runtime-migrate", "--db", str(agent_os_dir / "memory" / "index.db")],
            cwd=target,
            check=True,
            text=True,
            capture_output=True,
        )
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


def forward_runtime(command: str, rest: list[str]) -> int:
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

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in RUNTIME_ALIASES:
        return forward_runtime(argv[0], argv[1:])
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
