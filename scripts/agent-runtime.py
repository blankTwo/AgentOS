#!/usr/bin/env python3
"""Agent Runtime controllers for Agent OS."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import html
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_store import (
    DEFAULT_DB,
    DEFAULT_SCHEMA,
    ROOT,
    add_common_args,
    build_safe_fts_query,
    connect,
    ensure_initialized,
    normalize_csv,
    normalize_project_slug,
    print_json,
    row_to_dict,
    workspace_relative,
)


RUNTIME_KINDS = (
    "goal",
    "task",
    "observation",
    "capability",
    "policy",
    "verification",
    "tool",
    "skill",
    "model",
    "subagent",
    "adapter",
    "metrics",
    "trace",
    "recovery",
    "reflection",
    "improvement",
    "event",
)

EVENT_TYPES = (
    "UserRequest",
    "ContextReady",
    "GoalCreated",
    "RunCreated",
    "TaskPlanned",
    "TaskStarted",
    "TaskCompleted",
    "GoalStateChanged",
    "TaskStateChanged",
    "RunStateChanged",
    "VerificationPlanned",
    "VerificationPassed",
    "VerificationFailed",
    "DocumentationChecked",
    "MemoryUpdated",
    "KernelStep",
    "Blocked",
    "Recovered",
    "RecoveryPlanned",
    "RecoveryCheckpointCreated",
    "RecoveryMarked",
    "SkillValidated",
    "ModelRunRecorded",
    "SubAgentRunRecorded",
    "AdapterRegistered",
    "MetricsRecorded",
    "TraceExported",
)

MODEL_PROVIDERS = ("openai", "anthropic", "google", "qwen", "deepseek", "local", "mock", "custom")
SUBAGENT_ROLES = ("planner", "executor", "reviewer", "verifier", "memory-recorder")
HOST_TYPES = ("codex", "claude", "cursor", "vscode", "cli", "mcp", "custom")
HOST_CAPABILITY_PROTOCOL = {
    "codex": {
        "shell",
        "git",
        "runtime-cli",
        "skills",
        "memory",
        "browser",
        "model-runtime",
        "tool-runtime",
        "subagent-runtime",
    },
    "claude": {
        "shell",
        "git",
        "runtime-cli",
        "skills",
        "memory",
        "tool-runtime",
        "subagent-runtime",
    },
    "cursor": {
        "shell",
        "git",
        "runtime-cli",
        "inject-agent-os",
        "status-panel",
        "doctor",
        "dashboard",
        "report",
    },
    "vscode": {
        "install",
        "inject-agent-os",
        "status-panel",
        "doctor",
        "dashboard",
        "report",
        "runtime-cli",
    },
    "cli": {
        "shell",
        "git",
        "runtime-cli",
        "doctor",
        "dashboard",
        "report",
        "security-check",
        "policy-packs",
    },
    "mcp": {
        "tool-runtime",
        "api",
        "memory",
        "context",
        "report",
    },
    "custom": set(),
}
DOCTOR_CHECKS = ("directories", "agents", "rules", "skills", "memory", "runtime")
CURRENT_SCHEMA_VERSION = "15"
SECRET_PATTERNS = {
    "generic_secret": re.compile(r"(?i)\b(secret|token|api[_-]?key|password)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{16,})"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
HIGH_ENTROPY_VALUE_RE = re.compile(r"['\"]?([A-Za-z0-9+/=_\-]{32,})['\"]?")
MODEL_PROVIDER_ENV_VARS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "qwen": ("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
    "deepseek": ("DEEPSEEK_API_KEY",),
}
SECRET_ENV_NAME_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password|credential)")
SECURITY_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".tmp", "node_modules", "memory", "sessions", "logs", "temp"}
DANGEROUS_COMMAND_PATTERNS = (
    (re.compile(r"\bRemove-Item\b.*\s-Recurse\b", re.IGNORECASE), "recursive-delete"),
    (re.compile(r"\brm\s+-rf\b", re.IGNORECASE), "recursive-delete"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE), "destructive-git-reset"),
    (re.compile(r"\bgit\s+clean\s+-fd", re.IGNORECASE), "destructive-git-clean"),
    (re.compile(r"\b(drop|truncate)\s+table\b", re.IGNORECASE), "destructive-database"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+publish\b", re.IGNORECASE), "release-publish"),
)

CONTAINER_PROJECT_NAMES = {".agent-os", ".config", ".meta", "workspace"}

TASK_LAYER_KEYWORDS = {
    "UI": ("ui", "page", "component", "style", "layout", "interaction", "responsive", "tailwind", "react", "vue"),
    "API": ("api", "auth", "endpoint", "request", "response", "route", "controller"),
    "Data": ("data", "database", "schema", "migration", "table", "query", "cache", "transaction"),
    "Integration": ("integration", "linkage", "login", "payment", "webhook", "sdk", "end-to-end", "e2e"),
    "Runtime": ("runtime", "script", "build", "deploy", "dependency", "environment", "agent", "agent os"),
    "Test": ("test", "regression", "unittest", "pytest", "jest"),
    "Bugfix": ("bug", "fix", "error", "exception", "failure", "broken", "regression"),
    "Refactor": ("refactor", "split", "restructure", "maintainability", "responsibility", "reuse"),
}

SKILL_BY_LAYER = {
    "UI": ("feature-ui", "ui-refine"),
    "API": ("api-change",),
    "Data": ("api-change", "bugfix", "refactor"),
    "Integration": ("api-change", "bugfix"),
    "Runtime": ("bugfix", "refactor"),
    "Test": ("write-tests",),
    "Bugfix": ("bugfix",),
    "Refactor": ("refactor",),
}

SAFE_VERIFICATION_PREFIXES = (
    "python -m py_compile ",
    "python -m unittest",
    "python -m pytest",
    "python scripts\\agent-runtime.py --help",
    "python scripts/agent-runtime.py --help",
    "python scripts\\memory-tools.py --help",
    "python scripts/memory-tools.py --help",
    "git diff --check",
    "rg ",
)


def require_arg(args: argparse.Namespace, name: str) -> Any:
    value = getattr(args, name)
    if value is None or value == "":
        raise SystemExit(f"Expected --{name.replace('_', '-')} for runtime-record {args.kind}")
    return value


def parse_runtime_links(values: list[str] | None) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    if not values:
        return links
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid capability link, expected relation=target: {value}")
        relation, target = value.split("=", 1)
        relation = relation.strip()
        target = target.strip()
        if not relation or not target:
            raise SystemExit(f"Invalid capability link, expected relation=target: {value}")
        links.append((relation, target))
    return links


def agent_workspace_root() -> Path:
    return ROOT.parent if ROOT.name == ".agent-os" else ROOT


def split_terms(values: list[str] | None, fallback: str | None = None) -> list[str]:
    raw = " ".join(values or [])
    if fallback:
        raw = f"{raw} {fallback}"
    terms = re.findall(r"[\w\u4e00-\u9fff]+", raw.lower(), flags=re.UNICODE)
    return list(dict.fromkeys(term for term in terms if len(term) >= 2))


def compact_list(values: list[str], limit: int = 8) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = f" (+{len(values) - limit} more)" if len(values) > limit else ""
    return "; ".join(shown) + suffix


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_project_slug(project: str | None = None) -> tuple[str, str]:
    if project:
        return normalize_project_slug(project), "provided --project"
    base = agent_workspace_root()
    if base.name not in CONTAINER_PROJECT_NAMES:
        return normalize_project_slug(base.name), f"workspace directory: {base.name}"
    package_json = base / "package.json"
    package_name = load_json_file(package_json).get("name")
    if package_name:
        return normalize_project_slug(str(package_name)), "package.json name"
    return "unknown-project", "fallback unknown-project"


def detect_stack(files: list[str] | None = None) -> tuple[str, str, str]:
    base = agent_workspace_root()
    candidates = [Path(value) for value in files or []]
    suffixes = {path.suffix.lower() for path in candidates}
    package = load_json_file(base / "package.json")
    deps = " ".join((package.get("dependencies") or {}).keys())
    dev_deps = " ".join((package.get("devDependencies") or {}).keys())
    dep_text = f"{deps} {dev_deps}".lower()
    signals: list[str] = []
    stacks: list[str] = []

    if suffixes.intersection({".tsx", ".jsx"}) or "react" in dep_text:
        stacks.append("React")
        signals.append("React TSX/JSX or dependency")
    if any((base / name).exists() for name in ("vite.config.ts", "next.config.js", "next.config.ts")):
        stacks.append("Frontend Node")
        signals.append("frontend build config")
    if "express" in dep_text or "koa" in dep_text or "nest" in dep_text:
        stacks.append("Node")
        signals.append("Node server dependency")
    if (base / "go.mod").exists():
        stacks.append("Go")
        signals.append("go.mod")
    if (base / "Cargo.toml").exists():
        stacks.append("Rust")
        signals.append("Cargo.toml")
    if (base / "pyproject.toml").exists() or (base / "requirements.txt").exists() or suffixes == {".py"}:
        stacks.append("Python")
        signals.append("Python project or files")
    if (base / "pom.xml").exists() or (base / "build.gradle").exists():
        stacks.append("Java")
        signals.append("Java build file")
    if any((base / name).exists() for name in ("app.config.ts", "project.config.json")) or "taro" in dep_text:
        stacks.append("Taro/Mini Program")
        signals.append("Taro/Mini Program config")

    if not stacks:
        return "Unknown", "low", "no strong stack signal"
    confidence = "high" if signals else "low"
    if len(stacks) > 1:
        confidence = "medium"
    return ", ".join(dict.fromkeys(stacks)), confidence, "; ".join(signals)


def detect_task_layers(request: str, files: list[str] | None = None) -> list[str]:
    haystack = request.lower()
    file_values = files or []
    suffixes = {Path(value).suffix.lower() for value in file_values}
    paths = " ".join(value.lower().replace("\\", "/") for value in file_values)
    layers: list[str] = []

    for layer, keywords in TASK_LAYER_KEYWORDS.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            layers.append(layer)

    if suffixes.intersection({".tsx", ".jsx", ".vue", ".svelte", ".css"}):
        layers.append("UI")
    if any(token in paths for token in ("/api/", "/routes/", "/controllers/", "/server/", "/backend/")):
        layers.append("API")
    if suffixes.intersection({".sql"}) or any(token in paths for token in ("migration", "schema", "model", "db/")):
        layers.append("Data")
    if any(token in paths for token in ("scripts/agent-runtime.py", "memory/schema.sql", "rules/", "skills/", "agents.md")):
        layers.append("Runtime")

    return list(dict.fromkeys(layers)) or ["Runtime"]


def detect_intent(request: str) -> str:
    lower = request.lower()
    if any(token in lower for token in ("fix", "bug", "error", "broken", "failure", "regression")):
        return "bugfix"
    if any(token in lower for token in ("implement", "add", "create", "connect", "support", "complete")):
        return "feature"
    if any(token in lower for token in ("refactor", "split", "restructure", "optimize", "improve")):
        return "refactor"
    if any(token in lower for token in ("test", "verify", "coverage")):
        return "test"
    if any(token in lower for token in ("review", "inspect", "audit")):
        return "review"
    return "task"


def detect_scale(request: str, layers: list[str], files: list[str] | None = None) -> str:
    lower = request.lower()
    file_count = len(files or [])
    layer_count = len(set(layers))
    critical = any(
        token in lower
        for token in (
            "architecture",
            "database",
            "migration",
            "permission",
            "payment",
            "security",
            "production",
            "release",
            "agent os",
            "full standard",
        )
    )
    if critical or "Runtime" in layers and any(token in lower for token in ("agent", "runtime", "complete")):
        return "L4"
    if layer_count >= 2 or "Integration" in layers:
        return "L3"
    if file_count > 1 or any(token in lower for token in ("module", "multiple files", "flow")):
        return "L2"
    return "L1"


def git_worktree_dirty() -> bool:
    try:
        completed = subprocess.run(
            "git status --short",
            cwd=ROOT,
            shell=True,
            text=True,
            capture_output=True,
            timeout=10,
        )
    except subprocess.SubprocessError:
        return False
    return bool(completed.stdout.strip())


def test_files_available() -> bool:
    test_roots = [ROOT / "tests", ROOT / "test"]
    if any(root.exists() and any(root.rglob("test*.py")) for root in test_roots):
        return True
    package = load_json_file(ROOT / "package.json")
    scripts = package.get("scripts") or {}
    return any("test" in key for key in scripts)


def workspace_risk_signals(files: list[str] | None = None) -> list[str]:
    signals: list[str] = []
    values = files or []
    normalized = [value.replace("\\", "/").lower() for value in values]
    if git_worktree_dirty():
        signals.append("dirty-worktree")
    if len(values) >= 5:
        signals.append("large-change")
    if any(value.endswith(("package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "requirements.txt", "pyproject.toml")) for value in normalized):
        signals.append("dependency-upgrade")
    if any("migration" in value or value.endswith(".sql") for value in normalized):
        signals.append("migration")
    if any(value.startswith("docs/agent-os/") for value in normalized):
        signals.append("docs-agent-os")
    if test_files_available():
        signals.append("tests-available")
    else:
        signals.append("tests-missing")
    return list(dict.fromkeys(signals))


def docs_path_bucket(path: str) -> str | None:
    normalized = path.replace("\\", "/").lower()
    if not normalized.startswith("docs/agent-os/"):
        return None
    if "/plans/" in normalized:
        return "plans"
    if "/tasks/" in normalized:
        return "tasks"
    if "/decisions/" in normalized:
        return "decisions"
    if "/reviews/" in normalized:
        return "reviews"
    if "/verification/" in normalized:
        return "verification"
    return "docs"


def docs_impact_for_files(files: list[str] | None) -> dict[str, Any]:
    impacted = {"plans": False, "tasks": False, "decisions": False, "reviews": False, "verification": False}
    reasons: list[str] = []
    for value in files or []:
        bucket = docs_path_bucket(value)
        if bucket and bucket in impacted:
            impacted[bucket] = True
            reasons.append(f"changed {bucket} docs file: {value}")
    return {"impacted": impacted, "reasons": list(dict.fromkeys(reasons))}


def docs_freshness_for_request(request: str, files: list[str] | None, workspace: dict[str, Any]) -> dict[str, Any]:
    docs_impact = docs_impact_for_files(files)
    docs_exists = workspace["docs"]["exists"]
    normalized = [value.replace("\\", "/").lower() for value in files or []]
    request_lower = request.lower()
    docs_related_change = (
        any(value.startswith("docs/agent-os/") for value in normalized)
        or any(token in request_lower for token in ("docs", "documentation", "readme", "contract", "usage", "command", "guide", "spec", "path"))
    )
    stale_docs = docs_exists and docs_related_change and not any(docs_impact["impacted"].values())
    missing_docs = docs_related_change and not docs_exists
    must_update = stale_docs or missing_docs or bool(docs_impact["reasons"])
    return {
        "docs_exists": docs_exists,
        "docs_related_change": docs_related_change,
        "missing_docs": missing_docs,
        "stale_docs": stale_docs,
        "must_update": must_update,
        "impact": docs_impact,
        "suggestion": (
            "Update docs/agent-os with the changed behavior, commands, or contract."
            if must_update
            else "No docs freshness issue detected."
        ),
    }


def knowledge_conflict_for_capability(
    *,
    project: str,
    capability_name: str,
    layer_hits: dict[str, list[str]],
    linkage: dict[str, Any],
    memory_hits: list[str],
    docs_freshness: dict[str, Any],
    workspace: dict[str, Any],
) -> dict[str, Any]:
    code_present = any(layer_hits[layer] for layer in ("frontend", "api", "backend", "data", "verification"))
    memory_present = bool(memory_hits)
    docs_present = workspace["docs"]["exists"]
    docs_mention = bool(docs_freshness["impact"]["reasons"])
    conflict_sources: list[str] = []
    reasons: list[str] = []
    if memory_present and not code_present:
        conflict_sources.append("memory-code")
        reasons.append("Memory has hits but code evidence is absent.")
    if memory_present and docs_present and docs_freshness["missing_docs"]:
        conflict_sources.append("memory-docs")
        reasons.append("Memory has hits but docs are missing for docs-related work.")
    if docs_present and code_present and docs_freshness["stale_docs"]:
        conflict_sources.append("docs-code")
        reasons.append("Docs are present but appear stale relative to the current request/files.")
    if layer_hits["api"] and layer_hits["backend"] and not linkage["api_backend_overlap"]:
        conflict_sources.append("code-runtime")
        reasons.append("API/backend chain exists but routes do not overlap, so the chain is broken.")
    conflict = len(conflict_sources) >= 2 or ("code-runtime" in conflict_sources and (memory_present or docs_mention))
    evidence = {
        "memory_hits": len(memory_hits),
        "code_present": code_present,
        "docs_present": docs_present,
        "docs_mention": docs_mention,
        "linkage": linkage["evidence"],
    }
    return {
        "project": project,
        "capability_name": capability_name,
        "conflict": conflict,
        "conflict_sources": list(dict.fromkeys(conflict_sources)),
        "reasons": list(dict.fromkeys(reasons)),
        "evidence": evidence,
        "suggestion": (
            "Re-read code, docs, and memory, then re-verify the live path before trusting prior knowledge."
            if conflict
            else "No obvious knowledge conflict detected."
        ),
    }


def cmd_runtime_check_docs(args: argparse.Namespace) -> None:
    workspace = workspace_snapshot(args.project)
    docs_freshness = docs_freshness_for_request(args.request or args.project, args.files, workspace)
    print_json({"ok": True, "project": args.project, "workspace": workspace, "docs_freshness": docs_freshness})


def cmd_runtime_check_knowledge(args: argparse.Namespace) -> None:
    workspace = workspace_snapshot(args.project)
    query_files = args.files or []
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        memory_hits = search_memory_for_capability(conn, args.project, args.request or args.capability or args.project, args.limit)
        runtime_hits = conn.execute(
            """
            SELECT summary
            FROM agent_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
    layer_hits = {"frontend": [], "api": [], "backend": [], "data": [], "verification": []}
    if query_files:
        for value in query_files:
            lower = value.replace("\\", "/").lower()
            if any(token in lower for token in ("src/", "frontend", ".tsx", ".jsx", ".vue", ".svelte")):
                layer_hits["frontend"].append(value)
            if any(token in lower for token in ("api", "route", "controller")):
                layer_hits["api"].append(value)
            if any(token in lower for token in ("server", "backend", "service")):
                layer_hits["backend"].append(value)
            if any(token in lower for token in ("db", "schema", "migration", ".sql")):
                layer_hits["data"].append(value)
            if any(token in lower for token in ("test", "spec")):
                layer_hits["verification"].append(value)
    linkage = capability_linkage(layer_hits, {key: set() for key in layer_hits})
    docs_freshness = docs_freshness_for_request(args.request or args.capability or args.project, query_files, workspace)
    conflict = knowledge_conflict_from_state(
        project=args.project,
        name=args.capability or args.request or args.project,
        memory_hits=memory_hits,
        docs_freshness=docs_freshness,
        workspace=workspace,
        code_evidence=layer_hits["frontend"] + layer_hits["api"] + layer_hits["backend"] + layer_hits["data"],
        runtime_evidence=[row["summary"] for row in runtime_hits],
    )
    print_json({"ok": True, "project": args.project, "workspace": workspace, "docs_freshness": docs_freshness, "knowledge_conflict": conflict, "memory_hits": memory_hits, "layer_hits": layer_hits, "linkage": linkage})


def knowledge_conflict_from_state(
    *,
    project: str,
    name: str,
    memory_hits: list[str],
    docs_freshness: dict[str, Any],
    workspace: dict[str, Any],
    code_evidence: list[str],
    runtime_evidence: list[str],
) -> dict[str, Any]:
    memory_present = bool(memory_hits)
    docs_present = workspace["docs"]["exists"]
    code_present = bool(code_evidence)
    runtime_present = bool(runtime_evidence)
    conflict_sources: list[str] = []
    reasons: list[str] = []
    if memory_present and not code_present:
        conflict_sources.append("memory-code")
        reasons.append("Memory mentions the capability but current code evidence is missing.")
    if docs_present and docs_freshness["stale_docs"]:
        conflict_sources.append("docs-code")
        reasons.append("Docs are present but stale relative to the current request.")
    if docs_freshness["missing_docs"] and (memory_present or code_present):
        conflict_sources.append("memory-docs")
        reasons.append("Memory or code exists but docs are missing for docs-related work.")
    if runtime_present and not code_present and memory_present:
        conflict_sources.append("runtime-code")
        reasons.append("Runtime evidence disagrees with memory without matching code evidence.")
    conflict = len(conflict_sources) >= 2 or (memory_present and docs_present and docs_freshness["missing_docs"] and not code_present)
    return {
        "project": project,
        "name": name,
        "conflict": conflict,
        "conflict_sources": list(dict.fromkeys(conflict_sources)),
        "reasons": list(dict.fromkeys(reasons)),
        "evidence": {
            "memory_hits": len(memory_hits),
            "code_evidence": len(code_evidence),
            "runtime_evidence": len(runtime_evidence),
            "docs_exists": docs_present,
            "stale_docs": docs_freshness["stale_docs"],
            "missing_docs": docs_freshness["missing_docs"],
        },
        "suggestion": (
            "Re-read memory, docs, code, and runtime evidence, then re-verify the live capability chain."
            if conflict
            else "No obvious knowledge conflict detected."
        ),
    }


def workspace_snapshot(project: str | None = None) -> dict[str, Any]:
    base = agent_workspace_root()
    project_slug, project_evidence = detect_project_slug(project)
    git_status = ""
    git_branch = ""
    try:
        status = subprocess.run(
            "git status --short",
            cwd=base,
            shell=True,
            text=True,
            capture_output=True,
            timeout=10,
        )
        git_status = status.stdout.strip()
        branch = subprocess.run(
            "git branch --show-current",
            cwd=base,
            shell=True,
            text=True,
            capture_output=True,
            timeout=10,
        )
        git_branch = branch.stdout.strip()
    except subprocess.SubprocessError:
        pass

    docs_root = base / "docs" / "agent-os"
    docs = {
        "exists": docs_root.exists(),
        "plans": len(list((docs_root / "plans").glob("*"))) if (docs_root / "plans").exists() else 0,
        "tasks": len(list((docs_root / "tasks").glob("*"))) if (docs_root / "tasks").exists() else 0,
        "decisions": len(list((docs_root / "decisions").glob("*"))) if (docs_root / "decisions").exists() else 0,
        "reviews": len(list((docs_root / "reviews").glob("*"))) if (docs_root / "reviews").exists() else 0,
        "verification": len(list((docs_root / "verification").glob("*"))) if (docs_root / "verification").exists() else 0,
    }

    file_stats = {
        "files": 0,
        "directories": 0,
        "tests": 0,
        "docs": 0,
    }
    for path in base.rglob("*"):
        if should_skip_scan_path(path):
            continue
        if path.is_file():
            file_stats["files"] += 1
            if path.suffix.lower() in {".md", ".markdown"}:
                file_stats["docs"] += 1
            if "test" in path.name.lower():
                file_stats["tests"] += 1
        elif path.is_dir():
            file_stats["directories"] += 1

    runtime_counts = {}
    with connect(DEFAULT_DB) as conn:
        ensure_initialized(conn, DEFAULT_SCHEMA)
        runtime_counts = {
            "goals": conn.execute("SELECT COUNT(*) AS count FROM agent_goals WHERE project = ?", (project_slug,)).fetchone()["count"],
            "tasks": conn.execute("SELECT COUNT(*) AS count FROM agent_tasks WHERE project = ?", (project_slug,)).fetchone()["count"],
            "events": conn.execute("SELECT COUNT(*) AS count FROM agent_events WHERE project = ?", (project_slug,)).fetchone()["count"],
            "verifications": conn.execute("SELECT COUNT(*) AS count FROM verification_runs WHERE project = ?", (project_slug,)).fetchone()["count"],
        }

    return {
        "project": project_slug,
        "project_evidence": project_evidence,
        "root": str(base),
        "git": {
            "branch": git_branch or None,
            "dirty": bool(git_status),
            "status": git_status.splitlines()[:20],
        },
        "docs": docs,
        "files": file_stats,
        "runtime": runtime_counts,
    }


def context_for_request(project: str | None, request: str, files: list[str] | None) -> dict[str, Any]:
    project_slug, project_evidence = detect_project_slug(project)
    stack, stack_confidence, stack_evidence = detect_stack(files)
    layers = detect_task_layers(request, files)
    scale = detect_scale(request, layers, files)
    intent = detect_intent(request)
    evidence = (
        f"project={project_evidence}; stack={stack_evidence}; "
        f"layers={','.join(layers)}; risk_signals={','.join(workspace_risk_signals(files))}; "
        f"files={','.join(files or []) or 'none'}"
    )
    return {
        "project": project_slug,
        "request": request,
        "stack": stack,
        "stack_confidence": stack_confidence,
        "task_layers": layers,
        "scale": scale,
        "intent": intent,
        "files": files or [],
        "evidence": evidence,
    }


def record_runtime_context(conn, context: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO runtime_contexts(
            project, request, stack, stack_confidence, task_layers,
            scale, intent, files, evidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context["project"],
            context["request"],
            context["stack"],
            context["stack_confidence"],
            normalize_csv(context["task_layers"]),
            context["scale"],
            context["intent"],
            normalize_csv(context["files"]),
            context["evidence"],
        ),
    )
    return cur.lastrowid


def record_event(
    conn,
    *,
    project: str,
    event_type: str,
    summary: str,
    run_id: str | None = None,
    goal_id: str | None = None,
    task_id: str | None = None,
    source: str = "runtime",
    payload: dict[str, Any] | None = None,
    severity: str = "info",
) -> int:
    cur = conn.execute(
        """
        INSERT INTO agent_events(
            project, run_id, goal_id, task_id, event_type, source, summary, payload_json, severity
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project,
            run_id,
            goal_id,
            task_id,
            event_type,
            source,
            summary,
            json.dumps(payload or {}, ensure_ascii=False, sort_keys=True),
            severity,
        ),
    )
    return cur.lastrowid


def transition_state(
    conn,
    *,
    project: str,
    entity_type: str,
    entity_id: str,
    new_status: str,
    event_type: str,
    summary: str,
    goal_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
    extra_fields: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    extra_fields = extra_fields or {}
    extra_sql = "".join(f", {key} = ?" for key in extra_fields)
    values = [new_status, *extra_fields.values(), entity_id, project]
    if entity_type == "goal":
        conn.execute(
            f"""
            UPDATE agent_goals
            SET status = ?,
                updated_at = datetime('now')
                {extra_sql}
            WHERE id = ? AND project = ?
            """,
            values,
        )
    elif entity_type == "task":
        conn.execute(
            f"""
            UPDATE agent_tasks
            SET status = ?,
                updated_at = datetime('now')
                {extra_sql}
            WHERE id = ? AND project = ?
            """,
            values,
        )
    elif entity_type == "run":
        conn.execute(
            f"""
            UPDATE runtime_runs
            SET status = ?,
                updated_at = datetime('now')
                {extra_sql}
            WHERE id = ? AND project = ?
            """,
            values,
        )
    else:
        raise SystemExit(f"Unsupported entity type for transition: {entity_type}")
    record_event(
        conn,
        project=project,
        goal_id=goal_id,
        task_id=task_id,
        run_id=run_id,
        event_type=event_type,
        source="state-machine",
        summary=summary,
        payload={"entity_type": entity_type, "entity_id": entity_id, "status": new_status, **(payload or {})},
    )


def normalize_skill_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    normalized: list[str] = []
    for item in raw_values:
        for part in str(item).split(","):
            part = part.strip().strip("\"'")
            if part:
                normalized.append(part)
    return list(dict.fromkeys(normalized))


def skill_identifiers(manifest: dict[str, Any]) -> set[str]:
    identifiers = {str(manifest.get("skill_name") or "").strip()}
    path = manifest.get("path")
    if path:
        identifiers.add(Path(str(path)).parent.name)
    return {item for item in identifiers if item}


def match_skill_trigger(
    manifest: dict[str, Any],
    request: str | None,
    task_layers: list[str],
    stack: str,
) -> dict[str, Any]:
    request_text = (request or "").lower()
    stack_text = (stack or "").lower()
    evidence: list[str] = []
    score = 0
    skill_name = manifest.get("skill_name")

    for layer in task_layers:
        if skill_name in SKILL_BY_LAYER.get(layer, ()):
            score += 4
            evidence.append(f"mapped from {layer} layer")

    if skill_name == "feature-react" and "react" in stack_text:
        score += 3
        evidence.append("React stack detected")

    for trigger in manifest.get("triggers", []):
        trigger_text = str(trigger).strip().lower()
        if not trigger_text:
            continue
        if trigger_text in request_text:
            score += 5
            evidence.append(f"trigger phrase matched: {trigger}")
            continue
        tokens = [
            token
            for token in re.findall(r"[\w\u4e00-\u9fff]+", trigger_text)
            if len(token) >= 3 and token not in {"when", "use", "user", "task", "change", "changes", "needed"}
        ]
        matched = [token for token in tokens if token in request_text]
        if matched:
            score += min(4, len(matched))
            evidence.append(f"trigger tokens matched: {', '.join(matched[:4])}")

    return {
        "matched": score > 0,
        "score": score,
        "evidence": evidence,
    }


def build_skill_dependency_graph(manifests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    graph: dict[str, dict[str, Any]] = {}
    known = set()
    for manifest in manifests:
        known.update(skill_identifiers(manifest))
    for manifest in manifests:
        missing_dependencies = [dep for dep in manifest.get("dependencies", []) if dep not in known]
        graph[manifest["skill_name"]] = {
            "version": manifest.get("version"),
            "path": manifest.get("path"),
            "status": manifest.get("status"),
            "dependencies": manifest.get("dependencies", []),
            "missing_dependencies": missing_dependencies,
            "conflicts": manifest.get("conflicts", []),
        }
    return graph


def detect_skill_conflicts(
    manifests: list[dict[str, Any]],
    selected_skill_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected = set(selected_skill_names or [])
    if selected:
        selected_manifests = [
            manifest
            for manifest in manifests
            if skill_identifiers(manifest) & selected or manifest.get("skill_name") in selected
        ]
    else:
        selected_manifests = manifests
    active_identifiers: set[str] = set()
    for manifest in selected_manifests:
        active_identifiers.update(skill_identifiers(manifest))

    conflicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    skill_name_counts: dict[str, int] = {}
    for manifest in selected_manifests:
        skill_name_counts[manifest["skill_name"]] = skill_name_counts.get(manifest["skill_name"], 0) + 1
        for conflict in manifest.get("conflicts", []):
            conflict_name = str(conflict).strip()
            if not conflict_name or conflict_name not in active_identifiers:
                continue
            pair = tuple(sorted((manifest["skill_name"], conflict_name)))
            if pair in seen:
                continue
            seen.add(pair)
            conflicts.append(
                {
                    "type": "declared-conflict",
                    "skill_name": manifest["skill_name"],
                    "conflicts_with": conflict_name,
                    "reason": f"{manifest['skill_name']} declares conflict with {conflict_name}",
                }
            )
    for skill_name, count in skill_name_counts.items():
        if count > 1:
            conflicts.append(
                {
                    "type": "duplicate-skill-name",
                    "skill_name": skill_name,
                    "conflicts_with": skill_name,
                    "reason": f"duplicate skill name: {skill_name}",
                }
            )
    return conflicts


def recommend_skills(
    task_layers: list[str],
    stack: str,
    request: str | None = None,
    skills_dir: Path | None = None,
) -> list[dict[str, Any]]:
    available = load_skill_metadata(skills_dir)
    recommendations: list[dict[str, str]] = []
    for layer in task_layers:
        for skill in SKILL_BY_LAYER.get(layer, ()):
            meta = available.get(skill, {})
            match = match_skill_trigger(meta, request, [layer], stack) if meta else {"evidence": []}
            recommendations.append(
                {
                    "skill_name": skill,
                    "rationale": meta.get("description") or f"{skill} matches {layer} layer work.",
                    "manifest_status": meta.get("status", "missing"),
                    "manifest_path": meta.get("path"),
                    "version": meta.get("version"),
                    "dependencies": meta.get("dependencies", []),
                    "conflicts": meta.get("conflicts", []),
                    "issues": meta.get("issues", []),
                    "trigger_evidence": match.get("evidence", []),
                }
            )
    if "React" in stack and "feature-react" not in [item["skill_name"] for item in recommendations]:
        meta = available.get("feature-react", {})
        match = match_skill_trigger(meta, request, task_layers, stack) if meta else {"evidence": ["React stack detected"]}
        recommendations.append(
            {
                "skill_name": "feature-react",
                "rationale": meta.get("description")
                or "React stack detected; use as implementation helper when UI/API state code is touched.",
                "manifest_status": meta.get("status", "missing"),
                "manifest_path": meta.get("path"),
                "version": meta.get("version"),
                "dependencies": meta.get("dependencies", []),
                "conflicts": meta.get("conflicts", []),
                "issues": meta.get("issues", []),
                "trigger_evidence": match.get("evidence", []),
            }
        )
    for meta in available.values():
        match = match_skill_trigger(meta, request, task_layers, stack)
        if not match["matched"]:
            continue
        recommendations.append(
            {
                "skill_name": meta["skill_name"],
                "rationale": f"Request trigger matched for {meta['skill_name']}: {'; '.join(match['evidence'])}",
                "manifest_status": meta.get("status", "missing"),
                "manifest_path": meta.get("path"),
                "version": meta.get("version"),
                "dependencies": meta.get("dependencies", []),
                "conflicts": meta.get("conflicts", []),
                "issues": meta.get("issues", []),
                "trigger_evidence": match["evidence"],
                "trigger_score": match["score"],
            }
        )
    deduped: dict[str, dict[str, Any]] = {}
    for item in recommendations:
        deduped.setdefault(item["skill_name"], item)
    return list(deduped.values())


def parse_skill_frontmatter(text: str) -> tuple[dict[str, Any], bool]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, False
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if stripped == "---":
            return data, True
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current_key:
            current = data.setdefault(current_key, [])
            if not isinstance(current, list):
                current = []
                data[current_key] = current
            current.append(stripped[2:].strip().strip("\"'"))
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            current_key = key
            if value in ("", "[]"):
                data[key] = [] if value == "[]" else ""
            elif value.startswith("[") and value.endswith("]"):
                data[key] = [part.strip().strip("\"'") for part in value[1:-1].split(",") if part.strip()]
            else:
                data[key] = value.strip("\"'")
    return data, False


def extract_skill_section_headings(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading:
                headings.append(heading)
    return headings


def validate_skill_manifest(skill_file: Path) -> dict[str, Any]:
    skill_dir_name = skill_file.parent.name
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return {
            "skill_name": skill_dir_name,
            "description": "",
            "path": workspace_relative(skill_file).as_posix(),
            "status": "invalid",
            "version": None,
            "dependencies": [],
            "triggers": [],
            "conflicts": [],
            "issues": [f"read-error: {exc}"],
        }

    frontmatter, has_frontmatter = parse_skill_frontmatter(text)
    headings = extract_skill_section_headings(text)
    name = str(frontmatter.get("name") or skill_dir_name).strip()
    version = str(frontmatter.get("version") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    dependencies = normalize_skill_list(frontmatter.get("dependencies", frontmatter.get("requires", [])))
    triggers = normalize_skill_list(frontmatter.get("triggers", frontmatter.get("when", [])))
    conflicts = normalize_skill_list(frontmatter.get("conflicts", frontmatter.get("conflicts_with", [])))

    heading_text = " ".join(headings).lower()
    issues: list[str] = []
    warnings: list[str] = []
    if not has_frontmatter:
        issues.append("missing frontmatter")
    if not name:
        issues.append("missing name")
    if not description:
        issues.append("missing description")
    if not version:
        warnings.append("missing version")
    if not triggers and "when to use" not in heading_text:
        issues.append("missing trigger instructions")
    if not any(heading.lower() == "steps" for heading in headings):
        warnings.append("missing Steps section")
    for dependency in dependencies:
        dependency_name = str(dependency).strip()
        if not dependency_name:
            issues.append("empty dependency declaration")
            continue
        dependency_path = skill_file.parent.parent / dependency_name / "SKILL.md"
        if not dependency_path.exists():
            issues.append(f"missing dependency: {dependency_name}")

    return {
        "skill_name": name,
        "version": version or None,
        "description": description,
        "path": workspace_relative(skill_file).as_posix(),
        "status": "valid" if not issues else "invalid",
        "dependencies": dependencies,
        "triggers": triggers,
        "conflicts": conflicts,
        "issues": issues,
        "warnings": warnings,
    }


def load_skill_metadata(skills_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    skills_dir = skills_dir or ROOT / "skills"
    metadata: dict[str, dict[str, Any]] = {}
    if not skills_dir.exists():
        return metadata
    for skill_file in skills_dir.glob("*/SKILL.md"):
        manifest = validate_skill_manifest(skill_file)
        metadata[manifest["skill_name"]] = {"name": manifest["skill_name"], **manifest}
    return metadata


def validate_skill_runtime(skills_dir: Path | None = None, skill_names: list[str] | None = None) -> list[dict[str, Any]]:
    skills_dir = skills_dir or ROOT / "skills"
    if not skills_dir.exists():
        return []
    requested = set(skill_names or [])
    manifests: list[dict[str, Any]] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        manifest = validate_skill_manifest(skill_file)
        if requested and skill_file.parent.name not in requested and manifest["skill_name"] not in requested:
            continue
        manifests.append(manifest)
    for requested_name in sorted(requested):
        if not any(item["skill_name"] == requested_name or Path(item["path"]).parent.name == requested_name for item in manifests):
            manifests.append(
                {
                    "skill_name": requested_name,
                    "version": None,
                    "description": "",
                    "path": str((skills_dir / requested_name / "SKILL.md").as_posix()),
                    "status": "missing",
                    "dependencies": [],
                    "triggers": [],
                    "conflicts": [],
                    "issues": ["missing SKILL.md"],
                    "warnings": [],
                }
            )
    return manifests


def plan_tasks_for(context: dict[str, Any], capability_status: str) -> list[dict[str, str]]:
    layers = context["task_layers"]
    scale = context["scale"]
    tasks = [
        {
            "title": "Confirm context, task layer, and scale",
            "assigned_role": "planner",
            "task_layer": "Runtime",
            "plan": "Use runtime context detection evidence before selecting skills.",
        },
        {
            "title": "Confirm capability chain state",
            "assigned_role": "planner",
            "task_layer": "Integration" if "Integration" in layers else ",".join(layers),
            "plan": f"Use capability evidence; current status is {capability_status}.",
        },
        {
            "title": "Apply policy decisions before execution",
            "assigned_role": "planner",
            "task_layer": "Runtime",
            "plan": "Apply plan, TDD, review, rollback, worktree, and performance decisions.",
        },
        {
            "title": "Execute scoped implementation",
            "assigned_role": "executor",
            "task_layer": ",".join(layers),
            "plan": "Modify only files required by the confirmed task boundary.",
        },
        {
            "title": "Run verification and record evidence",
            "assigned_role": "verifier",
            "task_layer": "Test",
            "plan": "Run planned checks and store result evidence.",
        },
    ]
    if scale in {"L3", "L4"}:
        tasks.append(
            {
                "title": "Run review and recovery audit",
                "assigned_role": "reviewer",
                "task_layer": "Runtime",
                "plan": "Check high-risk gates, recovery plan, and final completion evidence.",
            }
        )
    return tasks


def resolve_scan_roots(values: list[str] | None) -> list[Path]:
    base = agent_workspace_root()
    roots = values or ["."]
    resolved: list[Path] = []
    for value in roots:
        path = Path(value)
        if not path.is_absolute():
            path = base / path
        if path.exists():
            resolved.append(path.resolve())
    return resolved or [base.resolve()]


def should_skip_scan_path(path: Path) -> bool:
    skip_parts = {
        ".git",
        ".idea",
        ".vscode",
        "__pycache__",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".next",
        ".nuxt",
        ".turbo",
        ".venv",
        "venv",
        "target",
        ".pytest_cache",
    }
    return any(part in skip_parts for part in path.parts)


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in {
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".vue",
        ".svelte",
        ".py",
        ".go",
        ".java",
        ".kt",
        ".rs",
        ".php",
        ".rb",
        ".cs",
        ".json",
        ".yml",
        ".yaml",
        ".toml",
        ".sql",
        ".md",
        ".env",
    }


def classify_capability_file(path: Path, text: str) -> set[str]:
    lower_path = path.as_posix().lower()
    lower_text = text.lower()
    parts = set(part.lower() for part in path.parts)
    layers: set[str] = set()
    suffix = path.suffix.lower()

    if suffix in {".md", ".mdx", ".txt", ".rst"}:
        return layers

    frontend_path = bool(parts.intersection({"pages", "components", "views", "screens", "frontend", "client", "web", "app"}))
    frontend_code = suffix in {".tsx", ".jsx", ".vue", ".svelte"} or bool(
        re.search(r"\b(return\s*<|className=|onClick=|onChange=|defineComponent|<template\b)", text)
    )
    if frontend_path and frontend_code:
        layers.add("frontend")

    api_path = bool(parts.intersection({"api", "apis", "client", "clients", "services", "request", "requests"}))
    api_code = bool(re.search(r"\b(fetch|axios|request)\s*\(|\bhttp\.(get|post|put|patch|delete)\s*\(|/api/|graphql", lower_text))
    if api_path and api_code:
        layers.add("api")

    backend_path = bool(parts.intersection({"server", "backend", "routes", "router", "controllers", "controller", "handlers", "handler"}))
    backend_code = bool(
        re.search(
            r"\b(router|app)\.(get|post|put|patch|delete)\s*\(|@(get|post|put|patch|delete)\b|\b(controller|handler|endpoint)\b",
            lower_text,
        )
    )
    if backend_path and backend_code:
        layers.add("backend")

    data_path = bool(parts.intersection({"db", "database", "schema", "schemas", "models", "model", "entities", "entity", "migrations"}))
    data_code = suffix == ".sql" or bool(
        re.search(r"\b(create\s+table|alter\s+table|migration|prisma|drizzle|schema|collection|model)\b", lower_text)
    )
    if data_path and data_code:
        layers.add("data")

    if (
        parts.intersection({"test", "tests", "__tests__", "spec", "specs", "e2e"})
        or any(token in lower_path for token in (".test.", ".spec.", "_test."))
        or any(token in lower_text for token in ("describe(", "it(", "test(", "expect(", "assert"))
    ):
        layers.add("verification")

    return layers


def extract_route_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    generic = {"api", "v1", "v2", "http", "https"}
    for match in re.findall(r"['\"](/[\w./:{}-]+)['\"]", text):
        cleaned = re.sub(r"[:{}]", "", match.lower()).strip("/")
        for part in cleaned.split("/"):
            if len(part) >= 3 and part not in generic:
                tokens.add(part)
        if cleaned and cleaned not in generic:
            tokens.add(cleaned)
    for match in re.findall(r"\b(auth|login|phone|user|payment|order|permission|role|token|session)[\w-]*\b", text.lower()):
        tokens.add(match)
    return tokens


def capability_linkage(layer_hits: dict[str, list[str]], route_tokens: dict[str, set[str]]) -> dict[str, Any]:
    api_tokens = route_tokens.get("api", set())
    backend_tokens = route_tokens.get("backend", set())
    frontend_tokens = route_tokens.get("frontend", set())
    data_tokens = route_tokens.get("data", set())
    api_backend_overlap = sorted(api_tokens.intersection(backend_tokens))
    frontend_api_overlap = sorted(frontend_tokens.intersection(api_tokens))
    backend_data_overlap = sorted(backend_tokens.intersection(data_tokens))
    connected = bool(api_backend_overlap or frontend_api_overlap or backend_data_overlap)
    return {
        "connected": connected,
        "api_backend_overlap": api_backend_overlap[:8],
        "frontend_api_overlap": frontend_api_overlap[:8],
        "backend_data_overlap": backend_data_overlap[:8],
        "evidence": (
            f"frontend_api={compact_list(frontend_api_overlap)}; "
            f"api_backend={compact_list(api_backend_overlap)}; "
            f"backend_data={compact_list(backend_data_overlap)}"
        ),
    }


def derive_capability_status(
    layer_hits: dict[str, list[str]],
    *,
    require_data: bool = False,
    require_verification: bool = False,
) -> str:
    frontend = bool(layer_hits["frontend"])
    api = bool(layer_hits["api"])
    backend = bool(layer_hits["backend"])
    data = bool(layer_hits["data"])
    verification = bool(layer_hits["verification"])
    any_layer = frontend or api or backend or data or verification

    if not any_layer:
        return "absent"
    if frontend and api and backend and (data or not require_data) and (verification or not require_verification):
        return "complete"
    if (frontend and backend and not api) or (api and not backend) or (frontend and api and not backend):
        return "broken-chain"
    return "partial"


def confidence_for_capability(status: str, layer_hits: dict[str, list[str]], memory_hits: list[str]) -> float:
    layer_count = sum(1 for values in layer_hits.values() if values)
    score = 0.2 + min(layer_count * 0.15, 0.6)
    if status == "complete":
        score += 0.15
    if memory_hits:
        score += 0.1
    if status == "absent":
        score = 0.85 if not memory_hits else 0.55
    if status == "unconfirmed":
        score = min(score, 0.55)
    return round(max(0.0, min(score, 0.98)), 2)


def rank_context_items(
    *,
    request: str,
    context: dict[str, Any],
    workspace: dict[str, Any],
    memory_hits: list[str] | None = None,
    verification_hits: list[str] | None = None,
) -> list[dict[str, Any]]:
    memory_hits = memory_hits or []
    verification_hits = verification_hits or []
    request_lower = request.lower()
    ranked: list[dict[str, Any]] = []

    def add(kind: str, title: str, summary: str, score: float, evidence: str, source: str) -> None:
        ranked.append(
            {
                "kind": kind,
                "title": title,
                "summary": summary,
                "score": round(max(0.0, min(score, 1.0)), 2),
                "evidence": evidence,
                "source": source,
            }
        )

    add(
        "request",
        "Current request",
        context["request"],
        1.0,
        "explicit user input",
        "context",
    )
    add(
        "workspace",
        "Workspace snapshot",
        f"git_dirty={workspace['git']['dirty']}; docs={workspace['docs']['exists']}; runtime_goals={workspace['runtime']['goals']}",
        0.92 if workspace["git"]["dirty"] else 0.86,
        workspace["root"],
        "workspace",
    )
    add(
        "context",
        "Detected task context",
        f"stack={context['stack']}; layers={','.join(context['task_layers'])}; scale={context['scale']}; intent={context['intent']}",
        0.95 if context["scale"] in {"L3", "L4"} else 0.88,
        context["evidence"],
        "context",
    )
    if memory_hits:
        add(
            "memory",
            "Memory hits",
            memory_hits[0],
            0.8 if len(memory_hits) > 1 else 0.7,
            f"{len(memory_hits)} hit(s)",
            "memory",
        )
    if verification_hits:
        add(
            "verification",
            "Verification evidence",
            verification_hits[0],
            0.85,
            f"{len(verification_hits)} hit(s)",
            "verification",
        )
    if workspace["docs"]["exists"]:
        add(
            "docs",
            "Project execution docs",
            f"plans={workspace['docs']['plans']}; tasks={workspace['docs']['tasks']}; decisions={workspace['docs']['decisions']}; reviews={workspace['docs']['reviews']}; verification={workspace['docs']['verification']}",
            0.78,
            "docs/agent-os snapshot",
            "workspace",
        )
    if "plan" in request_lower or "implement" in request_lower or "feature" in request_lower:
        add("intent", "Feature intent", context["intent"], 0.84, "request language", "context")
    if "fix" in request_lower or "bug" in request_lower:
        add("intent", "Bugfix intent", context["intent"], 0.84, "request language", "context")

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in ranked:
        deduped[(item["kind"], item["title"])] = item
    return sorted(deduped.values(), key=lambda item: item["score"], reverse=True)


def search_memory_for_capability(conn, project: str, query: str, limit: int = 5) -> list[str]:
    fts_query = build_safe_fts_query(query)
    try:
        rows = conn.execute(
            """
            SELECT title, summary, files, confidence
            FROM memory_fts
            JOIN memory_items mi ON mi.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
              AND (mi.project = ? OR mi.project = '*')
            ORDER BY bm25(memory_fts)
            LIMIT ?
            """,
            (fts_query, project, limit),
        ).fetchall()
    except Exception:
        pattern = f"%{query}%"
        rows = conn.execute(
            """
            SELECT title, summary, files, confidence
            FROM memory_items
            WHERE (project = ? OR project = '*')
              AND (title LIKE ? OR summary LIKE ? OR files LIKE ? OR tags LIKE ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, pattern, pattern, pattern, pattern, limit),
        ).fetchall()
    return [
        f"{row['title']}: {row['summary']} ({row['files'] or 'no files'}, confidence={row['confidence']})"
        for row in rows
    ]


def policy_decisions_for(
    *,
    scale: str,
    capability_status: str,
    task_layers: list[str],
    signals: list[str],
) -> list[dict[str, str]]:
    normalized_layers = {layer.lower() for layer in task_layers}
    normalized_signals = {signal.lower() for signal in signals}
    high_risk_layers = {"api", "data", "integration", "runtime", "bugfix"}
    critical_signals = {
        "auth",
        "permission",
        "payment",
        "security",
        "database",
        "migration",
        "production",
        "release",
        "agent-os",
        "architecture",
        "performance",
    }
    risky = bool(normalized_layers.intersection(high_risk_layers) or normalized_signals.intersection(critical_signals))
    incomplete_capability = capability_status in {"partial", "broken-chain", "absent", "unconfirmed"}

    if scale == "L1" and capability_status == "complete" and not risky:
        plan_decision = "direct-execution"
        execution_mode = "direct"
        plan_reason = "L1 local change with complete capability chain and no high-risk signal."
    elif scale == "L2" and not incomplete_capability:
        plan_decision = "brief-plan-required"
        execution_mode = "brief-plan"
        plan_reason = "L2 module-level change needs a short plan before execution."
    else:
        plan_decision = "full-plan-required"
        execution_mode = "full-plan"
        plan_reason = "Incomplete capability chain, L3/L4 scale, or risk signal requires full planning."

    decisions = [
        {
            "decision_type": "plan",
            "decision": plan_decision,
            "rationale": plan_reason,
            "severity": "high" if plan_decision == "full-plan-required" else "normal",
            "blocking": "1" if plan_decision == "full-plan-required" else "0",
        },
        {
            "decision_type": "execution-mode",
            "decision": execution_mode,
            "rationale": "Execution mode derived from task scale, capability state, and risk signals.",
            "severity": "normal",
            "blocking": "0",
        },
    ]

    tdd_needed = bool(
        normalized_layers.intersection({"api", "data", "integration", "bugfix"})
        or normalized_signals.intersection({"auth", "payment", "permission", "security", "database", "migration"})
    )
    decisions.append(
        {
            "decision_type": "tdd",
            "decision": "recommended" if tdd_needed else "optional",
            "rationale": "TDD is recommended for contract, data, integration, security, and root-cause bug work.",
            "severity": "high" if tdd_needed else "low",
            "blocking": "0",
        }
    )

    review_needed = scale in {"L3", "L4"} or bool(
        normalized_signals.intersection({"auth", "payment", "permission", "security", "agent-os", "architecture", "release"})
    )
    decisions.append(
        {
            "decision_type": "review",
            "decision": "required" if review_needed else "optional",
            "rationale": "Review is required for cross-layer, security-sensitive, release, architecture, or Agent OS changes.",
            "severity": "critical" if review_needed else "low",
            "blocking": "1" if review_needed else "0",
        }
    )

    rollback_needed = scale == "L4" or bool(
        normalized_signals.intersection({"auth", "payment", "permission", "security", "database", "migration", "production", "release"})
    )
    decisions.append(
        {
            "decision_type": "rollback",
            "decision": "required" if rollback_needed else "recommended",
            "rationale": "Rollback is required for data, auth, payment, permission, production, release, and L4 changes.",
            "severity": "critical" if rollback_needed else "normal",
            "blocking": "1" if rollback_needed else "0",
        }
    )

    worktree_needed = scale == "L4" or bool(
        normalized_signals.intersection(
            {"large-refactor", "large-change", "dependency-upgrade", "parallel-agent", "dirty-worktree", "architecture"}
        )
    )
    decisions.append(
        {
            "decision_type": "worktree",
            "decision": "recommended" if worktree_needed else "not-needed",
            "rationale": "Worktree isolation is recommended for architecture, large refactor, dependency, dirty-worktree, and parallel-agent work.",
            "severity": "high" if worktree_needed else "low",
            "blocking": "0",
        }
    )

    performance_needed = bool(normalized_signals.intersection({"performance", "hot-path", "large-data", "render-path", "cache"}))
    decisions.append(
        {
            "decision_type": "performance",
            "decision": "required" if performance_needed else "not-needed",
            "rationale": "Performance check is required when performance, hot path, large data, render path, or cache risk is present.",
            "severity": "high" if performance_needed else "low",
            "blocking": "1" if performance_needed else "0",
        }
    )

    if "tests-missing" in normalized_signals and scale in {"L3", "L4"}:
        decisions.append(
            {
                "decision_type": "review",
                "decision": "required",
                "rationale": "Review is required because L3/L4 work has no detected test harness.",
                "severity": "critical",
                "blocking": "1",
            }
        )

    return decisions


def cmd_runtime_evaluate_policy(args: argparse.Namespace) -> None:
    signals = list(dict.fromkeys((args.signal or []) + workspace_risk_signals(args.files)))
    decisions = policy_decisions_for(
        scale=args.scale,
        capability_status=args.capability_status,
        task_layers=args.task_layer or [],
        signals=signals,
    )
    evidence = (
        f"scale={args.scale}; capability_status={args.capability_status}; "
        f"task_layers={','.join(args.task_layer or []) or 'none'}; "
        f"signals={','.join(signals) or 'none'}"
    )
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for item in decisions:
                conn.execute(
                    """
                    INSERT INTO policy_decisions(
                        project, goal_id, task_id, decision_type, decision,
                        rationale, evidence, severity, blocking
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.task_id,
                        item["decision_type"],
                        item["decision"],
                        item["rationale"],
                        evidence,
                        item.get("severity", "normal"),
                        int(item.get("blocking", "0")),
                    ),
                )
            conn.commit()
    print_json({"ok": True, "project": args.project, "evidence": evidence, "decisions": decisions})


def cmd_runtime_scan_capability(args: argparse.Namespace) -> None:
    terms = split_terms(args.term, args.name)
    if not terms:
        raise SystemExit("Expected capability --name or --term")

    roots = resolve_scan_roots(args.roots)
    layer_hits: dict[str, list[str]] = {
        "frontend": [],
        "api": [],
        "backend": [],
        "data": [],
        "verification": [],
    }
    files_scanned = 0
    files_matched = 0
    max_hits_per_layer = args.max_hits
    memory_hits: list[str] = []
    route_tokens: dict[str, set[str]] = {
        "frontend": set(),
        "api": set(),
        "backend": set(),
        "data": set(),
        "verification": set(),
    }

    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if files_scanned >= args.max_files:
                break
            if not path.is_file() or should_skip_scan_path(path) or not is_text_candidate(path):
                continue
            files_scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            haystack = f"{path.as_posix().lower()}\n{text.lower()}"
            if not any(term in haystack for term in terms):
                continue
            files_matched += 1
            rel_path = workspace_relative(path)
            layers = classify_capability_file(path, text)
            for layer in layers:
                route_tokens[layer].update(extract_route_tokens(text))
                if len(layer_hits[layer]) < max_hits_per_layer:
                    layer_hits[layer].append(rel_path.as_posix())

    status = derive_capability_status(
        layer_hits,
        require_data=args.require_data,
        require_verification=args.require_verification,
    )
    linkage = capability_linkage(layer_hits, route_tokens)
    if layer_hits["api"] and layer_hits["backend"] and not linkage["api_backend_overlap"]:
        status = "broken-chain"
    if args.use_memory:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            memory_hits = search_memory_for_capability(conn, args.project, " ".join(terms), args.max_hits)
        if status == "absent" and memory_hits:
            status = "unconfirmed"
    memory_import_hint = None
    project_memory = ROOT / "memory" / "projects" / f"{normalize_project_slug(args.project)}.md"
    if args.use_memory and not memory_hits and project_memory.exists():
        memory_import_hint = f"SQLite memory has no hits. Import Markdown first: python scripts/memory-tools.py import-markdown --project {normalize_project_slug(args.project)}"
    confidence = confidence_for_capability(status, layer_hits, memory_hits)
    code_evidence = compact_list(
        layer_hits["frontend"] + layer_hits["api"] + layer_hits["backend"] + layer_hits["data"],
        args.max_hits,
    )
    test_evidence = compact_list(layer_hits["verification"], args.max_hits)
    memory_evidence = compact_list(memory_hits, args.max_hits)
    evidence = (
        f"terms={','.join(terms)}; roots={','.join(path.as_posix() for path in roots)}; "
        f"files_scanned={files_scanned}; files_matched={files_matched}; "
        f"confidence={confidence}; memory_hits={len(memory_hits)}; linkage={linkage['evidence']}"
    )
    links = [(layer, target) for layer, targets in layer_hits.items() for target in targets]
    docs_freshness = docs_freshness_for_request(args.name or args.project, args.term or args.roots or args.files, workspace_snapshot(args.project))
    conflict = knowledge_conflict_for_capability(
        project=args.project,
        capability_name=args.name,
        layer_hits=layer_hits,
        linkage=linkage,
        memory_hits=memory_hits,
        docs_freshness=docs_freshness,
        workspace=workspace_snapshot(args.project),
    )

    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            conn.execute(
                """
                INSERT INTO capability_nodes(
                    project, name, status, frontend, api, backend,
                    data_state, verification, evidence, confidence,
                    memory_evidence, code_evidence, test_evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, name) DO UPDATE SET
                    status = excluded.status,
                    frontend = excluded.frontend,
                    api = excluded.api,
                    backend = excluded.backend,
                    data_state = excluded.data_state,
                    verification = excluded.verification,
                    evidence = excluded.evidence,
                    confidence = excluded.confidence,
                    memory_evidence = excluded.memory_evidence,
                    code_evidence = excluded.code_evidence,
                    test_evidence = excluded.test_evidence,
                    updated_at = datetime('now')
                """,
                (
                    args.project,
                    args.name,
                    status,
                    compact_list(layer_hits["frontend"]),
                    compact_list(layer_hits["api"]),
                    compact_list(layer_hits["backend"]),
                    compact_list(layer_hits["data"]),
                    compact_list(layer_hits["verification"]),
                    evidence,
                    confidence,
                    memory_evidence,
                    code_evidence,
                    test_evidence,
                ),
            )
            row = conn.execute(
                "SELECT id FROM capability_nodes WHERE project = ? AND name = ?",
                (args.project, args.name),
            ).fetchone()
            capability_id = row["id"]
            conn.execute("DELETE FROM capability_links WHERE capability_id = ?", (capability_id,))
            for relation, target in links:
                conn.execute(
                    """
                    INSERT INTO capability_links(capability_id, relation, target, evidence)
                    VALUES (?, ?, ?, ?)
                    """,
                    (capability_id, relation, target, evidence),
                )
            conn.execute(
                """
                INSERT INTO agent_observations(project, goal_id, source, summary, evidence, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    "runtime-scan-capability",
                    f"Capability {args.name} scanned as {status}.",
                    evidence,
                    "warning" if status in {"broken-chain", "unconfirmed"} else "info",
                ),
            )
            conn.commit()

    print_json(
        {
            "ok": True,
            "project": args.project,
            "name": args.name,
            "status": status,
            "confidence": confidence,
            "evidence": evidence,
            "layers": layer_hits,
            "linkage": linkage,
            "memory_hits": memory_hits,
            "memory_import_hint": memory_import_hint,
            "docs_freshness": docs_freshness,
            "knowledge_conflict": conflict,
        }
    )


def verification_checks_for(task_layers: list[str], scale: str, changed_files: list[str]) -> list[dict[str, str]]:
    layers = {layer.lower() for layer in task_layers}
    files = [Path(value) for value in changed_files]
    suffixes = {path.suffix.lower() for path in files}
    checks: list[dict[str, str]] = []

    runtime_files = {"scripts/agent-runtime.py", "scripts/agent_store.py"}
    if "runtime" in layers or any(path.as_posix() in runtime_files for path in files):
        checks.extend(
            [
                {
                    "scope": "agent runtime syntax",
                    "command": "python -m py_compile scripts\\agent-runtime.py scripts\\agent_store.py",
                    "rationale": "Agent Runtime CLI and shared store changes must compile.",
                },
                {
                    "scope": "agent runtime cli help",
                    "command": "python scripts\\agent-runtime.py --help",
                    "rationale": "Agent Runtime CLI must expose expected runtime commands.",
                },
            ]
        )

    if "api" in layers or "integration" in layers:
        checks.append(
            {
                "scope": "api contract",
                "command": "Run project API tests or endpoint smoke test for changed contract.",
                "rationale": "API and integration work must verify request/response behavior.",
            }
        )
    if "data" in layers:
        checks.append(
            {
                "scope": "data integrity",
                "command": "Run migration/schema validation and affected query tests.",
                "rationale": "Data work must verify schema, migration, and consistency behavior.",
            }
        )
    if "ui" in layers or suffixes.intersection({".tsx", ".jsx", ".vue", ".svelte", ".css"}):
        checks.append(
            {
                "scope": "ui behavior",
                "command": "Run frontend build plus targeted browser interaction/viewport checks.",
                "rationale": "UI work must verify render, interaction, and responsive behavior.",
            }
        )
    if "bugfix" in layers:
        checks.append(
            {
                "scope": "regression",
                "command": "Run or add the smallest regression test that fails before the fix and passes after it.",
                "rationale": "Bugfix work needs root-cause regression evidence.",
            }
        )
    if scale in {"L3", "L4"}:
        checks.append(
            {
                "scope": "cross-layer smoke",
                "command": "Run the primary end-to-end path touched by the change.",
                "rationale": "L3/L4 work must verify the full behavior chain, not only individual files.",
            }
        )

    if not checks:
        checks.append(
            {
                "scope": "targeted validation",
                "command": "Run the narrowest command or manual check that proves the changed behavior.",
                "rationale": "Every task needs explicit validation evidence.",
            }
        )

    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for check in checks:
        key = (check["scope"], check["command"])
        if key not in seen:
            seen.add(key)
            unique.append(check)
    return unique


def pipeline_stages_for(
    *,
    workspace: dict[str, Any],
    decisions: list[dict[str, Any]],
    verification_checks: list[dict[str, Any]],
    docs_required: bool,
    memory_required: bool,
    open_tasks: int,
    recovery_required: bool,
    recoveries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recovery_ready = any(
        row.get("status") in {"available", "used"} or row.get("checkpoint_ref")
        for row in recoveries
    )
    return [
        {
            "name": "plan",
            "status": "done",
            "summary": "Context, ranking, policy, and task queue prepared.",
        },
        {
            "name": "act",
            "status": "pending",
            "summary": "Implementation changes applied to scoped files.",
        },
        {
            "name": "observe",
            "status": "done" if workspace["runtime"]["events"] >= 0 else "pending",
            "summary": "Workspace and runtime state observed.",
        },
        {
            "name": "verify",
            "status": "done" if verification_checks else "pending",
            "summary": f"{len(verification_checks)} verification check(s) prepared.",
        },
        {
            "name": "document",
            "status": "done" if docs_required else "pending",
            "summary": "Documentation Gate evaluated.",
        },
        {
            "name": "learn",
            "status": "done" if memory_required else "pending",
            "summary": "Memory Gate evaluated.",
        },
        {
            "name": "recover",
            "status": "done" if not recovery_required or recovery_ready else "pending",
            "summary": "Recovery path evaluated." if recovery_ready or not recovery_required else "Recovery plan exists but no usable checkpoint is ready yet.",
        },
        {
            "name": "closeout",
            "status": "done" if open_tasks == 0 and verification_checks else "pending",
            "summary": "Open tasks and gate completeness checked.",
        },
    ]


def validation_profile_for(stack: str, task_layers: list[str], files: list[str] | None = None) -> list[dict[str, str]]:
    stack_lower = stack.lower()
    layers = {layer.lower() for layer in task_layers}
    checks: list[dict[str, str]] = []
    if "python" in stack_lower or any(Path(value).suffix == ".py" for value in files or []):
        checks.append({"scope": "python syntax", "command": "python -m py_compile <changed-python-files>"})
        checks.append({"scope": "python tests", "command": "python -m unittest discover -s tests"})
    if "react" in stack_lower or "frontend" in stack_lower:
        checks.append({"scope": "frontend build", "command": "npm run build"})
        checks.append({"scope": "frontend tests", "command": "npm test"})
    if "node" in stack_lower:
        checks.append({"scope": "node tests", "command": "npm test"})
    if "go" in stack_lower:
        checks.append({"scope": "go tests", "command": "go test ./..."})
    if "rust" in stack_lower:
        checks.append({"scope": "rust tests", "command": "cargo test"})
    if "ui" in layers:
        checks.append({"scope": "browser smoke", "command": "Run targeted browser interaction and viewport checks."})
    if "api" in layers or "integration" in layers:
        checks.append({"scope": "api smoke", "command": "Run API contract or endpoint smoke test."})
    if not checks:
        checks.append({"scope": "targeted validation", "command": "Run the narrowest command that proves the changed behavior."})
    return checks


def verification_pipeline_for(stack: str, task_layers: list[str], scale: str, files: list[str] | None = None) -> list[dict[str, Any]]:
    layers = {layer.lower() for layer in task_layers}
    file_values = files or []
    suffixes = {Path(value).suffix.lower() for value in file_values}
    profile_checks = validation_profile_for(stack, task_layers, file_values)
    planned_checks = verification_checks_for(task_layers, scale, file_values)
    stages: list[dict[str, Any]] = []

    def add(stage: str, command: str, required: bool, rationale: str) -> None:
        stages.append(
            {
                "stage": stage,
                "command": command,
                "required": required,
                "status": "planned",
                "rationale": rationale,
            }
        )

    if any("syntax" in check["scope"] for check in profile_checks) or suffixes.intersection({".py", ".ts", ".tsx", ".js", ".jsx"}):
        add("compile", next((check["command"] for check in profile_checks if "syntax" in check["scope"]), "Run project compile/typecheck"), True, "Changed source files need syntax or compile verification.")
    if suffixes.intersection({".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte", ".css"}):
        add("lint", "Run project lint or static checks.", scale in {"L2", "L3", "L4"}, "Frontend or typed code should pass static checks when available.")
    if any("test" in check["scope"] for check in profile_checks) or "test" in layers or scale in {"L2", "L3", "L4"}:
        add("test", next((check["command"] for check in profile_checks if "tests" in check["scope"]), "Run targeted tests."), True, "Tests provide regression evidence for non-trivial work.")
    if scale in {"L3", "L4"} or {"api", "integration", "data"}.intersection(layers):
        add("review", "Run Review Gate or equivalent consistency review.", True, "Cross-layer or high-risk work needs review evidence.")
    if "performance" in layers or any("performance" in check["rationale"].lower() for check in planned_checks):
        add("benchmark", "Run benchmark/profiling or explain substitute observation.", True, "Performance-sensitive changes require non-regression evidence.")
    if scale in {"L3", "L4"} or {"ui", "api", "integration"}.intersection(layers):
        add("smoke", next((check["command"] for check in planned_checks if "smoke" in check["scope"]), "Run the primary user/API smoke path."), True, "User-visible and cross-layer paths need smoke verification.")
    if not stages:
        add("targeted", "Run the narrowest command or manual check that proves the changed behavior.", True, "Every task needs explicit validation evidence.")

    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for stage in stages:
        deduped[(stage["stage"], stage["command"])] = stage
    return list(deduped.values())


def cmd_runtime_plan_verification(args: argparse.Namespace) -> None:
    checks = verification_checks_for(args.task_layer or [], args.scale, args.files or [])
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for check in checks:
                conn.execute(
                    """
                    INSERT INTO verification_runs(project, goal_id, task_id, scope, command, result, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.task_id,
                        check["scope"],
                        check["command"],
                        "not-run",
                        check["rationale"],
                    ),
                )
            conn.commit()
    print_json({"ok": True, "project": args.project, "checks": checks})


def cmd_runtime_detect_validation_profile(args: argparse.Namespace) -> None:
    layers = args.task_layer or detect_task_layers(args.request or "", args.files)
    stack = args.stack or detect_stack(args.files)[0]
    checks = validation_profile_for(stack, layers, args.files)
    print_json({"ok": True, "project": args.project, "stack": stack, "task_layers": layers, "checks": checks})


def cmd_runtime_verification_pipeline(args: argparse.Namespace) -> None:
    layers = args.task_layer or detect_task_layers(args.request or "", args.files)
    stack = args.stack or detect_stack(args.files)[0]
    scale = args.scale or detect_scale(args.request or "", layers, args.files)
    stages = verification_pipeline_for(stack, layers, scale, args.files)
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for stage in stages:
                conn.execute(
                    """
                    INSERT INTO verification_runs(project, goal_id, task_id, scope, command, result, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.task_id,
                        stage["stage"],
                        stage["command"],
                        "not-run",
                        stage["rationale"],
                    ),
                )
            conn.commit()
    print_json({"ok": True, "project": args.project, "stack": stack, "task_layers": layers, "scale": scale, "stages": stages})


def cmd_runtime_plan_recovery(args: argparse.Namespace) -> None:
    affected_files = normalize_csv(args.files)
    strategy_parts = []
    if args.checkpoint:
        strategy_parts.append(f"Use checkpoint {args.checkpoint}.")
    else:
        strategy_parts.append("Create or identify a clean git commit/worktree checkpoint before risky edits.")
    if affected_files:
        strategy_parts.append(f"Limit rollback to files: {affected_files}.")
    if args.migration:
        strategy_parts.append("Prepare migration down/restore path before applying data changes.")
    if args.feature_flag:
        strategy_parts.append(f"Use feature flag/config fallback: {args.feature_flag}.")
    strategy_parts.append("If validation fails, stop expansion, restore checkpoint or revert affected files, then rerun verification.")
    strategy = " ".join(strategy_parts)
    evidence = args.evidence or "runtime-plan-recovery generated from task risk inputs"

    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            cur = conn.execute(
                """
                INSERT INTO recovery_points(project, goal_id, task_id, strategy, files, status, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    strategy,
                    affected_files,
                    "available" if args.checkpoint else "planned",
                    evidence,
                ),
            )
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                task_id=args.task_id,
                event_type="RecoveryPlanned",
                source="runtime-plan-recovery",
                summary="Recovery strategy planned.",
                payload={
                    "strategy": strategy,
                    "files": affected_files,
                    "checkpoint": args.checkpoint,
                    "migration": bool(args.migration),
                    "feature_flag": args.feature_flag,
                },
            )
            conn.commit()
            recovery_id = cur.lastrowid
    else:
        recovery_id = None
    print_json(
        {
            "ok": True,
            "project": args.project,
            "id": recovery_id,
            "status": "available" if args.checkpoint else "planned",
            "strategy": strategy,
            "files": affected_files,
            "evidence": evidence,
        }
    )


def cmd_runtime_next(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        goal = conn.execute(
            """
            SELECT *
            FROM agent_goals
            WHERE project = ? AND (? IS NULL OR id = ?) AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (args.project, args.goal_id, args.goal_id),
        ).fetchone()
        task = conn.execute(
            """
            SELECT *
            FROM agent_tasks
            WHERE project = ?
              AND (? IS NULL OR goal_id = ?)
              AND status IN ('in_progress', 'pending', 'blocked')
            ORDER BY
              CASE status WHEN 'in_progress' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
              updated_at DESC
            LIMIT 1
            """,
            (args.project, args.goal_id, args.goal_id),
        ).fetchone()
        capability = conn.execute(
            """
            SELECT *
            FROM capability_nodes
            WHERE project = ?
            ORDER BY
              CASE status
                WHEN 'broken-chain' THEN 0
                WHEN 'unconfirmed' THEN 1
                WHEN 'absent' THEN 2
                WHEN 'partial' THEN 3
                ELSE 4
              END,
              updated_at DESC
            LIMIT 1
            """,
            (args.project,),
        ).fetchone()
        failed_verification = conn.execute(
            """
            SELECT *
            FROM verification_runs
            WHERE project = ? AND result IN ('failed', 'blocked')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (args.project,),
        ).fetchone()

        next_action = "create-goal"
        rationale = "No active goal exists for this project."
        if failed_verification:
            next_action = "fix-verification-failure"
            rationale = f"Latest verification is {failed_verification['result']}: {failed_verification['scope']}."
        elif capability and capability["status"] in {"broken-chain", "unconfirmed", "absent", "partial"}:
            next_action = "complete-capability-chain"
            rationale = f"Capability {capability['name']} is {capability['status']}."
        elif task:
            if task["status"] == "blocked":
                next_action = "resolve-blocker"
                rationale = task["blocker"] or f"Task {task['id']} is blocked."
            elif task["status"] == "in_progress":
                next_action = "continue-task"
                rationale = f"Task {task['id']} is already in progress."
            else:
                next_action = "start-task"
                rationale = f"Task {task['id']} is pending."
                if args.advance:
                    transition_state(
                        conn,
                        project=args.project,
                        entity_type="task",
                        entity_id=task["id"],
                        new_status="in_progress",
                        goal_id=task["goal_id"],
                        task_id=task["id"],
                        event_type="TaskStarted",
                        summary=f"Started task {task['id']}.",
                        payload={"title": task["title"], "assigned_role": task["assigned_role"]},
                    )
                    conn.commit()
        elif goal:
            next_action = "create-task"
            rationale = f"Goal {goal['id']} is active but has no pending task."

    print_json(
        {
            "ok": True,
            "project": args.project,
            "next_action": next_action,
            "rationale": rationale,
            "goal": row_to_dict(goal) if goal else None,
            "task": row_to_dict(task) if task else None,
            "capability": row_to_dict(capability) if capability else None,
            "failed_verification": row_to_dict(failed_verification) if failed_verification else None,
        }
    )


def cmd_runtime_detect_context(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    context_id = None
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            context_id = record_runtime_context(conn, context)
            conn.commit()
    print_json({"ok": True, "id": context_id, **context})


def cmd_runtime_workspace_snapshot(args: argparse.Namespace) -> None:
    snapshot = workspace_snapshot(args.project)
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            record_event(
                conn,
                project=snapshot["project"],
                event_type="ContextReady",
                source="runtime-workspace-snapshot",
                summary="Workspace snapshot captured.",
                payload=snapshot,
            )
            conn.commit()
    print_json({"ok": True, **snapshot})


def cmd_runtime_rank_context(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    workspace = workspace_snapshot(context["project"])
    memory_hits: list[str] = []
    verification_hits: list[str] = []
    if args.use_memory:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            memory_hits = search_memory_for_capability(conn, context["project"], args.request, args.limit)
            verification_hits = [
                f"{row['scope']}: {row['result']} ({row['evidence'] or 'no evidence'})"
                for row in conn.execute(
                    """
                    SELECT scope, result, evidence
                    FROM verification_runs
                    WHERE project = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (context["project"], args.limit),
                ).fetchall()
            ]
    ranked = rank_context_items(
        request=args.request,
        context=context,
        workspace=workspace,
        memory_hits=memory_hits,
        verification_hits=verification_hits,
    )
    print_json({"ok": True, "context": context, "workspace": workspace, "ranked": ranked})


def cmd_runtime_record_event(args: argparse.Namespace) -> None:
    payload = {}
    if args.payload_json:
        try:
            payload = json.loads(args.payload_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid --payload-json: {exc}") from exc
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type=args.event_type,
            source=args.source,
            summary=args.summary,
            payload=payload,
            severity=args.severity,
        )
        conn.commit()
    print_json(
        {
            "ok": True,
            "id": event_id,
            "project": args.project,
            "event_type": args.event_type,
            "summary": args.summary,
        }
    )


def cmd_kernel_step(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    project = context["project"]
    snapshot = workspace_snapshot(project)
    ranked_context = rank_context_items(
        request=args.request,
        context=context,
        workspace=snapshot,
    )
    goal_id = args.goal_id or f"goal-{uuid.uuid4().hex[:8]}"
    run_id = args.run_id or f"kernel-{uuid.uuid4().hex[:8]}"
    capability_status = args.capability_status
    policy_signals = list(dict.fromkeys((args.signal or []) + workspace_risk_signals(context["files"])))
    decisions = policy_decisions_for(
        scale=context["scale"],
        capability_status=capability_status,
        task_layers=context["task_layers"],
        signals=policy_signals,
    )
    tasks = plan_tasks_for(context, capability_status)
    skills = recommend_skills(context["task_layers"], context["stack"])
    checks = verification_checks_for(context["task_layers"], context["scale"], context["files"])
    next_action = "start-task"
    if context["scale"] in {"L3", "L4"} or capability_status in {"partial", "broken-chain", "absent", "unconfirmed"}:
        next_action = "present-plan"
    if any(item["decision_type"] == "rollback" and item["decision"] == "required" for item in decisions):
        next_action = "prepare-recovery"

    event_ids: list[int] = []
    context_id = None
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            event_ids.append(
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="UserRequest",
                    source="kernel-step",
                    summary=args.request,
                    payload={"files": context["files"]},
                )
            )
            context_id = record_runtime_context(conn, context)
            event_ids.append(
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="ContextReady",
                    source="kernel-step",
                    summary=f"Kernel built context for {context['scale']} {context['intent']} task.",
                    payload={**context, "workspace": snapshot, "ranked_context": ranked_context},
                )
            )
            conn.execute(
                """
                INSERT INTO agent_goals(id, project, objective, status, priority, current_phase, success_criteria, evidence, source_request)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    objective = excluded.objective,
                    current_phase = excluded.current_phase,
                    evidence = excluded.evidence,
                    source_request = excluded.source_request,
                    updated_at = datetime('now')
                """,
                (
                    goal_id,
                    project,
                    args.request,
                    "active",
                    "normal",
                    "planning",
                    "Kernel step has context, ranking, policy, planned tasks, skill recommendations, and verification plan.",
                    "kernel-step",
                    f"{args.request}; workspace={snapshot['root']}",
                ),
            )
            event_ids.append(
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="GoalCreated",
                    source="kernel-step",
                    summary=f"Kernel created goal {goal_id}.",
                    payload={"objective": args.request, "workspace": snapshot, "ranked_context": ranked_context},
                )
            )
            conn.execute(
                """
                INSERT INTO runtime_runs(
                    id, project, request, goal_id, status, context_id, capability_status,
                    execution_mode, summary, next_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    context_id = excluded.context_id,
                    capability_status = excluded.capability_status,
                    execution_mode = excluded.execution_mode,
                    summary = excluded.summary,
                    next_action = excluded.next_action,
                    updated_at = datetime('now')
                """,
                (
                    run_id,
                    project,
                    args.request,
                    goal_id,
                    "ready",
                    context_id,
                    capability_status,
                    next((item["decision"] for item in decisions if item["decision_type"] == "execution-mode"), None),
                    "Kernel step prepared context, ranking, policy, task plan, skill recommendations, and verification plan.",
                    next_action,
                ),
            )
            event_ids.append(
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="RunCreated",
                    source="kernel-step",
                    summary=f"Kernel run {run_id} is ready.",
                    payload={"next_action": next_action, "capability_status": capability_status, "workspace": snapshot, "ranked_context": ranked_context},
                )
            )
            for item in decisions:
                conn.execute(
                    """
                    INSERT INTO policy_decisions(project, goal_id, decision_type, decision, rationale, evidence, severity, blocking)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project,
                        goal_id,
                        item["decision_type"],
                        item["decision"],
                        item["rationale"],
                        context["evidence"],
                        item.get("severity", "normal"),
                        int(item.get("blocking", "0")),
                    ),
                )
            for index, task in enumerate(tasks, start=1):
                task_id = f"{run_id}-task-{index}"
                conn.execute(
                    """
                    INSERT INTO agent_tasks(
                        id, goal_id, project, title, task_layer, scale, status,
                        assigned_role, plan, evidence, order_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        goal_id,
                        project,
                        task["title"],
                        task["task_layer"],
                        context["scale"],
                        "pending",
                        task["assigned_role"],
                        task["plan"],
                        f"kernel-step generated task plan; workspace={snapshot['root']}; ranked={len(ranked_context)}",
                        index,
                    ),
                )
                event_ids.append(
                    record_event(
                        conn,
                        project=project,
                        run_id=run_id,
                        goal_id=goal_id,
                        task_id=task_id,
                        event_type="TaskPlanned",
                        source="kernel-step",
                        summary=task["title"],
                        payload=task,
                    )
                )
            for check in checks:
                conn.execute(
                    """
                    INSERT INTO verification_runs(project, goal_id, scope, command, result, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project, goal_id, check["scope"], check["command"], "not-run", check["rationale"]),
                )
                event_ids.append(
                    record_event(
                        conn,
                        project=project,
                        run_id=run_id,
                        goal_id=goal_id,
                        event_type="VerificationPlanned",
                        source="kernel-step",
                    summary=check["scope"],
                    payload={**check, "workspace": snapshot, "ranked_context": ranked_context},
                )
            )
            event_ids.append(
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="KernelStep",
                    source="kernel-step",
                    summary=f"Kernel selected next action: {next_action}.",
                    payload={"next_action": next_action, "decisions": decisions, "workspace": snapshot, "ranked_context": ranked_context},
                )
            )
            conn.commit()

    print_json(
        {
            "ok": True,
            "project": project,
            "run_id": run_id,
            "goal_id": goal_id,
            "context_id": context_id,
            "event_ids": event_ids,
            "context": context,
            "workspace": snapshot,
            "ranked_context": ranked_context,
            "capability_status": capability_status,
            "decisions": decisions,
            "tasks": tasks,
            "skills": skills,
            "verification_checks": checks,
            "next_action": next_action,
        }
    )


def cmd_runtime_select_skills(args: argparse.Namespace) -> None:
    layers = args.task_layer or []
    if not layers and args.request:
        layers = detect_task_layers(args.request, args.files)
    if not layers:
        layers = ["Runtime"]
    stack = args.stack or detect_stack(args.files)[0]
    recommendations = recommend_skills(layers, stack, args.request, args.skills_dir or ROOT / "skills")
    selected_skill_names = [item["skill_name"] for item in recommendations]
    manifests = validate_skill_runtime(args.skills_dir or ROOT / "skills", selected_skill_names)
    dependency_graph = build_skill_dependency_graph(manifests)
    conflicts = detect_skill_conflicts(manifests, selected_skill_names)
    blockers: list[str] = []
    for manifest in manifests:
        if manifest["status"] != "valid":
            blockers.append(f"{manifest['skill_name']}: {manifest['status']}")
        missing_dependencies = dependency_graph.get(manifest["skill_name"], {}).get("missing_dependencies", [])
        if missing_dependencies:
            blockers.append(f"{manifest['skill_name']}: missing dependencies {', '.join(missing_dependencies)}")
    for conflict in conflicts:
        blockers.append(conflict["reason"])
    ok = not blockers
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for item in recommendations:
                conn.execute(
                    """
                    INSERT INTO skill_recommendations(
                        project, goal_id, run_id, task_layers, stack, skill_name, rationale, evidence
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.run_id,
                        normalize_csv(layers),
                        stack,
                        item["skill_name"],
                        item["rationale"],
                        args.request or "runtime-select-skills",
                    ),
                )
            conn.commit()
    print_json(
        {
            "ok": ok,
            "project": args.project,
            "task_layers": layers,
            "stack": stack,
            "skills": recommendations,
            "dependency_graph": dependency_graph,
            "conflicts": conflicts,
            "blockers": blockers,
        }
    )


def cmd_runtime_validate_skills(args: argparse.Namespace) -> None:
    skills_dir = args.skills_dir or ROOT / "skills"
    manifests = validate_skill_runtime(skills_dir, args.skill)
    selected_skill_names = [manifest["skill_name"] for manifest in manifests]
    dependency_graph = build_skill_dependency_graph(manifests)
    conflicts = detect_skill_conflicts(manifests, selected_skill_names)
    trigger_matches = [
        {
            "skill_name": manifest["skill_name"],
            **match_skill_trigger(manifest, args.request, args.task_layer or [], args.stack or ""),
        }
        for manifest in manifests
    ]
    status_counts: dict[str, int] = {}
    for manifest in manifests:
        status_counts[manifest["status"]] = status_counts.get(manifest["status"], 0) + 1
    blockers: list[str] = []
    for manifest in manifests:
        if manifest["status"] != "valid":
            blockers.append(f"{manifest['skill_name']}: {manifest['status']}")
        missing_dependencies = dependency_graph.get(manifest["skill_name"], {}).get("missing_dependencies", [])
        if missing_dependencies:
            blockers.append(f"{manifest['skill_name']}: missing dependencies {', '.join(missing_dependencies)}")
    for conflict in conflicts:
        blockers.append(conflict["reason"])
    ok = bool(manifests) and not blockers

    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for manifest in manifests:
                conn.execute(
                    """
                    INSERT INTO skill_manifests(
                        project, goal_id, run_id, skill_name, version, description, path, status,
                        dependencies_json, triggers_json, conflicts_json, issues_json, warnings_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.run_id,
                        manifest["skill_name"],
                        manifest.get("version"),
                        manifest["description"],
                        manifest["path"],
                        manifest["status"],
                        json.dumps(manifest.get("dependencies", []), ensure_ascii=False),
                        json.dumps(manifest.get("triggers", []), ensure_ascii=False),
                        json.dumps(manifest.get("conflicts", []), ensure_ascii=False),
                        json.dumps(manifest.get("issues", []), ensure_ascii=False),
                        json.dumps(manifest.get("warnings", []), ensure_ascii=False),
                    ),
                )
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                event_type="SkillValidated",
                source="skill-runtime",
                summary=f"Validated {len(manifests)} skill manifest(s); {status_counts}.",
                payload={
                    "skills_dir": str(skills_dir),
                    "status_counts": status_counts,
                    "conflicts": conflicts,
                    "blockers": blockers,
                },
                severity="info" if ok else "warning",
            )
            conn.commit()

    print_json(
        {
            "ok": ok,
            "project": args.project,
            "skills_dir": str(skills_dir),
            "status_counts": status_counts,
            "skills": manifests,
            "dependency_graph": dependency_graph,
            "trigger_matches": trigger_matches,
            "conflicts": conflicts,
            "blockers": blockers,
        }
    )


def cmd_runtime_plan_tasks(args: argparse.Namespace) -> None:
    context = {
        "request": args.request,
        "task_layers": args.task_layer or detect_task_layers(args.request, args.files),
        "scale": args.scale or "L1",
        "files": args.files or [],
    }
    tasks = plan_tasks_for(context, args.capability_status)
    created: list[str] = []
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for index, task in enumerate(tasks, start=1):
                task_id = f"{args.task_prefix}-{index}"
                conn.execute(
                    """
                    INSERT INTO agent_tasks(
                        id, goal_id, project, title, task_layer, scale, status,
                        assigned_role, plan, evidence, order_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title = excluded.title,
                        task_layer = excluded.task_layer,
                        scale = excluded.scale,
                        assigned_role = excluded.assigned_role,
                        plan = excluded.plan,
                        evidence = excluded.evidence,
                        order_index = excluded.order_index,
                        updated_at = datetime('now')
                    """,
                    (
                        task_id,
                        args.goal_id,
                        args.project,
                        task["title"],
                        task["task_layer"],
                        args.scale or context["scale"],
                        "pending",
                        task["assigned_role"],
                        task["plan"],
                        f"runtime-plan-tasks from capability_status={args.capability_status}",
                        index,
                    ),
                )
                created.append(task_id)
            conn.commit()
    print_json({"ok": True, "project": args.project, "tasks": tasks, "created_task_ids": created})


def cmd_runtime_complete_task(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = conn.execute(
            "SELECT goal_id, title FROM agent_tasks WHERE id = ? AND project = ?",
            (args.id, args.project),
        ).fetchone()
        if not row:
            raise SystemExit(f"Runtime task not found: {args.id}")
        transition_state(
            conn,
            project=args.project,
            entity_type="task",
            entity_id=args.id,
            new_status="completed",
            goal_id=row["goal_id"],
            task_id=args.id,
            event_type="TaskCompleted",
            summary=f"Completed task {args.id}.",
            extra_fields={"completed_evidence": args.evidence, "evidence": args.evidence},
            payload={"title": row["title"], "evidence": args.evidence},
        )
        remaining = 0
        if row["goal_id"]:
            remaining = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM agent_tasks
                WHERE project = ?
                  AND goal_id = ?
                  AND status IN ('pending', 'in_progress', 'blocked')
                """,
                (args.project, row["goal_id"]),
            ).fetchone()["count"]
            if args.complete_goal and remaining == 0:
                transition_state(
                    conn,
                    project=args.project,
                    entity_type="goal",
                    entity_id=row["goal_id"],
                    new_status="completed",
                    goal_id=row["goal_id"],
                    event_type="GoalStateChanged",
                    summary=f"Completed goal {row['goal_id']}.",
                    extra_fields={"current_phase": "completed", "final_result": args.evidence},
                    payload={"final_result": args.evidence},
                )
        conn.commit()
    print_json(
        {
            "ok": True,
            "project": args.project,
            "id": args.id,
            "goal_id": row["goal_id"],
            "remaining_open_goal_tasks": remaining,
        }
    )


def cmd_runtime_transition(args: argparse.Namespace) -> None:
    event_type_by_entity = {
        "goal": "GoalStateChanged",
        "task": "TaskStateChanged",
        "run": "RunStateChanged",
    }
    extra_fields: dict[str, Any] = {}
    if args.entity_type == "goal":
        if args.current_phase:
            extra_fields["current_phase"] = args.current_phase
        if args.final_result:
            extra_fields["final_result"] = args.final_result
    elif args.entity_type == "task":
        if args.completed_evidence:
            extra_fields["completed_evidence"] = args.completed_evidence
            extra_fields["evidence"] = args.completed_evidence
        if args.blocker:
            extra_fields["blocker"] = args.blocker
    elif args.entity_type == "run":
        if args.next_action:
            extra_fields["next_action"] = args.next_action
        if args.summary:
            extra_fields["summary"] = args.summary

    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        transition_state(
            conn,
            project=args.project,
            entity_type=args.entity_type,
            entity_id=args.id,
            new_status=args.status,
            goal_id=args.goal_id,
            task_id=args.task_id if args.entity_type != "task" else args.id,
            run_id=args.run_id if args.entity_type != "run" else args.id,
            event_type=event_type_by_entity[args.entity_type],
            summary=args.summary or f"{args.entity_type} {args.id} -> {args.status}",
            extra_fields=extra_fields,
            payload={"reason": args.reason} if args.reason else None,
        )
        conn.commit()
    print_json(
        {
            "ok": True,
            "project": args.project,
            "entity_type": args.entity_type,
            "id": args.id,
            "status": args.status,
        }
    )


def command_is_allowed(command: str, allow_unsafe: bool = False) -> bool:
    if allow_unsafe:
        return True
    normalized = command.strip()
    return any(normalized.startswith(prefix) for prefix in SAFE_VERIFICATION_PREFIXES)


def classify_tool_type(command: str | None, explicit_type: str | None = None) -> str:
    if explicit_type:
        return explicit_type
    normalized = (command or "").strip().lower()
    if normalized.startswith("git "):
        return "git"
    if normalized.startswith(("http://", "https://", "curl ", "Invoke-WebRequest".lower())):
        return "api"
    return "shell"


def summarize_output(text: str, limit: int = 1200) -> str:
    compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def redact_secrets(text: str | None) -> str | None:
    if text is None:
        return None
    redacted = text
    for name, value in os.environ.items():
        if not value or len(value) < 8 or not SECRET_ENV_NAME_RE.search(name):
            continue
        redacted = redacted.replace(value, "[REDACTED]")

    generic = SECRET_PATTERNS["generic_secret"]
    redacted = generic.sub(lambda match: match.group(0).replace(match.group(2), "[REDACTED]"), redacted)
    redacted = SECRET_PATTERNS["private_key"].sub("[REDACTED_PRIVATE_KEY]", redacted)
    redacted = SECRET_PATTERNS["aws_access_key"].sub("[REDACTED_AWS_ACCESS_KEY]", redacted)
    return redacted


def model_provider_config(provider: str) -> dict[str, Any]:
    required_env = MODEL_PROVIDER_ENV_VARS.get(provider, ())
    configured = [name for name in required_env if os.environ.get(name)]
    missing = [name for name in required_env if not os.environ.get(name)]
    if provider in {"local", "mock"}:
        return {
            "provider": provider,
            "requires_secret": False,
            "configured": True,
            "configured_env": [],
            "missing_env": [],
            "status": "ready",
        }
    if provider == "custom":
        return {
            "provider": provider,
            "requires_secret": False,
            "configured": True,
            "configured_env": [],
            "missing_env": [],
            "status": "custom-adapter-required",
        }
    return {
        "provider": provider,
        "requires_secret": True,
        "configured": bool(configured),
        "configured_env": configured,
        "missing_env": missing,
        "status": "ready" if configured else "missing-secret",
    }


def execute_model_adapter(args: argparse.Namespace, adapter: str) -> dict[str, Any]:
    prompt = args.prompt or args.prompt_summary or ""
    if args.provider in {"local", "mock"}:
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
        response = args.response_summary or f"{args.provider} adapter response for {args.operation}; prompt_sha256={digest}."
        return {
            "status": "passed",
            "response_summary": response,
            "failure_type": None,
            "failure_detail": None,
            "input_tokens": args.input_tokens if args.input_tokens is not None else len(prompt.split()),
            "output_tokens": args.output_tokens if args.output_tokens is not None else len(response.split()),
            "cost_estimate": args.cost_estimate if args.cost_estimate is not None else 0.0,
            "diagnostics": model_provider_config(args.provider),
        }

    diagnostics = model_provider_config(args.provider)
    if diagnostics["requires_secret"] and not diagnostics["configured"]:
        return {
            "status": "blocked",
            "response_summary": f"{args.provider} provider is missing required configuration.",
            "failure_type": "environment",
            "failure_detail": f"missing-provider-config:{','.join(diagnostics['missing_env'])}",
            "input_tokens": args.input_tokens,
            "output_tokens": args.output_tokens,
            "cost_estimate": args.cost_estimate,
            "diagnostics": diagnostics,
        }

    return {
        "status": "blocked",
        "response_summary": f"{args.provider} provider configuration is present, but direct external model execution is not enabled in this runtime command.",
        "failure_type": "environment",
        "failure_detail": "external-provider-execution-disabled",
        "input_tokens": args.input_tokens,
        "output_tokens": args.output_tokens,
        "cost_estimate": args.cost_estimate,
        "diagnostics": diagnostics,
    }


def classify_failure(exit_code: int | None, output: str) -> str | None:
    if exit_code == 0:
        return None
    lower = output.lower()
    if any(token in lower for token in ("assert", "expected", "actual", "failed", "mismatch", "regression")):
        return "implementation"
    if any(token in lower for token in ("syntaxerror", "traceback", "exception", "typeerror", "referenceerror", "attributeerror")):
        return "implementation"
    if any(token in lower for token in ("no such file", "not found", "permission", "environment", "missing dependency", "cannot find module")):
        return "environment"
    if any(token in lower for token in ("timeout", "timed out", "deadlock", "hang")):
        return "environment"
    if any(token in lower for token in ("denied", "forbidden", "unauthorized", "auth", "token", "credential")):
        return "environment"
    return "unknown"


def classify_failure_detail(exit_code: int | None, output: str, command: str | None = None) -> dict[str, str | None]:
    base = classify_failure(exit_code, output)
    lower = output.lower()
    command_lower = (command or "").lower()
    detail = "unknown"
    if exit_code == 0:
        return {"type": None, "detail": None}
    if any(token in lower for token in ("permission denied", "access denied", "unauthorized", "forbidden")):
        detail = "permission"
    elif any(token in lower for token in ("syntaxerror", "parse error", "unexpected token")):
        detail = "syntax"
    elif any(token in lower for token in ("assert", "expected", "actual", "mismatch", "diff")):
        detail = "assertion"
    elif any(token in lower for token in ("timeout", "timed out", "hang", "deadlock")):
        detail = "timeout"
    elif any(token in lower for token in ("not found", "no such file", "cannot find module", "missing dependency")):
        detail = "missing-dependency"
    elif any(token in lower for token in ("test", "pytest", "unittest", "jest", "spec")) or "test" in command_lower:
        detail = "test-failure"
    elif any(token in lower for token in ("traceback", "exception", "error")):
        detail = "runtime-error"
    return {"type": base, "detail": detail}


def parse_header_values(values: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for value in values or []:
        if ":" not in value:
            raise SystemExit(f"Invalid header, expected Name: Value: {value}")
        name, header_value = value.split(":", 1)
        name = name.strip()
        header_value = header_value.strip()
        if not name:
            raise SystemExit(f"Invalid empty header name: {value}")
        headers[name] = header_value
    return headers


def run_shell_adapter(command: str, timeout: int, allow_unsafe: bool) -> dict[str, Any]:
    if not command_is_allowed(command, allow_unsafe):
        return {
            "status": "blocked",
            "exit_code": None,
            "stdout_summary": "Command blocked by Tool Runtime safety policy.",
            "failure_type": "environment",
            "failure_detail": "policy-blocked",
        }
    completed = subprocess.run(command, cwd=ROOT, shell=True, text=True, capture_output=True, timeout=timeout)
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    failure_profile = classify_failure_detail(completed.returncode, output, command)
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "exit_code": completed.returncode,
        "stdout_summary": summarize_output(output),
        "failure_type": failure_profile["type"],
        "failure_detail": failure_profile["detail"],
    }


def run_git_adapter(action: str | None, target: str | None, timeout: int) -> dict[str, Any]:
    action = action or "status"
    commands = {
        "status": ["git", "status", "--short"],
        "diff": ["git", "diff", "--", *(target.split() if target else [])],
        "log": ["git", "log", "--oneline", "-n", target or "5"],
        "branch": ["git", "branch", "--show-current"],
        "check-clean": ["git", "status", "--short"],
    }
    if action not in commands:
        return {
            "status": "blocked",
            "exit_code": None,
            "stdout_summary": f"Unsupported git action: {action}",
            "failure_type": "requirement",
            "failure_detail": "unsupported-git-action",
        }
    completed = subprocess.run(commands[action], cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    output = f"{completed.stdout}\n{completed.stderr}".strip()
    status = "passed" if completed.returncode == 0 else "failed"
    failure_type = None
    failure_detail = None
    if action == "check-clean" and output:
        status = "failed"
        failure_type = "environment"
        failure_detail = "dirty-worktree"
    elif completed.returncode != 0:
        failure_profile = classify_failure_detail(completed.returncode, output, "git")
        failure_type = failure_profile["type"]
        failure_detail = failure_profile["detail"]
    return {
        "status": status,
        "exit_code": completed.returncode,
        "stdout_summary": summarize_output(output or "clean"),
        "failure_type": failure_type,
        "failure_detail": failure_detail,
    }


def run_url_fetch_adapter(*, url: str, method: str, headers: dict[str, str], body: str | None, timeout: int, expect_text: str | None, browser_mode: bool = False) -> dict[str, Any]:
    data = body.encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    status_code = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", 200)
            response_text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        response_text = exc.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "status": "failed",
            "exit_code": None,
            "stdout_summary": f"request failed: {exc}",
            "failure_type": "environment",
            "failure_detail": "request-failed",
        }

    missing_text = bool(expect_text and expect_text not in response_text)
    status = "passed" if 200 <= int(status_code or 0) < 400 and not missing_text else "failed"
    failure_type = "implementation" if missing_text else "environment" if status != "passed" else None
    failure_detail = "expected-text-missing" if missing_text else "http-status" if status != "passed" else None
    label = "browser fetched" if browser_mode else "api response"
    return {
        "status": status,
        "exit_code": int(status_code or 0),
        "stdout_summary": summarize_output(f"{label}: status={status_code}\n{response_text}"),
        "failure_type": failure_type,
        "failure_detail": failure_detail,
    }


def run_browser_adapter(*, url: str, action: str, selector: str | None, text: str | None, expect_text: str | None, screenshot_path: str | None, timeout: int) -> dict[str, Any]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "blocked",
            "exit_code": None,
            "stdout_summary": "Playwright is not installed; browser adapter cannot run interactive actions.",
            "failure_type": "environment",
            "failure_detail": "missing-browser-adapter",
        }

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            notes = [f"browser action={action}", f"url={url}"]
            if action == "click":
                if not selector:
                    raise ValueError("--selector is required for browser click")
                page.locator(selector).click(timeout=timeout * 1000)
                notes.append(f"clicked {selector}")
            elif action == "type":
                if not selector:
                    raise ValueError("--selector is required for browser type")
                page.locator(selector).fill(text or "", timeout=timeout * 1000)
                notes.append(f"typed into {selector}")
            elif action == "screenshot":
                if not screenshot_path:
                    raise ValueError("--screenshot-path is required for browser screenshot")
                output = Path(screenshot_path)
                output.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(output), full_page=True)
                notes.append(f"screenshot {output}")
            elif action not in {"open", "check-text"}:
                raise ValueError(f"Unsupported browser action: {action}")

            content = page.content()
            browser.close()
    except (PlaywrightError, TimeoutError, OSError, ValueError) as exc:
        return {
            "status": "blocked" if "Executable doesn't exist" in str(exc) else "failed",
            "exit_code": None,
            "stdout_summary": f"browser action failed: {exc}",
            "failure_type": "environment" if "Executable doesn't exist" in str(exc) else "implementation",
            "failure_detail": "missing-browser-engine" if "Executable doesn't exist" in str(exc) else "browser-action-failed",
        }

    if expect_text and expect_text not in content:
        return {
            "status": "failed",
            "exit_code": 0,
            "stdout_summary": summarize_output("\n".join([*notes, "expected text missing", content])),
            "failure_type": "implementation",
            "failure_detail": "expected-text-missing",
        }
    return {
        "status": "passed",
        "exit_code": 0,
        "stdout_summary": summarize_output("\n".join(notes)),
        "failure_type": None,
        "failure_detail": None,
    }


def record_tool_run(conn, *, project: str, goal_id: str | None, run_id: str | None, task_id: str | None, tool_type: str, adapter: str, command: str | None, target: str | None, status: str, exit_code: int | None, duration_ms: int | None, stdout_summary: str | None, failure_type: str | None, failure_detail: str | None, evidence: str | None) -> int:
    cur = conn.execute(
        """
        INSERT INTO tool_runs(
            project, goal_id, run_id, task_id, tool_type, adapter, command, target,
            status, exit_code, duration_ms, stdout_summary, failure_type, failure_detail, evidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project,
            goal_id,
            run_id,
            task_id,
            tool_type,
            adapter,
            command,
            target,
            status,
            exit_code,
            duration_ms,
            stdout_summary,
            failure_type,
            failure_detail,
            evidence,
        ),
    )
    return cur.lastrowid


def model_adapter_name(provider: str, adapter: str | None = None) -> str:
    if adapter:
        return adapter
    return f"{provider}-model-adapter"


def record_model_run(conn, *, project: str, goal_id: str | None, run_id: str | None, task_id: str | None, provider: str, model_name: str, adapter: str, operation: str, status: str, duration_ms: int | None, input_tokens: int | None, output_tokens: int | None, cost_estimate: float | None, prompt_summary: str | None, response_summary: str | None, failure_type: str | None, failure_detail: str | None, evidence: str | None) -> int:
    cur = conn.execute(
        """
        INSERT INTO model_runs(
            project, goal_id, run_id, task_id, provider, model_name, adapter, operation,
            status, duration_ms, input_tokens, output_tokens, cost_estimate,
            prompt_summary, response_summary, failure_type, failure_detail, evidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project,
            goal_id,
            run_id,
            task_id,
            provider,
            model_name,
            adapter,
            operation,
            status,
            duration_ms,
            input_tokens,
            output_tokens,
            cost_estimate,
            prompt_summary,
            response_summary,
            failure_type,
            failure_detail,
            evidence,
        ),
    )
    return cur.lastrowid


def cmd_runtime_run_model(args: argparse.Namespace) -> None:
    adapter = model_adapter_name(args.provider, args.adapter)
    adapter_result: dict[str, Any] = {}
    started = time.perf_counter()
    if args.record_only:
        status = args.status or "not-run"
        failure_type = args.failure_type
        failure_detail = args.failure_detail
        response_summary = args.response_summary
        input_tokens = args.input_tokens
        output_tokens = args.output_tokens
        cost_estimate = args.cost_estimate
        diagnostics = model_provider_config(args.provider)
    elif args.status:
        status = args.status
        failure_type = args.failure_type
        failure_detail = args.failure_detail
        response_summary = args.response_summary
        input_tokens = args.input_tokens
        output_tokens = args.output_tokens
        cost_estimate = args.cost_estimate
        diagnostics = model_provider_config(args.provider)
    else:
        adapter_result = execute_model_adapter(args, adapter)
        status = adapter_result["status"]
        failure_type = adapter_result["failure_type"]
        failure_detail = adapter_result["failure_detail"]
        response_summary = adapter_result["response_summary"]
        input_tokens = adapter_result["input_tokens"]
        output_tokens = adapter_result["output_tokens"]
        cost_estimate = adapter_result["cost_estimate"]
        diagnostics = adapter_result["diagnostics"]

    duration_ms = args.duration_ms
    if duration_ms is None:
        duration_ms = int((time.perf_counter() - started) * 1000)

    prompt_summary = redact_secrets(args.prompt_summary or summarize_output(args.prompt or ""))
    response_summary = redact_secrets(response_summary)
    evidence_payload = {
        "summary": args.evidence or response_summary or prompt_summary,
        "diagnostics": {
            **diagnostics,
            "configured_env": diagnostics.get("configured_env", []),
            "missing_env": diagnostics.get("missing_env", []),
        },
    }
    evidence = redact_secrets(json.dumps(evidence_payload, ensure_ascii=False))
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        model_run_id = record_model_run(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            task_id=args.task_id,
            provider=args.provider,
            model_name=args.model,
            adapter=adapter,
            operation=args.operation,
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_estimate=cost_estimate,
            prompt_summary=summarize_output(prompt_summary or ""),
            response_summary=summarize_output(response_summary or ""),
            failure_type=failure_type,
            failure_detail=failure_detail,
            evidence=evidence,
        )
        record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="ModelRunRecorded",
            source="model-runtime",
            summary=f"{args.provider}/{args.model} model run recorded as {status}.",
            payload={
                "model_run_id": model_run_id,
                "provider": args.provider,
                "model": args.model,
                "adapter": adapter,
                "operation": args.operation,
                "status": status,
                "diagnostics": diagnostics,
            },
            severity="info" if status in {"passed", "not-run"} else "warning",
        )
        conn.commit()

    print_json(
        {
            "ok": status in {"passed", "not-run"},
            "id": model_run_id,
            "project": args.project,
            "provider": args.provider,
            "model": args.model,
            "adapter": adapter,
            "operation": args.operation,
            "status": status,
            "duration_ms": duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_estimate": cost_estimate,
            "response_summary": response_summary,
            "failure_type": failure_type,
            "failure_detail": failure_detail,
            "diagnostics": diagnostics,
        }
    )


def cmd_runtime_run_subagent(args: argparse.Namespace) -> None:
    completed_at = args.completed_at
    if args.status in {"completed", "blocked", "failed"} and not completed_at:
        completed_at = "now"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO subagent_runs(
                project, goal_id, run_id, task_id, role, status, input_summary,
                output_summary, boundary, handoff_to, failure_type, evidence,
                started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'now' THEN datetime('now') ELSE ? END)
            """,
            (
                args.project,
                args.goal_id,
                args.run_id,
                args.task_id,
                args.role,
                args.status,
                args.input_summary,
                args.output_summary,
                args.boundary,
                args.handoff_to,
                args.failure_type,
                args.evidence,
                args.started_at,
                completed_at,
                completed_at,
            ),
        )
        subagent_id = cur.lastrowid
        record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="SubAgentRunRecorded",
            source="subagent-runtime",
            summary=f"{args.role} sub-agent recorded as {args.status}.",
            payload={
                "subagent_run_id": subagent_id,
                "role": args.role,
                "status": args.status,
                "handoff_to": args.handoff_to,
                "boundary": args.boundary,
            },
            severity="info" if args.status in {"planned", "running", "completed"} else "warning",
        )
        conn.commit()
    print_json(
        {
            "ok": args.status in {"planned", "running", "completed"},
            "id": subagent_id,
            "project": args.project,
            "role": args.role,
            "status": args.status,
            "handoff_to": args.handoff_to,
            "failure_type": args.failure_type,
        }
    )


def subagent_chain_for(roles: list[str]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for index, role in enumerate(roles):
        handoff_to = roles[index + 1] if index + 1 < len(roles) else None
        boundary = {
            "planner": "Plan only; create scoped task decomposition and handoff.",
            "executor": "Execute scoped implementation only; do not approve own work.",
            "reviewer": "Review only; inspect diff and produce findings.",
            "verifier": "Verify only; run validation plan and report evidence.",
            "memory-recorder": "Record durable memory only; do not change implementation.",
        }[role]
        chain.append(
            {
                "role": role,
                "status": "planned",
                "handoff_to": handoff_to,
                "boundary": boundary,
                "order_index": index + 1,
            }
        )
    return chain


def cmd_runtime_plan_subagents(args: argparse.Namespace) -> None:
    roles = args.role or ["planner", "executor", "reviewer", "verifier"]
    chain = subagent_chain_for(roles)
    created: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.goal_id:
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_goals(id, project, objective, status, current_phase, success_criteria, evidence, source_request)
                VALUES (?, ?, ?, 'active', 'planning', ?, ?, ?)
                """,
                (
                    args.goal_id,
                    args.project,
                    args.request or "Sub-agent runtime chain",
                    "Sub-agent chain is planned and executable in role order.",
                    "runtime-plan-subagents",
                    args.request,
                ),
            )
        if args.run_id:
            conn.execute(
                """
                INSERT OR IGNORE INTO runtime_runs(
                    id, project, request, goal_id, status, execution_mode, summary, next_action
                )
                VALUES (?, ?, ?, ?, 'planned', ?, ?, ?)
                """,
                (
                    args.run_id,
                    args.project,
                    args.request or "Sub-agent runtime chain",
                    args.goal_id,
                    "subagent-chain",
                    "Sub-agent chain planned.",
                    "run-planned-subagents",
                ),
            )
        for item in chain:
            task_id = f"{args.task_prefix}-{item['order_index']}-{item['role']}"
            title = f"{item['role']} sub-agent task"
            plan = f"{item['role']} handles step {item['order_index']} and hands off to {item['handoff_to'] or 'done'}."
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_tasks(
                    id, goal_id, project, title, task_layer, scale, status,
                    assigned_role, plan, evidence, depends_on, order_index
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    args.goal_id,
                    args.project,
                    title,
                    args.task_layer,
                    args.scale,
                    "pending",
                    item["role"],
                    plan,
                    args.request or "runtime-plan-subagents",
                    f"{args.task_prefix}-{item['order_index'] - 1}-{roles[item['order_index'] - 2]}" if item["order_index"] > 1 else None,
                    item["order_index"],
                ),
            )
            cur = conn.execute(
                """
                INSERT INTO subagent_runs(
                    project, goal_id, run_id, task_id, role, status, input_summary,
                    output_summary, boundary, handoff_to, evidence
                )
                VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    task_id,
                    item["role"],
                    args.request or f"Plan {item['role']} sub-agent work.",
                    plan,
                    item["boundary"],
                    item["handoff_to"],
                    f"order_index={item['order_index']}",
                ),
            )
            subagent_id = cur.lastrowid
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                task_id=task_id,
                event_type="TaskPlanned",
                source="subagent-runtime",
                summary=f"Planned {item['role']} sub-agent.",
                payload={**item, "subagent_run_id": subagent_id, "task_id": task_id},
            )
            created.append({**item, "id": subagent_id, "task_id": task_id})
        conn.commit()
    print_json({"ok": True, "project": args.project, "subagents": created})


def build_review_findings(diff_text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not diff_text.strip():
        return findings
    if re.search(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]", diff_text):
        findings.append(
            {
                "severity": "P0",
                "category": "secret",
                "message": "Diff contains secret-like assignment; remove or redact before delivery.",
            }
        )
    if "TODO" in diff_text or "FIXME" in diff_text:
        findings.append(
            {
                "severity": "P2",
                "category": "incomplete-work",
                "message": "Diff contains TODO/FIXME markers that may indicate unfinished work.",
            }
        )
    if "console.log" in diff_text or "print(" in diff_text:
        findings.append(
            {
                "severity": "P3",
                "category": "debug-output",
                "message": "Diff contains debug output; confirm it is intentional.",
            }
        )
    return findings


def cmd_runtime_run_subagent_role(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    status = "completed"
    failure_type = None
    output_summary = ""
    evidence_payload: dict[str, Any] = {"role": args.role}

    if args.role == "reviewer":
        if args.diff_text is not None:
            diff_text = args.diff_text
        else:
            diff_result = run_git_adapter("diff", args.target, args.timeout)
            diff_text = diff_result["stdout_summary"] or ""
        findings = build_review_findings(diff_text)
        status = "failed" if any(item["severity"] in {"P0", "P1"} for item in findings) else "completed"
        failure_type = "implementation" if status == "failed" else None
        output_summary = f"Reviewer produced {len(findings)} finding(s)."
        evidence_payload.update({"findings": findings, "diff_summary": diff_text})
    elif args.role == "verifier":
        if not args.command:
            raise SystemExit("Expected --command for verifier role")
        verify_args = argparse.Namespace(
            command=args.command,
            timeout=args.timeout,
            allow_unsafe=args.allow_unsafe,
        )
        if not command_is_allowed(verify_args.command, verify_args.allow_unsafe):
            verify_result = {
                "result": "blocked",
                "exit_code": None,
                "stdout_summary": "Command blocked by safe verification prefix policy.",
                "failure_type": "environment",
                "failure_detail": "policy-blocked",
            }
        else:
            completed = subprocess.run(verify_args.command, cwd=ROOT, shell=True, text=True, capture_output=True, timeout=verify_args.timeout)
            output = f"{completed.stdout}\n{completed.stderr}".strip()
            failure_profile = classify_failure_detail(completed.returncode, output, verify_args.command)
            verify_result = {
                "result": "passed" if completed.returncode == 0 else "failed",
                "exit_code": completed.returncode,
                "stdout_summary": summarize_output(output),
                "failure_type": failure_profile["type"],
                "failure_detail": failure_profile["detail"],
            }
        status = "completed" if verify_result["result"] == "passed" else "failed"
        failure_type = verify_result["failure_type"]
        output_summary = f"Verifier result: {verify_result['result']} for {args.command}."
        evidence_payload.update({"verification": verify_result, "command": args.command})
    else:
        output_summary = args.output_summary or f"{args.role} role completed."
        evidence_payload["summary"] = output_summary

    duration_ms = int((time.perf_counter() - started) * 1000)
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO subagent_runs(
                project, goal_id, run_id, task_id, role, status, input_summary,
                output_summary, boundary, handoff_to, failure_type, evidence,
                started_at, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                args.project,
                args.goal_id,
                args.run_id,
                args.task_id,
                args.role,
                status,
                args.input_summary or f"Run {args.role} sub-agent role.",
                output_summary,
                args.boundary or f"{args.role} role boundary.",
                args.handoff_to,
                failure_type,
                json.dumps(evidence_payload, ensure_ascii=False),
            ),
        )
        subagent_id = cur.lastrowid
        verification_id = None
        if args.role == "verifier":
            verification = evidence_payload["verification"]
            verify_cur = conn.execute(
                """
                INSERT INTO verification_runs(
                    project, goal_id, task_id, scope, command, result, evidence,
                    exit_code, stdout_summary, failure_type, ran_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    args.scope,
                    args.command,
                    verification["result"],
                    verification["stdout_summary"],
                    verification["exit_code"],
                    verification["stdout_summary"],
                    verification["failure_type"],
                ),
            )
            verification_id = verify_cur.lastrowid
        record_event(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            task_id=args.task_id,
            event_type="SubAgentRunRecorded",
            source="subagent-runtime",
            summary=output_summary,
            payload={"subagent_run_id": subagent_id, "duration_ms": duration_ms, **evidence_payload},
            severity="info" if status == "completed" else "warning",
        )
        conn.commit()
    print_json(
        {
            "ok": status == "completed",
            "id": subagent_id,
            "verification_id": verification_id,
            "project": args.project,
            "role": args.role,
            "status": status,
            "failure_type": failure_type,
            "output_summary": output_summary,
            "evidence": evidence_payload,
        }
    )


def evaluate_host_capabilities(
    host_type: str,
    declared_capabilities: list[str],
    required_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    protocol = set(HOST_CAPABILITY_PROTOCOL.get(host_type, set()))
    declared = set(declared_capabilities)
    required = set(required_capabilities or [])
    unsupported_declared = sorted(declared - protocol) if protocol else []
    supported = sorted(declared & required)
    missing = sorted(required - declared)
    return {
        "host_type": host_type,
        "protocol_capabilities": sorted(protocol),
        "declared_capabilities": sorted(declared),
        "required_capabilities": sorted(required),
        "supported_capabilities": supported if required else sorted(declared & protocol),
        "missing_capabilities": missing,
        "unsupported_capabilities": unsupported_declared,
        "available_protocol_capabilities": sorted(protocol & declared),
        "unavailable_protocol_capabilities": sorted(protocol - declared),
        "compatible": not missing and not unsupported_declared,
    }


def cmd_runtime_register_adapter(args: argparse.Namespace) -> None:
    capabilities = args.capability or []
    issues: list[str] = []
    if not capabilities:
        issues.append("missing capability declaration")
    capability_evaluation = evaluate_host_capabilities(args.host_type, capabilities, args.require_capability)
    for capability in capability_evaluation["unsupported_capabilities"]:
        issues.append(f"unsupported capability for {args.host_type}: {capability}")
    for capability in capability_evaluation["missing_capabilities"]:
        issues.append(f"missing required capability: {capability}")
    if args.entrypoint:
        entrypoint_path = Path(args.entrypoint)
        if not entrypoint_path.is_absolute():
            entrypoint_path = ROOT / entrypoint_path
        if not entrypoint_path.exists():
            issues.append(f"missing entrypoint: {args.entrypoint}")
    status = args.status or ("invalid" if issues else "available")
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conn.execute(
            """
            INSERT INTO host_adapters(
                project, host_type, adapter_name, entrypoint, capabilities_json,
                config_path, status, issues_json, evidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project, host_type, adapter_name) DO UPDATE SET
                entrypoint = excluded.entrypoint,
                capabilities_json = excluded.capabilities_json,
                config_path = excluded.config_path,
                status = excluded.status,
                issues_json = excluded.issues_json,
                evidence = excluded.evidence,
                updated_at = datetime('now')
            """,
            (
                args.project,
                args.host_type,
                args.adapter_name,
                args.entrypoint,
                json.dumps(capabilities, ensure_ascii=False),
                args.config_path,
                status,
                json.dumps(issues, ensure_ascii=False),
                args.evidence,
            ),
        )
        row = conn.execute(
            """
            SELECT id FROM host_adapters
            WHERE project = ? AND host_type = ? AND adapter_name = ?
            """,
            (args.project, args.host_type, args.adapter_name),
        ).fetchone()
        adapter_id = row["id"]
        record_event(
            conn,
            project=args.project,
            event_type="AdapterRegistered",
            source="adapter-layer",
            summary=f"{args.host_type} adapter {args.adapter_name} registered as {status}.",
            payload={
                "adapter_id": adapter_id,
                "host_type": args.host_type,
                "adapter_name": args.adapter_name,
                "capabilities": capabilities,
                "capability_evaluation": capability_evaluation,
                "issues": issues,
            },
            severity="info" if status == "available" else "warning",
        )
        conn.commit()
    print_json(
        {
            "ok": status == "available",
            "id": adapter_id,
            "project": args.project,
            "host_type": args.host_type,
            "adapter_name": args.adapter_name,
            "status": status,
            "capabilities": capabilities,
            "capability_evaluation": capability_evaluation,
            "issues": issues,
        }
    )


def cmd_runtime_detect_host_adapter(args: argparse.Namespace) -> None:
    required = args.require_capability or []
    adapters: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            """
            SELECT *
            FROM host_adapters
            WHERE project = ? AND host_type = ?
            ORDER BY updated_at DESC
            """,
            (args.project, args.host_type),
        ).fetchall()
        for row in rows:
            capabilities = json.loads(row["capabilities_json"] or "[]")
            evaluation = evaluate_host_capabilities(args.host_type, capabilities, required)
            issues = json.loads(row["issues_json"] or "[]")
            adapters.append(
                {
                    **row_to_dict(row),
                    "capabilities": capabilities,
                    "issues": issues,
                    "capability_evaluation": evaluation,
                }
            )
    protocol = sorted(HOST_CAPABILITY_PROTOCOL.get(args.host_type, set()))
    available = [item for item in adapters if item["status"] == "available"]
    compatible = [item for item in available if item["capability_evaluation"]["compatible"]]
    print_json(
        {
            "ok": bool(compatible),
            "project": args.project,
            "host_type": args.host_type,
            "required_capabilities": required or protocol,
            "protocol_capabilities": protocol,
            "supported": [item["adapter_name"] for item in compatible],
            "unsupported": [
                {
                    "adapter_name": item["adapter_name"],
                    "status": item["status"],
                    "missing_capabilities": item["capability_evaluation"]["missing_capabilities"],
                    "unsupported_capabilities": item["capability_evaluation"]["unsupported_capabilities"],
                    "issues": item["issues"],
                }
                for item in adapters
                if item not in compatible
            ],
            "adapters": adapters,
        }
    )


def count_retries(rows: list[sqlite3.Row], key_fields: tuple[str, ...], status_field: str) -> int:
    attempts: dict[tuple[Any, ...], int] = {}
    retries = 0
    for row in rows:
        key = tuple(row[field] for field in key_fields)
        if row[status_field] in {"failed", "blocked"}:
            attempts[key] = attempts.get(key, 0) + 1
        elif row[status_field] in {"passed", "completed"} and attempts.get(key, 0):
            retries += attempts[key]
            attempts[key] = 0
    return retries


def calculate_runtime_metrics(conn, project: str, goal_id: str | None = None, run_id: str | None = None, docs_freshness: dict[str, Any] | None = None) -> dict[str, Any]:
    goal_clause = " AND goal_id = ?" if goal_id else ""
    run_clause = " AND run_id = ?" if run_id else ""
    params: list[Any] = [project] + ([goal_id] if goal_id else []) + ([run_id] if run_id else [])

    tools = conn.execute(
        f"SELECT tool_type, adapter, status, duration_ms, created_at FROM tool_runs WHERE project = ?{goal_clause}{run_clause} ORDER BY created_at",
        params,
    ).fetchall()
    models = conn.execute(
        f"SELECT provider, model_name, operation, status, duration_ms, created_at FROM model_runs WHERE project = ?{goal_clause}{run_clause} ORDER BY created_at",
        params,
    ).fetchall()
    verifications = conn.execute(
        f"SELECT scope, command, result, created_at FROM verification_runs WHERE project = ?{goal_clause} ORDER BY created_at",
        [project] + ([goal_id] if goal_id else []),
    ).fetchall()

    durations = [row["duration_ms"] for row in [*tools, *models] if row["duration_ms"] is not None]
    failed_tools = [row for row in tools if row["status"] in {"failed", "blocked"}]
    failed_models = [row for row in models if row["status"] in {"failed", "blocked"}]
    failed_verifications = [row for row in verifications if row["result"] in {"failed", "blocked"}]
    passed_verifications = [row for row in verifications if row["result"] == "passed"]
    runtime_call_count = len(tools) + len(models)
    failure_count = len(failed_tools) + len(failed_models) + len(failed_verifications)
    total_observed = runtime_call_count + len(verifications)
    retry_count = (
        count_retries(tools, ("tool_type", "adapter"), "status")
        + count_retries(models, ("provider", "model_name", "operation"), "status")
        + count_retries(verifications, ("scope", "command"), "result")
    )
    return {
        "tool_call_count": len(tools),
        "model_call_count": len(models),
        "verification_count": len(verifications),
        "failure_count": failure_count,
        "retry_count": retry_count,
        "avg_duration_ms": (sum(durations) / len(durations)) if durations else None,
        "verification_pass_rate": (len(passed_verifications) / len(verifications)) if verifications else None,
        "failure_rate": (failure_count / total_observed) if total_observed else None,
        "docs_missing": bool(docs_freshness and docs_freshness.get("missing_docs")),
        "docs_stale": bool(docs_freshness and docs_freshness.get("stale_docs")),
        "docs_update_required": bool(docs_freshness and docs_freshness.get("must_update")),
        "details": {
            "failed_tools": len(failed_tools),
            "failed_models": len(failed_models),
            "failed_verifications": len(failed_verifications),
            "duration_sample_count": len(durations),
        },
    }


def cmd_runtime_metrics(args: argparse.Namespace) -> None:
    scope = "run" if args.run_id else "goal" if args.goal_id else "project"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        docs_freshness = None
        if args.request or args.files:
            docs_freshness = docs_freshness_for_request(args.request or args.project, args.files, workspace_snapshot(args.project))
        metrics = calculate_runtime_metrics(conn, args.project, args.goal_id, args.run_id, docs_freshness)
        metric_id = None
        if args.record:
            cur = conn.execute(
                """
                INSERT INTO runtime_metrics(
                    project, goal_id, run_id, scope, tool_call_count, model_call_count,
                    verification_count, failure_count, retry_count, avg_duration_ms,
                    verification_pass_rate, failure_rate, metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    scope,
                    metrics["tool_call_count"],
                    metrics["model_call_count"],
                    metrics["verification_count"],
                    metrics["failure_count"],
                    metrics["retry_count"],
                    metrics["avg_duration_ms"],
                    metrics["verification_pass_rate"],
                    metrics["failure_rate"],
                    json.dumps(metrics, ensure_ascii=False, sort_keys=True),
                ),
            )
            metric_id = cur.lastrowid
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                event_type="MetricsRecorded",
                source="observability",
                summary=f"Runtime metrics recorded for {scope} scope.",
                payload={"metric_id": metric_id, **metrics},
            )
            conn.commit()
    print_json({"ok": True, "project": args.project, "scope": scope, "id": metric_id, "metrics": metrics})


def scoped_rows(conn, table: str, project: str, goal_id: str | None, run_id: str | None, order_column: str = "created_at") -> list[dict[str, Any]]:
    where = ["project = ?"]
    params: list[Any] = [project]
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if goal_id and "goal_id" in columns:
        where.append("(goal_id = ? OR goal_id IS NULL)")
        params.append(goal_id)
    if run_id and "run_id" in columns:
        where.append("(run_id = ? OR run_id IS NULL)")
        params.append(run_id)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {' AND '.join(where)} ORDER BY {order_column}",
        params,
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def trace_time_value(item: dict[str, Any]) -> str:
    for key in ("created_at", "updated_at", "validated_at", "registered_at", "exported_at", "ran_at", "completed_at", "started_at"):
        if item.get(key):
            return str(item[key])
    return ""


def trace_timeline(trace: dict[str, Any]) -> list[dict[str, Any]]:
    sources = [
        ("goal", [trace["goal"]] if trace.get("goal") else []),
        ("run", [trace["run"]] if trace.get("run") else []),
        ("context", [trace["context"]] if trace.get("context") else []),
        ("task", trace.get("tasks", [])),
        ("policy", trace.get("policies", [])),
        ("skill", trace.get("skill_recommendations", [])),
        ("tool", trace.get("tool_runs", [])),
        ("model", trace.get("model_runs", [])),
        ("subagent", trace.get("subagent_runs", [])),
        ("verification", trace.get("verifications", [])),
        ("event", trace.get("events", [])),
        ("recovery", trace.get("recoveries", [])),
    ]
    timeline: list[dict[str, Any]] = []
    for source, rows in sources:
        for row in rows:
            if not row:
                continue
            label = row.get("event_type") or row.get("title") or row.get("summary") or row.get("scope") or row.get("role") or row.get("status") or source
            timeline.append(
                {
                    "source": source,
                    "id": row.get("id"),
                    "at": trace_time_value(row),
                    "label": str(label),
                    "status": row.get("status") or row.get("result") or row.get("severity"),
                    "duration_ms": row.get("duration_ms"),
                    "input_hash": stable_json_hash({key: row.get(key) for key in ("request", "command", "prompt_summary", "input_summary", "summary") if key in row}),
                    "output_hash": stable_json_hash({key: row.get(key) for key in ("response_summary", "stdout_summary", "output_summary", "evidence", "payload_json") if key in row}),
                }
            )
    return sorted(timeline, key=lambda item: (item["at"] or "", item["source"], str(item["id"] or "")))


def build_runtime_trace(conn, project: str, goal_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    run = None
    context = None
    if run_id:
        run = conn.execute("SELECT * FROM runtime_runs WHERE project = ? AND id = ?", (project, run_id)).fetchone()
        if not run:
            raise SystemExit(f"Runtime run not found: {run_id}")
        goal_id = goal_id or run["goal_id"]
        if run["context_id"]:
            context = conn.execute("SELECT * FROM runtime_contexts WHERE id = ?", (run["context_id"],)).fetchone()
    goal = None
    if goal_id:
        goal = conn.execute("SELECT * FROM agent_goals WHERE project = ? AND id = ?", (project, goal_id)).fetchone()
    if not context and goal_id:
        context = conn.execute(
            "SELECT * FROM runtime_contexts WHERE project = ? ORDER BY created_at DESC LIMIT 1",
            (project,),
        ).fetchone()
    metrics = calculate_runtime_metrics(conn, project, goal_id, run_id)
    trace = {
        "project": project,
        "goal_id": goal_id,
        "run_id": run_id,
        "goal": row_to_dict(goal) if goal else None,
        "run": row_to_dict(run) if run else None,
        "context": row_to_dict(context) if context else None,
        "tasks": scoped_rows(conn, "agent_tasks", project, goal_id, run_id, "order_index"),
        "policies": scoped_rows(conn, "policy_decisions", project, goal_id, run_id),
        "skill_recommendations": scoped_rows(conn, "skill_recommendations", project, goal_id, run_id),
        "skill_manifests": scoped_rows(conn, "skill_manifests", project, goal_id, run_id, "validated_at"),
        "tool_runs": scoped_rows(conn, "tool_runs", project, goal_id, run_id),
        "model_runs": scoped_rows(conn, "model_runs", project, goal_id, run_id),
        "subagent_runs": scoped_rows(conn, "subagent_runs", project, goal_id, run_id),
        "host_adapters": scoped_rows(conn, "host_adapters", project, goal_id, run_id, "updated_at"),
        "verifications": scoped_rows(conn, "verification_runs", project, goal_id, run_id),
        "recoveries": scoped_rows(conn, "recovery_points", project, goal_id, run_id),
        "metrics": metrics,
        "events": scoped_rows(conn, "agent_events", project, goal_id, run_id),
    }
    timeline = trace_timeline(trace)
    trace["timeline"] = timeline
    trace["duration_ms"] = sum(item["duration_ms"] or 0 for item in timeline)
    trace["input_hash"] = stable_json_hash({"project": project, "goal_id": goal_id, "run_id": run_id, "request": trace.get("run", {}).get("request") if trace.get("run") else None})
    trace["output_hash"] = stable_json_hash({key: trace[key] for key in ("tasks", "policies", "skill_recommendations", "tool_runs", "model_runs", "subagent_runs", "verifications", "events")})
    trace["event_count"] = len(trace["events"])
    return trace


def cmd_runtime_trace(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        trace = build_runtime_trace(conn, args.project, args.goal_id, args.run_id)
        trace_id = None
        if args.record:
            cur = conn.execute(
                """
                INSERT INTO runtime_traces(project, goal_id, run_id, trace_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    args.project,
                    trace["goal_id"],
                    args.run_id,
                    json.dumps(trace, ensure_ascii=False, sort_keys=True),
                ),
            )
            trace_id = cur.lastrowid
            record_event(
                conn,
                project=args.project,
                goal_id=trace["goal_id"],
                run_id=args.run_id,
                event_type="TraceExported",
                source="trace-report",
                summary="Runtime trace exported.",
                payload={"trace_id": trace_id},
            )
            conn.commit()
            trace = build_runtime_trace(conn, args.project, trace["goal_id"], args.run_id)
    print_json({"ok": True, "id": trace_id, "trace": trace})


def check_required_paths(root: Path) -> tuple[str, list[str]]:
    required_dirs = ["context", "rules", "skills", "tools", "workflows", "memory", "scripts", "tests"]
    missing = [path for path in required_dirs if not (root / path).is_dir()]
    return ("passed" if not missing else "failed", [f"missing directory: {path}" for path in missing])


def check_agents_file(root: Path) -> tuple[str, list[str]]:
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        return "failed", ["missing AGENTS.md"]
    text = agents_path.read_text(encoding="utf-8", errors="ignore")
    required_terms = ["Agent OS", "Mandatory Gates", "Execution Flow", "Project-Local Asset Priority"]
    missing = [term for term in required_terms if term not in text]
    return ("passed" if not missing else "failed", [f"AGENTS.md missing section: {term}" for term in missing])


def check_rules(root: Path) -> tuple[str, list[str]]:
    rules_dir = root / "rules"
    required_rules = ["coding-style.md", "testing.md", "change-policy.md", "agent-runtime.md", "security-hardening.md"]
    missing = [name for name in required_rules if not (rules_dir / name).exists()]
    return ("passed" if not missing else "failed", [f"missing rule: {name}" for name in missing])


def check_skills(root: Path) -> tuple[str, list[str]]:
    manifests = validate_skill_runtime(root / "skills")
    if not manifests:
        return "failed", ["no skills found"]
    issues = []
    for manifest in manifests:
        if manifest["status"] != "valid":
            issues.append(f"{manifest['skill_name']}: {', '.join(manifest['issues'])}")
    return ("passed" if not issues else "failed", issues)


def check_memory(root: Path, conn) -> tuple[str, list[str]]:
    issues = []
    if not (root / "memory" / "schema.sql").exists():
        issues.append("missing memory/schema.sql")
    if not (root / "memory" / "projects").is_dir():
        issues.append("missing memory/projects directory")
    schema_version = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    if not schema_version:
        issues.append("schema_meta schema_version missing")
    elif schema_version["value"] != CURRENT_SCHEMA_VERSION:
        issues.append(f"schema_version expected {CURRENT_SCHEMA_VERSION}, found {schema_version['value']}")
    return ("passed" if not issues else "failed", issues)


def check_runtime(root: Path, conn) -> tuple[str, list[str]]:
    required_tables = [
        "runtime_runs",
        "agent_goals",
        "agent_tasks",
        "agent_events",
        "tool_runs",
        "skill_manifests",
        "model_runs",
        "subagent_runs",
        "host_adapters",
        "runtime_metrics",
        "runtime_traces",
    ]
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    existing = {row["name"] for row in rows}
    issues = [f"missing runtime table: {table}" for table in required_tables if table not in existing]
    script_path = root / "scripts" / "agent-runtime.py"
    if not script_path.exists():
        issues.append("missing scripts/agent-runtime.py")
    return ("passed" if not issues else "failed", issues)


def check_bootstrap(root: Path) -> tuple[str, list[str]]:
    issues = []
    installer = root / "scripts" / "agent-os.py"
    if not installer.exists():
        issues.append("missing scripts/agent-os.py")
    else:
        text = installer.read_text(encoding="utf-8", errors="ignore")
        if "PROJECT_AGENTS_TEMPLATE" not in text:
            issues.append("installer missing embedded root AGENTS bootstrap template")
        if ".agent-os/AGENTS.md" not in text:
            issues.append("embedded bootstrap does not delegate to .agent-os/AGENTS.md")
    return ("passed" if not issues else "failed", issues)


def check_policy_pack_health(root: Path) -> tuple[str, list[str]]:
    issues = []
    packs_dir = root / "policy-packs"
    if not packs_dir.exists():
        issues.append("missing policy-packs directory")
    else:
        packs = list(packs_dir.glob("*/policy-pack.json"))
        if not packs:
            issues.append("no policy-pack.json files found")
        for pack_file in packs:
            pack = load_policy_pack(pack_file)
            if pack["status"] != "valid":
                issues.extend(f"{pack['name']}: {issue}" for issue in pack["issues"])
    return ("passed" if not issues else "failed", issues)


def check_security_health(root: Path) -> tuple[str, list[str]]:
    issues = []
    if not (root / "rules" / "security-hardening.md").exists():
        issues.append("missing rules/security-hardening.md")
    scan = scan_secrets(root, max_files=500)
    if scan["findings"]:
        issues.append(f"secret scan found {len(scan['findings'])} finding(s)")
    return ("passed" if not issues else "failed", issues)


def check_db_writable(db_path: Path, schema_path: Path) -> tuple[str, list[str]]:
    issues = []
    try:
        with connect(db_path) as conn:
            ensure_initialized(conn, schema_path)
            conn.execute("CREATE TABLE IF NOT EXISTS runtime_write_check(id INTEGER PRIMARY KEY, checked_at TEXT)")
            conn.execute("INSERT INTO runtime_write_check(checked_at) VALUES (datetime('now'))")
            conn.execute("DELETE FROM runtime_write_check WHERE id IN (SELECT id FROM runtime_write_check ORDER BY id DESC LIMIT 1)")
            conn.commit()
    except Exception as exc:  # pragma: no cover - defensive health path
        issues.append(f"database is not writable: {exc}")
    return ("passed" if not issues else "failed", issues)


def cmd_runtime_doctor(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    checks: list[dict[str, Any]] = []
    status, issues = check_required_paths(root)
    checks.append({"name": "directories", "status": status, "issues": issues})
    status, issues = check_agents_file(root)
    checks.append({"name": "agents", "status": status, "issues": issues})
    status, issues = check_rules(root)
    checks.append({"name": "rules", "status": status, "issues": issues})
    status, issues = check_skills(root)
    checks.append({"name": "skills", "status": status, "issues": issues})
    status, issues = check_bootstrap(root)
    checks.append({"name": "bootstrap", "status": status, "issues": issues})
    status, issues = check_policy_pack_health(root)
    checks.append({"name": "policy-packs", "status": status, "issues": issues})
    status, issues = check_security_health(root)
    checks.append({"name": "security", "status": status, "issues": issues})

    db_path = args.db
    schema_path = args.schema
    if args.root:
        db_path = root / "memory" / "index.db"
        schema_path = root / "memory" / "schema.sql"
    try:
        with connect(db_path) as conn:
            ensure_initialized(conn, schema_path)
            status, issues = check_memory(root, conn)
            checks.append({"name": "memory", "status": status, "issues": issues})
            status, issues = check_runtime(root, conn)
            checks.append({"name": "runtime", "status": status, "issues": issues})
            schema_version = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
            version_issues = []
            if not schema_version or schema_version["value"] != CURRENT_SCHEMA_VERSION:
                version_issues.append(f"schema_version expected {CURRENT_SCHEMA_VERSION}, found {schema_version['value'] if schema_version else 'missing'}")
            checks.append({"name": "version", "status": "passed" if not version_issues else "failed", "issues": version_issues})
            status, issues = check_db_writable(db_path, schema_path)
            checks.append({"name": "db-writable", "status": status, "issues": issues})
    except (Exception, SystemExit) as exc:  # pragma: no cover - defensive health report path
        checks.append({"name": "memory", "status": "failed", "issues": [f"memory initialization failed: {exc}"]})
        checks.append({"name": "runtime", "status": "failed", "issues": [f"runtime initialization failed: {exc}"]})

    ok = all(check["status"] == "passed" for check in checks)
    print_json(
        {
            "ok": ok,
            "root": str(root),
            "checks": checks,
            "summary": {
                "passed": sum(1 for check in checks if check["status"] == "passed"),
                "failed": sum(1 for check in checks if check["status"] != "passed"),
            },
        }
    )


def read_agent_os_version(root: Path = ROOT) -> str:
    version_path = root / "VERSION"
    if not version_path.exists():
        return "unknown"
    return version_path.read_text(encoding="utf-8", errors="ignore").strip() or "unknown"


def read_db_schema_version(db_path: Path, schema_path: Path) -> str | None:
    if not db_path.exists():
        return None
    with connect(db_path) as conn:
        ensure_initialized(conn, schema_path)
        row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
        return row["value"] if row else None


def cmd_runtime_version(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    db_path = args.db if not args.root else root / "memory" / "index.db"
    schema_path = args.schema if not args.root else root / "memory" / "schema.sql"
    db_schema_version = read_db_schema_version(db_path, schema_path) if db_path.exists() else None
    print_json(
        {
            "ok": True,
            "root": str(root),
            "agent_os_version": read_agent_os_version(root),
            "expected_schema_version": CURRENT_SCHEMA_VERSION,
            "db_exists": db_path.exists(),
            "db_schema_version": db_schema_version,
            "migration_required": db_schema_version != CURRENT_SCHEMA_VERSION,
        }
    )


def cmd_runtime_migrate(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    db_path = args.db if not args.root else root / "memory" / "index.db"
    schema_path = args.schema if not args.root else root / "memory" / "schema.sql"
    before = read_db_schema_version(db_path, schema_path) if db_path.exists() else None
    backup_path = db_path.with_suffix(db_path.suffix + f".bak-{time.strftime('%Y%m%d%H%M%S')}")
    actions = []
    if not db_path.exists():
        actions.append("create database")
    else:
        actions.append(f"backup database to {backup_path}")
    if before != CURRENT_SCHEMA_VERSION:
        actions.append(f"migrate schema to {CURRENT_SCHEMA_VERSION}")
    rollback_hint = f"Restore backup with: copy {backup_path} {db_path}" if db_path.exists() else "Delete the newly created database and rerun migration."
    if args.dry_run:
        print_json(
            {
                "ok": True,
                "applied": False,
                "root": str(root),
                "db": str(db_path),
                "backup": str(backup_path) if db_path.exists() else None,
                "before_schema_version": before,
                "after_schema_version": before,
                "actions": actions,
                "migration_required": before != CURRENT_SCHEMA_VERSION,
                "rollback_hint": rollback_hint,
                "report": {
                    "will_create_database": not db_path.exists(),
                    "will_backup": db_path.exists(),
                    "will_migrate_schema": before != CURRENT_SCHEMA_VERSION,
                },
            }
        )
        return
    if db_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(db_path, backup_path)
    try:
        with connect(db_path) as conn:
            ensure_initialized(conn, schema_path)
            row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
            after = row["value"] if row else None
    except Exception:
        if backup_path.exists():
            shutil.copy2(backup_path, db_path)
        raise
    print_json(
        {
            "ok": after == CURRENT_SCHEMA_VERSION,
            "applied": True,
            "root": str(root),
            "db": str(db_path),
            "backup": str(backup_path) if backup_path.exists() else None,
            "before_schema_version": before,
            "after_schema_version": after,
            "actions": actions,
            "migration_required": before != CURRENT_SCHEMA_VERSION,
            "rollback_hint": rollback_hint,
            "report": {
                "created_database": before is None,
                "backup_created": backup_path.exists(),
                "schema_migrated": before != after,
            },
        }
    )


def dashboard_rows(conn, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [row_to_dict(row) for row in conn.execute(query, params).fetchall()]


def build_dashboard_data(conn, project: str, limit: int = 20) -> dict[str, Any]:
    return {
        "project": project,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "goals": dashboard_rows(
            conn,
            "SELECT id, objective, status, priority, current_phase, updated_at FROM agent_goals WHERE project = ? ORDER BY updated_at DESC LIMIT ?",
            (project, limit),
        ),
        "runs": dashboard_rows(
            conn,
            "SELECT id, goal_id, status, capability_name, capability_status, execution_mode, updated_at FROM runtime_runs WHERE project = ? ORDER BY updated_at DESC LIMIT ?",
            (project, limit),
        ),
        "tasks": dashboard_rows(
            conn,
            "SELECT id, goal_id, title, status, assigned_role, order_index, updated_at FROM agent_tasks WHERE project = ? ORDER BY updated_at DESC LIMIT ?",
            (project, limit),
        ),
        "events": dashboard_rows(
            conn,
            "SELECT id, run_id, goal_id, event_type, source, summary, severity, created_at FROM agent_events WHERE project = ? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ),
        "verification": dashboard_rows(
            conn,
            "SELECT id, goal_id, task_id, scope, command, result, failure_type, evidence, created_at FROM verification_runs WHERE project = ? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ),
    }


def render_dashboard_table(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"<section><h2>{html.escape(title)}</h2><p class=\"empty\">暂无记录</p></section>"
    columns = list(rows[0].keys())
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(column) or ''))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<section><h2>{html.escape(title)}</h2><table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></section>"


def render_dashboard_html(data: dict[str, Any]) -> str:
    sections = [
        render_dashboard_table("目标", data["goals"]),
        render_dashboard_table("运行", data["runs"]),
        render_dashboard_table("任务", data["tasks"]),
        render_dashboard_table("事件", data["events"]),
        render_dashboard_table("验证", data["verification"]),
    ]
    summary_cards = "".join(
        f"<div class=\"metric\"><strong>{len(data[key])}</strong><span>{label}</span></div>"
        for key, label in (
            ("goals", "目标"),
            ("runs", "运行"),
            ("tasks", "任务"),
            ("events", "事件"),
            ("verification", "验证"),
        )
    )
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Agent OS 运行总览 - {html.escape(data['project'])}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f7f8fb; color: #1f2937; }}
    header {{ padding: 16px 24px 14px; background: #111827; color: white; }}
    main {{ padding: 16px 24px 28px; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    h2 {{ margin: 16px 0 8px; font-size: 15px; }}
    .meta {{ color: #cbd5e1; margin: 0; font-size: 12px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin: 12px 0 6px; }}
    .metric {{ background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px 12px; }}
    .metric strong {{ display: block; font-size: 20px; line-height: 1.1; }}
    .metric span {{ color: #6b7280; font-size: 12px; }}
    section {{ margin-top: 10px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #e5e7eb; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e5e7eb; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #f3f4f6; font-weight: 700; }}
    tr:last-child td {{ border-bottom: 0; }}
    .empty {{ background: white; border: 1px solid #e5e7eb; padding: 10px 12px; color: #6b7280; }}
  </style>
</head>
<body>
  <header>
    <h1>Agent OS 运行总览</h1>
    <p class=\"meta\">项目：{html.escape(data['project'])} · 生成时间：{html.escape(data['generated_at'])}</p>
  </header>
  <main>
    <div class=\"metrics\">{summary_cards}</div>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def cmd_runtime_dashboard(args: argparse.Namespace) -> None:
    output = args.output or (ROOT / "docs" / "agent-os" / "dashboard.html")
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        data = build_dashboard_data(conn, args.project, args.limit)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard_html(data), encoding="utf-8")
    data_source = dashboard_data_source(data)
    data_output = args.data_output
    if data_output:
        data_output.parent.mkdir(parents=True, exist_ok=True)
        data_output.write_text(json.dumps(data_source, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json(
        {
            "ok": True,
            "project": args.project,
            "output": str(output),
            "data_output": str(data_output) if data_output else None,
            "sections": ["goals", "runs", "tasks", "events", "verification"],
            "data_source": data_source if args.inline_data else {"kind": data_source["kind"], "section_counts": data_source["sections"]},
        }
    )


def average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def parse_version_parts(version: str | None) -> tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", version)[:4])


def compare_versions(current: str | None, expected: str | None) -> int:
    current_parts = parse_version_parts(current)
    expected_parts = parse_version_parts(expected)
    max_len = max(len(current_parts), len(expected_parts), 1)
    current_parts = current_parts + (0,) * (max_len - len(current_parts))
    expected_parts = expected_parts + (0,) * (max_len - len(expected_parts))
    if current_parts == expected_parts:
        return 0
    return -1 if current_parts < expected_parts else 1


def sequence_points(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    ordered = list(reversed(rows))
    points = []
    for index, row in enumerate(ordered, start=1):
        value = row.get(field)
        if value is None:
            continue
        points.append({"index": index, "created_at": row.get("created_at"), "value": value})
    return points


def cluster_failures(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for row in snapshots:
        payload = json.loads(row.get("metrics_json") or "{}")
        if row.get("failure_rate"):
            key = payload.get("dominant_failure_type") or payload.get("failure_type") or "runtime-failure"
            cluster = clusters.setdefault(key, {"type": key, "count": 0, "latest_at": None, "evidence": []})
            cluster["count"] += 1
            cluster["latest_at"] = cluster["latest_at"] or row.get("created_at")
            if payload.get("failure_evidence"):
                cluster["evidence"].append(payload["failure_evidence"])
        if payload.get("docs_missing") or payload.get("docs_stale"):
            cluster = clusters.setdefault("documentation-drift", {"type": "documentation-drift", "count": 0, "latest_at": None, "evidence": []})
            cluster["count"] += 1
            cluster["latest_at"] = cluster["latest_at"] or row.get("created_at")
            cluster["evidence"].append("docs missing/stale")
    return sorted(clusters.values(), key=lambda item: (-item["count"], item["type"]))


def dashboard_data_source(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "vscode-dashboard-data",
        "project": data["project"],
        "generated_at": data["generated_at"],
        "sections": {
            "goals": len(data["goals"]),
            "runs": len(data["runs"]),
            "tasks": len(data["tasks"]),
            "events": len(data["events"]),
            "verification": len(data["verification"]),
        },
        "records": data,
    }


def cmd_runtime_quality_trends(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            """
            SELECT id, scope, failure_rate, verification_pass_rate, retry_count, metrics_json, created_at
            FROM runtime_metrics
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
    snapshots = [row_to_dict(row) for row in rows]
    failure_rates = [row["failure_rate"] for row in snapshots if row["failure_rate"] is not None]
    pass_rates = [row["verification_pass_rate"] for row in snapshots if row["verification_pass_rate"] is not None]
    docs_update_required = 0
    docs_missing_or_stale = 0
    for row in snapshots:
        payload = json.loads(row["metrics_json"] or "{}")
        if payload.get("docs_update_required"):
            docs_update_required += 1
        if payload.get("docs_missing") or payload.get("docs_stale"):
            docs_missing_or_stale += 1
    trends = {
        "sample_count": len(snapshots),
        "latest_failure_rate": snapshots[0]["failure_rate"] if snapshots else None,
        "average_failure_rate": average(failure_rates),
        "latest_verification_pass_rate": snapshots[0]["verification_pass_rate"] if snapshots else None,
        "average_verification_pass_rate": average(pass_rates),
        "retry_count_total": sum(row["retry_count"] or 0 for row in snapshots),
        "docs_update_required_count": docs_update_required,
        "docs_missing_or_stale_count": docs_missing_or_stale,
        "docs_missing_rate": (docs_missing_or_stale / len(snapshots)) if snapshots else None,
        "failure_rate_series": sequence_points(snapshots, "failure_rate"),
        "verification_pass_rate_series": sequence_points(snapshots, "verification_pass_rate"),
        "failure_clusters": cluster_failures(snapshots),
    }
    report = {"ok": True, "project": args.project, "trends": trends, "snapshots": snapshots}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json(report)


def load_policy_pack(pack_file: Path) -> dict[str, Any]:
    try:
        data = json.loads(pack_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "name": pack_file.parent.name,
            "path": workspace_relative(pack_file).as_posix(),
            "status": "invalid",
            "issues": [f"invalid policy pack json: {exc}"],
        }
    issues = []
    for field in ("name", "version", "description"):
        if not data.get(field):
            issues.append(f"missing {field}")
    for field in ("rules", "workflows", "gates"):
        if not isinstance(data.get(field), list) or not data.get(field):
            issues.append(f"missing {field}")
    for ref in [*(data.get("rules") or []), *(data.get("workflows") or [])]:
        ref_path = ROOT / ref
        if not ref_path.exists():
            issues.append(f"missing reference: {ref}")
    if data.get("inherits") is not None and not isinstance(data.get("inherits"), list):
        issues.append("inherits must be a list")
    if data.get("overrides") is not None and not isinstance(data.get("overrides"), dict):
        issues.append("overrides must be an object")
    if data.get("conflicts") is not None and not isinstance(data.get("conflicts"), list):
        issues.append("conflicts must be a list")
    return {
        "name": data.get("name") or pack_file.parent.name,
        "version": data.get("version"),
        "description": data.get("description"),
        "path": workspace_relative(pack_file).as_posix(),
        "rules": data.get("rules") or [],
        "workflows": data.get("workflows") or [],
        "gates": data.get("gates") or [],
        "inherits": data.get("inherits") or [],
        "overrides": data.get("overrides") or {},
        "conflicts": data.get("conflicts") or [],
        "status": "valid" if not issues else "invalid",
        "issues": issues,
    }


def policy_state_path(root: Path) -> Path:
    return root / "policy-packs" / ".enabled.json"


def load_policy_state(root: Path) -> dict[str, Any]:
    state_path = policy_state_path(root)
    if not state_path.exists():
        return {"enabled": [], "overrides": {}}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"enabled": [], "overrides": {}, "issues": ["invalid enabled policy state"]}
    if not isinstance(data.get("enabled"), list):
        data["enabled"] = []
    if not isinstance(data.get("overrides"), dict):
        data["overrides"] = {}
    return data


def write_policy_state(root: Path, state: dict[str, Any]) -> None:
    path = policy_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def all_policy_packs(packs_dir: Path) -> list[dict[str, Any]]:
    if not packs_dir.exists():
        return []
    return [load_policy_pack(pack_file) for pack_file in sorted(packs_dir.glob("*/policy-pack.json"))]


def policy_pack_conflicts(packs: list[dict[str, Any]], enabled: list[str]) -> list[str]:
    by_name = {pack["name"]: pack for pack in packs}
    issues = []
    for name in enabled:
        pack = by_name.get(name)
        if not pack:
            issues.append(f"enabled policy pack missing: {name}")
            continue
        for inherited in pack.get("inherits", []):
            if inherited not in by_name:
                issues.append(f"{name} inherits missing pack: {inherited}")
            elif inherited not in enabled:
                issues.append(f"{name} inherits disabled pack: {inherited}")
        for conflict in pack.get("conflicts", []):
            if conflict in enabled:
                issues.append(f"{name} conflicts with enabled pack: {conflict}")
    return issues


def cmd_runtime_policy_packs(args: argparse.Namespace) -> None:
    packs_dir = args.packs_dir or ROOT / "policy-packs"
    root = packs_dir.parent if args.packs_dir else ROOT
    state = load_policy_state(root)
    packs = all_policy_packs(packs_dir)
    if args.action:
        if not args.name:
            raise SystemExit("--name is required when --action is used")
        enabled = list(dict.fromkeys(state.get("enabled", [])))
        if args.action == "enable" and args.name not in enabled:
            enabled.append(args.name)
        elif args.action == "disable":
            enabled = [name for name in enabled if name != args.name]
        state["enabled"] = enabled
        if args.override:
            overrides = state.setdefault("overrides", {})
            pack_overrides = overrides.setdefault(args.name, {})
            for value in args.override:
                if "=" not in value:
                    raise SystemExit(f"Invalid --override value, expected key=value: {value}")
                key, raw = value.split("=", 1)
                pack_overrides[key] = raw
        write_policy_state(root, state)
    if args.name:
        packs = [pack for pack in packs if pack["name"] == args.name or Path(pack["path"]).parent.name == args.name]
        if not packs:
            packs.append({"name": args.name, "path": str(packs_dir / args.name / "policy-pack.json"), "status": "missing", "issues": ["policy pack missing"]})
    enabled = state.get("enabled", [])
    conflicts = policy_pack_conflicts(all_policy_packs(packs_dir), enabled)
    for pack in packs:
        pack["enabled"] = pack["name"] in enabled
        pack["active_overrides"] = state.get("overrides", {}).get(pack["name"], {})
    ok = bool(packs) and all(pack["status"] == "valid" for pack in packs) and not conflicts
    print_json(
        {
            "ok": ok,
            "packs_dir": str(packs_dir),
            "state_path": str(policy_state_path(root)),
            "enabled": enabled,
            "conflicts": conflicts,
            "packs": packs,
        }
    )


def load_security_ignore_patterns(root: Path) -> list[str]:
    ignore_file = root / ".agent-os-security-ignore"
    if not ignore_file.exists():
        return []
    patterns = []
    for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped.replace("\\", "/"))
    return patterns


def is_ignored_security_path(path: Path, root: Path, patterns: list[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {char: value.count(char) for char in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def high_entropy_findings(line: str) -> list[dict[str, Any]]:
    findings = []
    for match in HIGH_ENTROPY_VALUE_RE.finditer(line):
        value = match.group(1)
        entropy = shannon_entropy(value)
        if len(value) >= 32 and entropy >= 4.2 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            findings.append({"type": "high_entropy", "entropy": round(entropy, 3), "value_preview": f"{value[:4]}...{value[-4:]}"})
    return findings


def iter_security_scan_files(root: Path, max_files: int, ignore_patterns: list[str] | None = None) -> list[Path]:
    ignore_patterns = ignore_patterns or []
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= max_files:
            break
        rel_parts = path.relative_to(root).parts
        if any(part in SECURITY_SKIP_DIRS for part in rel_parts):
            continue
        if not path.is_file():
            continue
        if is_ignored_security_path(path, root, ignore_patterns):
            continue
        if path.suffix.lower() in {".db", ".sqlite", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".gz", ".lock"}:
            continue
        if path.name.endswith((".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm")):
            continue
        files.append(path)
    return files


def scan_secrets(root: Path, max_files: int = 2000) -> dict[str, Any]:
    findings = []
    ignore_patterns = load_security_ignore_patterns(root)
    files = iter_security_scan_files(root, max_files, ignore_patterns)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for name, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(
                        {
                            "type": name,
                            "path": workspace_relative(path).as_posix(),
                            "line": line_no,
                            "evidence": line[:120],
                        }
                    )
            for entropy_finding in high_entropy_findings(line):
                findings.append(
                    {
                        "type": entropy_finding["type"],
                        "path": workspace_relative(path).as_posix(),
                        "line": line_no,
                        "evidence": entropy_finding["value_preview"],
                        "entropy": entropy_finding["entropy"],
                    }
                )
    return {"checked_files": len(files), "ignored_patterns": ignore_patterns, "findings": findings}


def assess_dangerous_command(command: str | None) -> dict[str, Any]:
    if not command:
        return {"command": None, "risk": "none", "blocked": False, "matches": []}
    matches = [{"type": label, "pattern": pattern.pattern} for pattern, label in DANGEROUS_COMMAND_PATTERNS if pattern.search(command)]
    return {
        "command": command,
        "risk": "high" if matches else "normal",
        "blocked": bool(matches),
        "matches": matches,
        "decision": "requires explicit user approval" if matches else "allowed by default policy",
    }


def permission_policy_report() -> dict[str, Any]:
    return {
        "tool_allowlist": list(SAFE_VERIFICATION_PREFIXES),
        "allow_unsafe_requires_user_approval": True,
        "high_risk_requires_risk_gate": [
            "filesystem deletion",
            "dependency upgrade",
            "database migration",
            "auth or permission change",
            "production or release command",
        ],
    }


def sandbox_strategy_report() -> dict[str, Any]:
    return {
        "workspace_bounded_execution": True,
        "ignore_local_runtime_state": ["memory/index.db", "memory/index.db-*", "sessions/", "logs/", "temp/"],
        "recommend_worktree_for": [
            "large refactor",
            "architecture change",
            "dependency upgrade",
            "database migration",
            "experimental work",
            "multi-agent shared files",
        ],
    }


def cmd_runtime_security_check(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    secret_scan = scan_secrets(root, args.max_files)
    permission_policy = permission_policy_report()
    sandbox_strategy = sandbox_strategy_report()
    dangerous_command = assess_dangerous_command(args.command)
    ok = not secret_scan["findings"] and not dangerous_command["blocked"]
    report = {
        "ok": ok,
        "root": str(root),
        "secret_scan": secret_scan,
        "dangerous_command": dangerous_command,
        "permission_policy": permission_policy,
        "sandbox_strategy": sandbox_strategy,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json(report)


def distribution_channels(root: Path) -> list[dict[str, Any]]:
    repo = str(root)
    return [
        {
            "name": "copy",
            "status": "ready",
            "command": "python .agent-os/scripts/agent-os.py install --target <project>",
            "upgrade": "replace .agent-os then run agent-os doctor, version, migrate",
        },
        {
            "name": "git-clone",
            "status": "ready",
            "command": f"git clone <agent-os-repo-url> {Path('.agent-os')}",
            "upgrade": "git -C .agent-os pull && python .agent-os/scripts/agent-os.py migrate",
        },
        {
            "name": "git-submodule",
            "status": "ready",
            "command": "git submodule add <agent-os-repo-url> .agent-os",
            "upgrade": "git submodule update --remote .agent-os && python .agent-os/scripts/agent-os.py migrate",
        },
        {
            "name": "vscode-plugin",
            "status": "ready",
            "command": "VSCode command: Agent OS: Inject Workspace",
            "upgrade": "plugin calls agent-os install --force and refreshes doctor/dashboard data",
        },
        {
            "name": "package",
            "status": "planned",
            "command": "agent-os install --target <project>",
            "upgrade": "agent-os upgrade --target <project>",
        },
    ]


def cmd_runtime_distribution(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    channels = distribution_channels(root)
    if args.channel:
        channels = [channel for channel in channels if channel["name"] == args.channel]
    ok = bool(channels) and all(channel["status"] in {"ready", "planned"} for channel in channels)
    print_json({"ok": ok, "root": str(root), "channels": channels})


def vscode_integration_protocol(root: Path, project: str) -> dict[str, Any]:
    return {
        "mode": "workspace-injection",
        "project": project,
        "agent_os_dir": ".agent-os",
        "commands": {
            "inject": "python <extension>/agent-os/scripts/agent-os.py install --target ${workspaceFolder} --force",
            "doctor": "python ${workspaceFolder}/.agent-os/scripts/agent-os.py doctor",
            "dashboard": "python ${workspaceFolder}/.agent-os/scripts/agent-os.py dashboard --project <project> --data-output docs/agent-os/dashboard.json",
            "report": "python ${workspaceFolder}/.agent-os/scripts/agent-runtime.py runtime-report --project <project>",
            "quality_trends": "python ${workspaceFolder}/.agent-os/scripts/agent-os.py quality-trends --project <project> --output docs/agent-os/quality-trends.json",
        },
        "panel_data_sources": [
            "runtime-doctor JSON",
            "runtime-dashboard JSON data source",
            "runtime-quality-trends JSON",
            "runtime-report JSON",
        ],
        "boundaries": [
            "The panel observes Agent OS state and may trigger install/doctor/report commands.",
            "The panel is not a chat runtime.",
            "User project execution docs stay under docs/agent-os/.",
            "Project root AGENTS.md remains the bootstrap entry.",
        ],
        "required_capabilities": ["install", "status-panel", "doctor", "dashboard", "report", "runtime-cli"],
    }


def cmd_runtime_vscode_protocol(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    protocol = vscode_integration_protocol(root, args.project)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(protocol, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json({"ok": True, "root": str(root), "protocol": protocol})


def team_workspace_report(root: Path) -> dict[str, Any]:
    policy_state = load_policy_state(root)
    packs = all_policy_packs(root / "policy-packs")
    bootstrap_status, bootstrap_issues = check_bootstrap(root)
    override_points = [
        "project root AGENTS.md",
        ".agent-os/policy-packs/.enabled.json",
        "project-local docs/agent-os/",
        "project-local memory/projects/{project}.md",
    ]
    conflicts = policy_pack_conflicts(packs, policy_state.get("enabled", []))
    return {
        "policy_state": policy_state,
        "policy_packs": packs,
        "bootstrap": {"status": bootstrap_status, "issues": bootstrap_issues, "source": "scripts/agent-os.py embedded PROJECT_AGENTS_TEMPLATE"},
        "override_points": override_points,
        "conflicts": conflicts,
        "ready": bool(packs) and not conflicts and bootstrap_status == "passed",
    }


def cmd_runtime_team_workspace(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    report = team_workspace_report(root)
    print_json({"ok": report["ready"], "root": str(root), "team_workspace": report})


def release_checklist(root: Path, db_path: Path, schema_path: Path) -> dict[str, Any]:
    with connect(db_path) as conn:
        ensure_initialized(conn, schema_path)
        memory_status, memory_issues = check_memory(root, conn)
        runtime_status, runtime_issues = check_runtime(root, conn)
        schema_version = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    doctor_checks = []
    for name, checker in (
        ("directories", check_required_paths),
        ("agents", check_agents_file),
        ("rules", check_rules),
        ("skills", check_skills),
        ("bootstrap", check_bootstrap),
        ("policy-packs", check_policy_pack_health),
        ("security", check_security_health),
    ):
        status, issues = checker(root)
        doctor_checks.append({"name": name, "status": status, "issues": issues})
    doctor_checks.extend(
        [
            {"name": "memory", "status": memory_status, "issues": memory_issues},
            {"name": "runtime", "status": runtime_status, "issues": runtime_issues},
            {
                "name": "schema-version",
                "status": "passed" if schema_version and schema_version["value"] == CURRENT_SCHEMA_VERSION else "failed",
                "issues": [] if schema_version and schema_version["value"] == CURRENT_SCHEMA_VERSION else [f"expected schema {CURRENT_SCHEMA_VERSION}"],
            },
        ]
    )
    security = {
        "secret_scan": scan_secrets(root, max_files=2000),
        "dangerous_command": assess_dangerous_command(None),
    }
    tests = [
        "python -m py_compile scripts/agent-os.py scripts/agent-runtime.py scripts/agent_store.py tests/test_agent_runtime.py",
        "python -m unittest tests.test_agent_runtime",
        "git diff --check",
    ]
    failed = [check for check in doctor_checks if check["status"] != "passed"]
    ok = not failed and not security["secret_scan"]["findings"]
    return {
        "ok": ok,
        "version": read_agent_os_version(root),
        "schema_version": schema_version["value"] if schema_version else None,
        "checks": doctor_checks,
        "security": security,
        "required_tests": tests,
        "failed_checks": failed,
    }


def cmd_runtime_release_check(args: argparse.Namespace) -> None:
    root = args.root.resolve() if args.root else ROOT
    db_path = args.db if not args.root else root / "memory" / "index.db"
    schema_path = args.schema if not args.root else root / "memory" / "schema.sql"
    report = release_checklist(root, db_path, schema_path)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json(report)


def cmd_runtime_run_tool(args: argparse.Namespace) -> None:
    tool_type = classify_tool_type(args.command or args.target, args.tool_type)
    adapter = args.adapter or f"{tool_type}-adapter"
    command = args.command
    target = args.target
    result = "not-run"
    exit_code = None
    stdout_summary = None
    failure_type = None
    failure_detail = None
    duration_ms = 0

    started = time.perf_counter()
    if tool_type == "shell":
        if not command:
            result = "not-run"
            stdout_summary = "shell tool call recorded without local execution."
        else:
            execution = run_shell_adapter(command, args.timeout, args.allow_unsafe)
            result = execution["status"]
            exit_code = execution["exit_code"]
            stdout_summary = execution["stdout_summary"]
            failure_type = execution["failure_type"]
            failure_detail = execution["failure_detail"]
    elif tool_type == "git":
        execution = run_git_adapter(args.git_action or command, target, args.timeout)
        command = command or f"git {args.git_action or 'status'}"
        result = execution["status"]
        exit_code = execution["exit_code"]
        stdout_summary = execution["stdout_summary"]
        failure_type = execution["failure_type"]
        failure_detail = execution["failure_detail"]
    elif tool_type == "api":
        url = target or command
        if not url:
            result = "not-run"
            stdout_summary = "api tool call recorded without URL."
        else:
            execution = run_url_fetch_adapter(
                url=url,
                method=args.method,
                headers=parse_header_values(args.header),
                body=args.body,
                timeout=args.timeout,
                expect_text=args.expect_text,
            )
            command = command or f"{args.method.upper()} {url}"
            target = url
            result = execution["status"]
            exit_code = execution["exit_code"]
            stdout_summary = execution["stdout_summary"]
            failure_type = execution["failure_type"]
            failure_detail = execution["failure_detail"]
    elif tool_type == "browser":
        url = target or command
        if not url:
            result = "not-run"
            stdout_summary = "browser tool call recorded without URL."
        else:
            execution = run_browser_adapter(
                url=url,
                action=args.browser_action,
                selector=args.selector,
                text=args.text,
                timeout=args.timeout,
                expect_text=args.expect_text,
                screenshot_path=args.screenshot_path,
            )
            command = command or f"browser {args.browser_action} {url}"
            target = url
            result = execution["status"]
            exit_code = execution["exit_code"]
            stdout_summary = execution["stdout_summary"]
            failure_type = execution["failure_type"]
            failure_detail = execution["failure_detail"]
    duration_ms = int((time.perf_counter() - started) * 1000)

    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        tool_id = record_tool_run(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            task_id=args.task_id,
            tool_type=tool_type,
            adapter=adapter,
            command=command,
            target=target,
            status=result,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout_summary=stdout_summary,
            failure_type=failure_type,
            failure_detail=failure_detail,
            evidence=args.evidence or stdout_summary,
        )
        record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="KernelStep",
            source="runtime-run-tool",
            summary=f"{tool_type} tool {result}.",
            payload={"tool_id": tool_id, "tool_type": tool_type, "adapter": adapter, "status": result, "failure_type": failure_type, "failure_detail": failure_detail},
            severity="info" if result in {"passed", "not-run"} else "error",
        )
        conn.commit()
    print_json({"ok": result == "passed" or result == "not-run", "id": tool_id, "project": args.project, "tool_type": tool_type, "adapter": adapter, "status": result, "exit_code": exit_code, "duration_ms": duration_ms, "failure_type": failure_type, "failure_detail": failure_detail, "stdout_summary": stdout_summary})


def classify_root_cause(source_type: str, failure_type: str | None, failure_detail: str | None, summary: str) -> str:
    if source_type == "success":
        return "Successful execution path is stable."
    if source_type == "partial":
        return "Task completed partially and needs follow-up."
    if failure_detail in {"assertion", "test-failure"} or failure_type == "implementation":
        return "Implementation behavior does not match expected outcome."
    if failure_detail in {"missing-dependency", "permission", "timeout"} or failure_type == "environment":
        return "Environment or tool execution prevented completion."
    if "plan" in summary.lower() or "review" in summary.lower():
        return "Process or coordination gap affected execution."
    return "Root cause requires more evidence."


def build_reflection_record(
    *,
    project: str,
    source_type: str,
    summary: str,
    evidence: str | None,
    goal_id: str | None = None,
    run_id: str | None = None,
    failure_type: str | None = None,
    failure_detail: str | None = None,
    pattern: str | None = None,
    next_step: str | None = None,
    confidence: float = 0.7,
) -> dict[str, Any]:
    root_cause = classify_root_cause(source_type, failure_type, failure_detail, summary)
    inferred_pattern = pattern
    inferred_next_step = next_step
    if not inferred_pattern:
        if source_type == "failure":
            inferred_pattern = "Add regression coverage and verify the failing chain end-to-end."
        elif source_type == "partial":
            inferred_pattern = "Finish the missing path before treating the capability as complete."
        else:
            inferred_pattern = "Keep the successful path and watch for regressions."
    if not inferred_next_step:
        if source_type == "failure":
            inferred_next_step = "Create or update a regression test, then fix the narrow root cause."
        elif source_type == "partial":
            inferred_next_step = "Plan the missing follow-up work and validate the full chain."
        else:
            inferred_next_step = "Record the stable path as reusable evidence."
    return {
        "project": project,
        "goal_id": goal_id,
        "run_id": run_id,
        "source_type": source_type,
        "root_cause": root_cause,
        "summary": summary,
        "evidence": evidence,
        "pattern": inferred_pattern,
        "next_step": inferred_next_step,
        "confidence": confidence,
    }


def record_reflection(conn, reflection: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO reflections(
            project, goal_id, run_id, source_type, root_cause, summary, evidence, pattern, next_step, confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reflection["project"],
            reflection.get("goal_id"),
            reflection.get("run_id"),
            reflection["source_type"],
            reflection["root_cause"],
            reflection["summary"],
            reflection.get("evidence"),
            reflection.get("pattern"),
            reflection.get("next_step"),
            reflection.get("confidence", 0.7),
        ),
    )
    return cur.lastrowid


def reflection_to_memory_item(reflection: dict[str, Any]) -> dict[str, Any]:
    title = f"Reflection: {reflection['root_cause'][:80]}"
    summary = reflection["summary"]
    pattern = reflection.get("pattern")
    next_step = reflection.get("next_step")
    evidence = reflection.get("evidence")
    lesson_body = f"{summary}\n\nPattern: {pattern or 'n/a'}\nNext step: {next_step or 'n/a'}"
    memory_type = "lesson" if reflection["source_type"] == "failure" else "pattern"
    return {
        "project": reflection["project"],
        "type": memory_type,
        "title": title,
        "summary": summary,
        "problem": reflection["root_cause"],
        "solution": next_step,
        "patterns": pattern,
        "files": None,
        "tags": normalize_csv(["reflection", reflection["source_type"], "agent-os"]),
        "validation": evidence or lesson_body,
        "confidence": reflection.get("confidence", 0.7),
    }


def reflection_to_candidate(reflection: dict[str, Any], memory_item_id: int | None = None) -> dict[str, Any] | None:
    if reflection["source_type"] not in {"failure", "partial"}:
        return None
    pattern = reflection.get("pattern") or reflection["root_cause"]
    candidate_name = normalize_project_slug(pattern)[:60] or "reflection-pattern"
    return {
        "name": candidate_name,
        "project": reflection["project"],
        "goal_id": reflection.get("goal_id"),
        "run_id": reflection.get("run_id"),
        "trigger": reflection["summary"],
        "evidence": reflection.get("evidence") or reflection["root_cause"],
        "validation": reflection.get("next_step") or "Review reflection and validate with a follow-up run.",
        "scope": "Learning from reflections",
        "boundary": "Do not auto-promote to rules or skills without human review.",
        "suggested_skill": None,
        "tags": normalize_csv(["reflection", "candidate", reflection["source_type"]]),
        "status": "candidate",
        "increment": 1,
        "confidence": reflection.get("confidence", 0.7),
        "memory_item_id": memory_item_id,
    }


def learn_from_reflection(conn, reflection: dict[str, Any]) -> dict[str, Any]:
    memory_item = reflection_to_memory_item(reflection)
    cur = conn.execute(
        """
        INSERT INTO memory_items(
            project, type, title, summary, problem, solution, patterns, files, tags,
            validation, confidence, source_session, import_key, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memory_item["project"],
            memory_item["type"],
            memory_item["title"],
            memory_item["summary"],
            memory_item["problem"],
            memory_item["solution"],
            memory_item["patterns"],
            memory_item["files"],
            memory_item["tags"],
            memory_item["validation"],
            memory_item["confidence"],
            reflection.get("run_id"),
            None,
            json.dumps(
                {
                    "source": "reflection",
                    "source_type": reflection["source_type"],
                    "goal_id": reflection.get("goal_id"),
                    "run_id": reflection.get("run_id"),
                    "root_cause": reflection["root_cause"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )
    memory_item_id = cur.lastrowid
    candidate = reflection_to_candidate(reflection, memory_item_id)
    candidate_id = None
    if candidate:
        conn.execute(
            """
            INSERT INTO skill_candidates(
                name, project, goal_id, run_id, trigger, evidence, validation, scope,
                boundary, suggested_skill, tags, status, count, confidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, project) DO UPDATE SET
                goal_id = COALESCE(excluded.goal_id, skill_candidates.goal_id),
                run_id = COALESCE(excluded.run_id, skill_candidates.run_id),
                trigger = excluded.trigger,
                evidence = excluded.evidence,
                validation = excluded.validation,
                scope = excluded.scope,
                boundary = excluded.boundary,
                suggested_skill = COALESCE(excluded.suggested_skill, skill_candidates.suggested_skill),
                tags = excluded.tags,
                status = skill_candidates.status,
                count = skill_candidates.count + 1,
                confidence = MAX(skill_candidates.confidence, excluded.confidence),
                updated_at = datetime('now')
            """,
            (
                candidate["name"],
                candidate["project"],
                candidate["goal_id"],
                candidate["run_id"],
                candidate["trigger"],
                candidate["evidence"],
                candidate["validation"],
                candidate["scope"],
                candidate["boundary"],
                candidate["suggested_skill"],
                candidate["tags"],
                candidate["status"],
                candidate["increment"],
                candidate["confidence"],
            ),
        )
        candidate_row = conn.execute(
            "SELECT id FROM skill_candidates WHERE name = ? AND project = ?",
            (candidate["name"], candidate["project"]),
        ).fetchone()
        candidate_id = candidate_row["id"] if candidate_row else None
        if candidate_id:
            conn.execute(
                """
                INSERT INTO skill_candidate_evidence(candidate_id, project, memory_item_id, evidence, validation)
                VALUES (?, ?, ?, ?, ?)
                """,
                (candidate_id, candidate["project"], memory_item_id, candidate["evidence"], candidate["validation"]),
            )
    return {"memory_item_id": memory_item_id, "candidate_id": candidate_id}


def infer_reflection_from_verification(
    *,
    project: str,
    goal_id: str | None,
    run_id: str | None,
    scope: str | None,
    result: str,
    failure_type: str | None,
    failure_detail: str | None,
    stdout_summary: str | None,
    command: str | None,
) -> dict[str, Any] | None:
    if result not in {"failed", "blocked"}:
        return None
    summary = f"{scope or 'verification'} failed with {failure_type or 'unknown'}"
    evidence = stdout_summary or command or ""
    next_step = "Write or update the smallest regression test, then rerun the failing path."
    return build_reflection_record(
        project=project,
        goal_id=goal_id,
        run_id=run_id,
        source_type="failure",
        summary=summary,
        evidence=evidence,
        failure_type=failure_type,
        failure_detail=failure_detail,
        pattern="Regression path should be captured before the fix is broadened.",
        next_step=next_step,
        confidence=0.85 if failure_type in {"implementation", "environment"} else 0.7,
    )


def cmd_runtime_run_verification(args: argparse.Namespace) -> None:
    command = args.command
    verification_id = args.id
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = None
        failure_detail = None
        if verification_id:
            row = conn.execute("SELECT * FROM verification_runs WHERE id = ?", (verification_id,)).fetchone()
            if not row:
                raise SystemExit(f"Verification run not found: {verification_id}")
            command = command or row["command"]
        if not command:
            raise SystemExit("Expected --command or --id with stored command")

        if not command_is_allowed(command, args.allow_unsafe):
            result = "blocked"
            exit_code = None
            stdout_summary = "Command blocked by safe verification prefix policy."
            failure_type = "environment"
            failure_detail = "policy-blocked"
        else:
            completed = subprocess.run(command, cwd=ROOT, shell=True, text=True, capture_output=True, timeout=args.timeout)
            output = f"{completed.stdout}\n{completed.stderr}".strip()
            result = "passed" if completed.returncode == 0 else "failed"
            exit_code = completed.returncode
            stdout_summary = summarize_output(output)
            failure_profile = classify_failure_detail(exit_code, output, command)
            failure_type = failure_profile["type"]
            failure_detail = failure_profile["detail"]

        if verification_id:
            conn.execute(
                """
                UPDATE verification_runs
                SET result = ?, exit_code = ?, stdout_summary = ?,
                    failure_type = ?, ran_at = datetime('now'), evidence = ?
                WHERE id = ?
                """,
                (result, exit_code, stdout_summary, failure_type, args.evidence or stdout_summary, verification_id),
            )
        elif args.record:
            cur = conn.execute(
                """
                INSERT INTO verification_runs(
                    project, goal_id, task_id, scope, command, result, evidence,
                    exit_code, stdout_summary, failure_type, ran_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    args.scope,
                    command,
                    result,
                    args.evidence or stdout_summary,
                    exit_code,
                    stdout_summary,
                    failure_type,
                ),
            )
            verification_id = cur.lastrowid
        event_type = "VerificationPassed" if result == "passed" else "VerificationFailed"
        severity = "info" if result == "passed" else "error"
        reflection_id = None
        record_event(
            conn,
            project=args.project,
            goal_id=args.goal_id or (row["goal_id"] if row else None),
            task_id=args.task_id or (row["task_id"] if row else None),
            event_type=event_type,
            source="runtime-run-verification",
            summary=f"{args.scope}: {result}",
            payload={
                "verification_id": verification_id,
                "command": command,
                "result": result,
                "exit_code": exit_code,
                "failure_type": failure_type,
                "failure_detail": failure_detail,
            },
            severity=severity,
        )
        if result in {"failed", "blocked"}:
            reflection = infer_reflection_from_verification(
                project=args.project,
                goal_id=args.goal_id or (row["goal_id"] if row else None),
                run_id=None,
                scope=args.scope,
                result=result,
                failure_type=failure_type,
                failure_detail=failure_detail,
                stdout_summary=stdout_summary,
                command=command,
            )
            if reflection:
                reflection_id = record_reflection(conn, reflection)
                learning = learn_from_reflection(conn, reflection)
                record_event(
                    conn,
                    project=args.project,
                    goal_id=args.goal_id or (row["goal_id"] if row else None),
                    task_id=args.task_id or (row["task_id"] if row else None),
                    event_type="MemoryUpdated",
                    source="runtime-run-verification",
                    summary="Reflection record created from verification failure.",
                    payload={
                        "reflection_id": reflection_id,
                        "memory_item_id": learning["memory_item_id"],
                        "candidate_id": learning["candidate_id"],
                        "root_cause": reflection["root_cause"],
                    },
                )
        conn.commit()

    print_json(
        {
            "ok": result == "passed",
            "id": verification_id,
            "project": args.project,
            "command": command,
            "result": result,
            "exit_code": exit_code,
            "failure_type": failure_type,
            "failure_detail": failure_detail,
            "stdout_summary": stdout_summary,
            "reflection_id": reflection_id,
            "learning": learning if result in {"failed", "blocked"} and reflection else None,
        }
    )


def cmd_runtime_create_checkpoint(args: argparse.Namespace) -> None:
    checkpoint = args.checkpoint
    if not checkpoint:
        try:
            completed = subprocess.run(
                "git rev-parse --short HEAD",
                cwd=ROOT,
                shell=True,
                text=True,
                capture_output=True,
                timeout=10,
            )
            checkpoint = completed.stdout.strip() if completed.returncode == 0 else "manual-checkpoint-required"
        except subprocess.SubprocessError:
            checkpoint = "manual-checkpoint-required"
    strategy = args.strategy or f"Use checkpoint {checkpoint}; revert affected files if validation fails."
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO recovery_points(
                project, goal_id, task_id, strategy, files, status, evidence, checkpoint_ref
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.project,
                args.goal_id,
                args.task_id,
                strategy,
                normalize_csv(args.files),
                "available",
                args.evidence or "runtime-create-checkpoint",
                checkpoint,
            ),
        )
        record_event(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="RecoveryCheckpointCreated",
            source="runtime-create-checkpoint",
            summary="Recovery checkpoint created.",
            payload={
                "checkpoint_ref": checkpoint,
                "strategy": strategy,
                "files": normalize_csv(args.files),
            },
        )
        conn.commit()
    print_json({"ok": True, "id": cur.lastrowid, "project": args.project, "checkpoint_ref": checkpoint, "strategy": strategy})


def cmd_runtime_mark_recovery(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conn.execute(
            """
            UPDATE recovery_points
            SET status = ?,
                applied_at = CASE WHEN ? = 'used' THEN datetime('now') ELSE applied_at END,
                obsolete_reason = COALESCE(?, obsolete_reason)
            WHERE id = ?
            """,
            (args.status, args.status, args.reason, args.id),
        )
        row = conn.execute(
            "SELECT project, goal_id, task_id, status, strategy FROM recovery_points WHERE id = ?",
            (args.id,),
        ).fetchone()
        if row:
            record_event(
                conn,
                project=row["project"],
                goal_id=row["goal_id"],
                task_id=row["task_id"],
                event_type="RecoveryMarked",
                source="runtime-mark-recovery",
                summary=f"Recovery point marked {args.status}.",
                payload={
                    "status": args.status,
                    "reason": args.reason,
                    "strategy": row["strategy"],
                },
            )
        conn.commit()
    print_json({"ok": True, "id": args.id, "status": args.status})


def cmd_runtime_reflect(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        reflection = build_reflection_record(
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            source_type=args.source_type,
            summary=args.summary,
            evidence=args.evidence,
            failure_type=args.failure_type,
            failure_detail=args.failure_detail,
            pattern=args.pattern,
            next_step=args.next_step,
            confidence=args.confidence,
        )
        reflection_id = record_reflection(conn, reflection)
        learning = learn_from_reflection(conn, reflection)
        record_event(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            event_type="MemoryUpdated",
            source="runtime-reflect",
            summary="Reflection record created.",
            payload={
                "reflection_id": reflection_id,
                "memory_item_id": learning["memory_item_id"],
                "candidate_id": learning["candidate_id"],
                "source_type": args.source_type,
                "root_cause": reflection["root_cause"],
            },
        )
        conn.commit()
    print_json({"ok": True, "id": reflection_id, "reflection": reflection, "learning": learning})


def cmd_runtime_final_check(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        goal_id = args.goal_id
        context_id = None
        goal = None
        if args.run_id:
            run = conn.execute(
                "SELECT goal_id, context_id FROM runtime_runs WHERE id = ? AND project = ?",
                (args.run_id, args.project),
            ).fetchone()
            if not run:
                raise SystemExit(f"Runtime run not found: {args.run_id}")
            goal_id = goal_id or run["goal_id"]
            context_id = run["context_id"]
        if goal_id:
            goal = conn.execute(
                "SELECT * FROM agent_goals WHERE id = ? AND project = ?",
                (goal_id, args.project),
            ).fetchone()

        goal_clause = " AND goal_id = ?" if goal_id else ""
        goal_params: list[Any] = [args.project] + ([goal_id] if goal_id else [])
        workspace = workspace_snapshot(args.project)
        tasks = conn.execute(
            f"SELECT * FROM agent_tasks WHERE project = ?{goal_clause} ORDER BY order_index, created_at",
            goal_params,
        ).fetchall()
        policies = conn.execute(
            f"SELECT * FROM policy_decisions WHERE project = ?{goal_clause} ORDER BY created_at",
            goal_params,
        ).fetchall()
        verifications = conn.execute(
            f"SELECT * FROM verification_runs WHERE project = ?{goal_clause} ORDER BY created_at",
            goal_params,
        ).fetchall()
        recoveries = conn.execute(
            f"SELECT * FROM recovery_points WHERE project = ?{goal_clause} ORDER BY created_at",
            goal_params,
        ).fetchall()
        recovery_required = bool(recoveries) or any(
            row["decision_type"] == "rollback" and row["decision"] == "required"
            for row in policies
        )
        recovery_ready = any(
            row["status"] in {"available", "used"} or row["checkpoint_ref"]
            for row in recoveries
        )
        memory_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM memory_items
            WHERE project = ? OR project = '*'
            """,
            (normalize_project_slug(args.project),),
        ).fetchone()["count"]
        verification_checks = verification_checks_for(
            [row["task_layer"] for row in tasks if row["task_layer"]],
            goal["current_phase"] if goal and goal["current_phase"] else "L1",
            [row["title"] for row in tasks],
        )
        open_tasks = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM agent_tasks
            WHERE project = ?{goal_clause}
              AND status IN ('pending', 'in_progress', 'blocked')
            """,
            goal_params,
        ).fetchone()["count"]
        docs_freshness = docs_freshness_for_request(
            goal["objective"] if goal else args.project,
            [row["title"] for row in tasks] + [row["decision"] for row in policies],
            workspace,
        )
        knowledge_conflict = knowledge_conflict_from_state(
            project=args.project,
            name=goal["objective"] if goal else args.project,
            memory_hits=[row["title"] for row in conn.execute(
                """
                SELECT title
                FROM memory_items
                WHERE project = ? OR project = '*'
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (normalize_project_slug(args.project),),
            ).fetchall()],
            docs_freshness=docs_freshness,
            workspace=workspace,
            code_evidence=[row["title"] for row in tasks],
            runtime_evidence=[row["summary"] for row in conn.execute(
                """
                SELECT summary
                FROM agent_events
                WHERE project = ?
                ORDER BY created_at DESC
                LIMIT 5
                """,
                (args.project,),
            ).fetchall()],
        )
        stage_inputs = pipeline_stages_for(
            workspace=workspace,
            decisions=[row_to_dict(row) for row in policies],
            verification_checks=verification_checks,
            docs_required=workspace["docs"]["exists"] or docs_freshness["must_update"],
            memory_required=memory_count > 0,
            open_tasks=open_tasks,
            recovery_required=recovery_required,
            recoveries=[row_to_dict(row) for row in recoveries],
        )
    verification = {row["result"]: 0 for row in verifications}
    for row in verifications:
        verification[row["result"]] = verification.get(row["result"], 0) + 1
    missing: list[str] = []
    if not stage_inputs or not any(stage["name"] == "plan" for stage in stage_inputs):
        missing.append("pipeline plan stage")
    if not any(stage["name"] == "observe" for stage in stage_inputs):
        missing.append("pipeline observe stage")
    if not verification_checks:
        missing.append("verification plan")
    if not verifications:
        missing.append("verification records")
    if not policies:
        missing.append("policy decisions")
    if knowledge_conflict["conflict"]:
        missing.append("knowledge conflict")
    if args.require_docs:
        if docs_freshness["stale_docs"]:
            missing.append("docs stale")
        elif docs_freshness["missing_docs"]:
            missing.append("docs missing")
        elif not workspace["docs"]["exists"]:
            missing.append("documentation workspace")
    if args.require_memory and memory_count == 0:
        missing.append("memory items")
    if args.require_recovery and not recoveries:
        missing.append("recovery point")
    if args.require_skills and not conn.execute(
        f"SELECT 1 FROM skill_recommendations WHERE project = ?{goal_clause} LIMIT 1",
        goal_params,
    ).fetchone():
        missing.append("skill recommendations")
    if open_tasks:
        missing.append(f"{open_tasks} open runtime task(s)")
    passed = not missing and verification.get("failed", 0) == 0 and verification.get("blocked", 0) == 0
    print_json(
        {
            "ok": passed,
            "project": args.project,
            "goal_id": goal_id,
            "run_id": args.run_id,
            "missing": missing,
            "workspace": workspace,
            "docs_freshness": docs_freshness,
            "knowledge_conflict": knowledge_conflict,
            "pipeline_stages": stage_inputs,
            "verification": verification,
            "recovery_count": len(recoveries),
            "recovery_ready": recovery_ready,
            "docs_workspace_exists": workspace["docs"]["exists"],
            "memory_item_count": memory_count,
            "skill_recommendation_count": conn.execute(
                f"SELECT COUNT(*) AS count FROM skill_recommendations WHERE project = ?{goal_clause}",
                goal_params,
            ).fetchone()["count"],
            "open_tasks": open_tasks,
        }
    )


def cmd_runtime_review_improvements(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        candidates = conn.execute(
            """
            SELECT name, project, goal_id, run_id, trigger, evidence, validation, scope, boundary,
                   status, count, confidence
            FROM skill_candidates
            WHERE (? IS NULL OR project = ? OR project = '*')
              AND (? IS NULL OR goal_id = ? OR goal_id IS NULL)
              AND (? IS NULL OR run_id = ? OR run_id IS NULL)
              AND status IN ('candidate', 'reviewing', 'approved')
            ORDER BY count DESC, updated_at DESC
            LIMIT ?
            """,
            (args.project, args.project, args.goal_id, args.goal_id, args.run_id, args.run_id, args.limit),
        ).fetchall()
        reviews = []
        for row in candidates:
            has_boundary = bool(row["scope"] and row["boundary"])
            has_validation = bool(row["validation"])
            enough_count = row["count"] >= args.min_count
            if enough_count and has_validation and has_boundary:
                recommendation = "ready-for-human-review"
            elif enough_count:
                recommendation = "needs-scope-boundary-or-validation"
            else:
                recommendation = "keep-as-candidate"
            reviews.append({**row_to_dict(row), "recommendation": recommendation})
            if args.record:
                conn.execute(
                    """
                    INSERT INTO improvement_reviews(
                        project, goal_id, run_id, candidate_name, source_type, trigger, evidence,
                        scope, boundary, status, review_result
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project, candidate_name, source_type) DO UPDATE SET
                        goal_id = excluded.goal_id,
                        run_id = excluded.run_id,
                        trigger = excluded.trigger,
                        evidence = excluded.evidence,
                        scope = excluded.scope,
                        boundary = excluded.boundary,
                        status = excluded.status,
                        review_result = excluded.review_result,
                        updated_at = datetime('now')
                    """,
                    (
                        row["project"],
                        args.goal_id or row["goal_id"],
                        args.run_id or row["run_id"],
                        row["name"],
                        "skill",
                        row["trigger"],
                        row["evidence"],
                        row["scope"],
                        row["boundary"],
                        "reviewing" if recommendation == "ready-for-human-review" else "candidate",
                        recommendation,
                    ),
                )
        if args.record:
            conn.commit()
    print_json({"ok": True, "project": args.project, "goal_id": args.goal_id, "run_id": args.run_id, "reviews": reviews})


def cmd_runtime_report(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        goal_id = args.goal_id
        run = None
        if args.run_id:
            run = conn.execute(
                "SELECT * FROM runtime_runs WHERE id = ? AND project = ?",
                (args.run_id, args.project),
            ).fetchone()
            if not run:
                raise SystemExit(f"Runtime run not found: {args.run_id}")
            goal_id = goal_id or run["goal_id"]
        goal = None
        if goal_id:
            goal = conn.execute(
                "SELECT * FROM agent_goals WHERE id = ? AND project = ?",
                (goal_id, args.project),
            ).fetchone()
        goal_clause = " AND goal_id = ?" if goal_id else ""
        params: list[Any] = [args.project] + ([goal_id] if goal_id else [])
        tasks = conn.execute(
            f"SELECT id, title, status, assigned_role, order_index FROM agent_tasks WHERE project = ?{goal_clause} ORDER BY order_index, created_at",
            params,
        ).fetchall()
        policies = conn.execute(
            f"SELECT decision_type, decision, severity, blocking, rationale FROM policy_decisions WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        verifications = conn.execute(
            f"SELECT scope, command, result, failure_type, stdout_summary FROM verification_runs WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        recoveries = conn.execute(
            f"SELECT id, status, checkpoint_ref, strategy, files FROM recovery_points WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        recovery_ready = any(
            row["status"] in {"available", "used"} or row["checkpoint_ref"]
            for row in recoveries
        )
        open_tasks = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM agent_tasks
            WHERE project = ?{goal_clause}
              AND status IN ('pending', 'in_progress', 'blocked')
            """,
            params,
        ).fetchone()["count"]
        workspace = workspace_snapshot(args.project)
        docs_freshness = docs_freshness_for_request(args.project, [row["title"] for row in tasks], workspace)
        verification_checks = verification_checks_for(
            [row["assigned_role"] for row in tasks if row["assigned_role"]],
            "L3" if goal_id else "L1",
            [row["title"] for row in tasks],
        )
        pipeline_stages = pipeline_stages_for(
            workspace=workspace,
            decisions=[row_to_dict(row) for row in policies],
            verification_checks=verification_checks,
            docs_required=workspace["docs"]["exists"] or docs_freshness["must_update"],
            memory_required=bool(goal_id),
            open_tasks=open_tasks,
            recovery_required=bool(recoveries) or any(
                row["decision_type"] == "rollback" and row["decision"] == "required"
                for row in policies
            ),
            recoveries=[row_to_dict(row) for row in recoveries],
        )
        skills = conn.execute(
            """
            SELECT skill_name, rationale, status
            FROM skill_recommendations
            WHERE project = ?
              AND (? IS NULL OR goal_id = ?)
              AND (? IS NULL OR run_id = ?)
            ORDER BY created_at
            """,
            (args.project, goal_id, goal_id, args.run_id, args.run_id),
        ).fetchall()
    print_json(
        {
            "ok": True,
            "project": args.project,
            "run": row_to_dict(run) if run else None,
            "goal": row_to_dict(goal) if goal else None,
            "tasks": [row_to_dict(row) for row in tasks],
            "policies": [row_to_dict(row) for row in policies],
            "verifications": [row_to_dict(row) for row in verifications],
            "recoveries": [row_to_dict(row) for row in recoveries],
            "skills": [row_to_dict(row) for row in skills],
            "workspace": workspace,
            "docs_freshness": docs_freshness,
            "pipeline_stages": pipeline_stages,
            "recovery_ready": recovery_ready,
        }
    )


def cmd_runtime_pipeline(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        goal_id = args.goal_id
        run = None
        if args.run_id:
            run = conn.execute(
                "SELECT * FROM runtime_runs WHERE id = ? AND project = ?",
                (args.run_id, args.project),
            ).fetchone()
            if not run:
                raise SystemExit(f"Runtime run not found: {args.run_id}")
            goal_id = goal_id or run["goal_id"]
        goal = None
        if goal_id:
            goal = conn.execute(
                "SELECT * FROM agent_goals WHERE id = ? AND project = ?",
                (goal_id, args.project),
            ).fetchone()
        goal_clause = " AND goal_id = ?" if goal_id else ""
        params: list[Any] = [args.project] + ([goal_id] if goal_id else [])
        tasks = conn.execute(
            f"SELECT * FROM agent_tasks WHERE project = ?{goal_clause} ORDER BY order_index, created_at",
            params,
        ).fetchall()
        policies = conn.execute(
            f"SELECT * FROM policy_decisions WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        verification_rows = conn.execute(
            f"SELECT * FROM verification_runs WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        recoveries = conn.execute(
            f"SELECT * FROM recovery_points WHERE project = ?{goal_clause} ORDER BY created_at",
            params,
        ).fetchall()
        open_tasks = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM agent_tasks
            WHERE project = ?{goal_clause}
              AND status IN ('pending', 'in_progress', 'blocked')
            """,
            params,
        ).fetchone()["count"]
        workspace = workspace_snapshot(args.project)
        verification_checks = verification_checks_for(
            [row["task_layer"] for row in tasks if row["task_layer"]],
            goal["current_phase"] if goal and goal["current_phase"] else "L1",
            [row["title"] for row in tasks],
        )
        pipeline_stages = pipeline_stages_for(
            workspace=workspace,
            decisions=[row_to_dict(row) for row in policies],
            verification_checks=verification_checks,
            docs_required=workspace["docs"]["exists"],
            memory_required=bool(goal_id),
            open_tasks=open_tasks,
            recovery_required=bool(recoveries) or any(
                row["decision_type"] == "rollback" and row["decision"] == "required"
                for row in policies
            ),
            recoveries=[row_to_dict(row) for row in recoveries],
        )
    print_json(
        {
            "ok": True,
            "project": args.project,
            "goal": row_to_dict(goal) if goal else None,
            "run": row_to_dict(run) if run else None,
            "stages": pipeline_stages,
            "verification_checks": verification_checks,
            "open_tasks": open_tasks,
            "workspace": workspace,
            "tasks": [row_to_dict(row) for row in tasks],
            "policies": [row_to_dict(row) for row in policies],
            "verifications": [row_to_dict(row) for row in verification_rows],
            "recoveries": [row_to_dict(row) for row in recoveries],
        }
    )


def cmd_runtime_run(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    project = context["project"]
    capability_name = args.capability or normalize_project_slug(args.request)[:60]
    goal_id = args.goal_id or f"goal-{uuid.uuid4().hex[:8]}"
    run_id = args.id or f"run-{uuid.uuid4().hex[:8]}"

    layer_terms = args.term or split_terms(None, args.request)
    fake_scan_args = argparse.Namespace(
        project=project,
        goal_id=goal_id,
        name=capability_name,
        term=layer_terms,
        roots=args.roots,
        max_files=args.max_files,
        max_hits=args.max_hits,
        require_data=args.require_data,
        require_verification=args.require_verification,
        use_memory=args.use_memory,
        record=False,
        db=args.db,
        schema=args.schema,
    )
    terms = split_terms(fake_scan_args.term, fake_scan_args.name)
    roots = resolve_scan_roots(fake_scan_args.roots)
    layer_hits = {"frontend": [], "api": [], "backend": [], "data": [], "verification": []}
    route_tokens = {"frontend": set(), "api": set(), "backend": set(), "data": set(), "verification": set()}
    files_scanned = 0
    files_matched = 0
    for root in roots:
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
            if files_scanned >= fake_scan_args.max_files:
                break
            if not path.is_file() or should_skip_scan_path(path) or not is_text_candidate(path):
                continue
            files_scanned += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            haystack = f"{path.as_posix().lower()}\n{text.lower()}"
            if not any(term in haystack for term in terms):
                continue
            files_matched += 1
            for layer in classify_capability_file(path, text):
                route_tokens[layer].update(extract_route_tokens(text))
                if len(layer_hits[layer]) < fake_scan_args.max_hits:
                    layer_hits[layer].append(workspace_relative(path).as_posix())

    memory_hits: list[str] = []
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.use_memory:
            memory_hits = search_memory_for_capability(conn, project, " ".join(terms), args.max_hits)
    capability_status = derive_capability_status(
        layer_hits,
        require_data=args.require_data,
        require_verification=args.require_verification,
    )
    linkage = capability_linkage(layer_hits, route_tokens)
    if layer_hits["api"] and layer_hits["backend"] and not linkage["api_backend_overlap"]:
        capability_status = "broken-chain"
    if capability_status == "absent" and memory_hits:
        capability_status = "unconfirmed"
    confidence = confidence_for_capability(capability_status, layer_hits, memory_hits)
    policy_signals = list(dict.fromkeys((args.signal or []) + workspace_risk_signals(context["files"])))
    decisions = policy_decisions_for(
        scale=context["scale"],
        capability_status=capability_status,
        task_layers=context["task_layers"],
        signals=policy_signals,
    )
    tasks = plan_tasks_for(context, capability_status)
    skills = recommend_skills(context["task_layers"], context["stack"])
    checks = verification_checks_for(context["task_layers"], context["scale"], context["files"])
    recovery_strategy = None
    if context["scale"] in {"L3", "L4"} or any(item["decision_type"] == "rollback" and item["decision"] == "required" for item in decisions):
        recovery_strategy = "Create or identify checkpoint before execution; revert affected files and rerun verification on failure."
    next_action = "execute-planned-tasks"
    if recovery_strategy:
        next_action = "prepare-recovery"

    context_id = None
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            record_event(
                conn,
                project=project,
                run_id=run_id,
                goal_id=goal_id,
                event_type="UserRequest",
                source="runtime-run",
                summary=args.request,
                payload={"files": context["files"], "capability": capability_name},
            )
            context_id = record_runtime_context(conn, context)
            record_event(
                conn,
                project=project,
                run_id=run_id,
                goal_id=goal_id,
                event_type="ContextReady",
                source="runtime-run",
                summary=f"Detected {context['scale']} {context['intent']} task for {context['stack']}.",
                payload=context,
            )
            conn.execute(
                """
                INSERT INTO agent_goals(id, project, objective, status, priority, current_phase, success_criteria, evidence, source_request)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    objective = excluded.objective,
                    current_phase = excluded.current_phase,
                    evidence = excluded.evidence,
                    source_request = excluded.source_request,
                    updated_at = datetime('now')
                """,
                (
                    goal_id,
                    project,
                    args.request,
                    "active",
                    "normal",
                    "planning",
                    "Runtime loop has context, capability, policy, tasks, verification, recovery, and final gate evidence.",
                    "runtime-run",
                    args.request,
                ),
            )
            record_event(
                conn,
                project=project,
                run_id=run_id,
                goal_id=goal_id,
                event_type="GoalCreated",
                source="runtime-run",
                summary=f"Goal {goal_id} created for runtime loop.",
                payload={"objective": args.request, "success_criteria": "Runtime loop has context, capability, policy, tasks, verification, recovery, and final gate evidence."},
            )
            conn.execute(
                """
                INSERT INTO capability_nodes(
                    project, name, status, frontend, api, backend, data_state,
                    verification, evidence, confidence, memory_evidence, code_evidence, test_evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, name) DO UPDATE SET
                    status = excluded.status,
                    frontend = excluded.frontend,
                    api = excluded.api,
                    backend = excluded.backend,
                    data_state = excluded.data_state,
                    verification = excluded.verification,
                    evidence = excluded.evidence,
                    confidence = excluded.confidence,
                    memory_evidence = excluded.memory_evidence,
                    code_evidence = excluded.code_evidence,
                    test_evidence = excluded.test_evidence,
                    updated_at = datetime('now')
                """,
                (
                    project,
                    capability_name,
                    capability_status,
                    compact_list(layer_hits["frontend"]),
                    compact_list(layer_hits["api"]),
                    compact_list(layer_hits["backend"]),
                    compact_list(layer_hits["data"]),
                    compact_list(layer_hits["verification"]),
                    f"runtime-run scanned files={files_scanned}, matched={files_matched}; linkage={linkage['evidence']}",
                    confidence,
                    compact_list(memory_hits),
                    compact_list(layer_hits["frontend"] + layer_hits["api"] + layer_hits["backend"] + layer_hits["data"]),
                    compact_list(layer_hits["verification"]),
                ),
            )
            conn.execute(
                """
                INSERT INTO runtime_runs(
                    id, project, request, goal_id, status, context_id, capability_name,
                    capability_status, execution_mode, summary, next_action
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    context_id = excluded.context_id,
                    capability_name = excluded.capability_name,
                    capability_status = excluded.capability_status,
                    execution_mode = excluded.execution_mode,
                    summary = excluded.summary,
                    next_action = excluded.next_action,
                    updated_at = datetime('now')
                """,
                (
                    run_id,
                    project,
                    args.request,
                    goal_id,
                    "ready",
                    context_id,
                    capability_name,
                    capability_status,
                    next((item["decision"] for item in decisions if item["decision_type"] == "execution-mode"), None),
                    "Runtime loop prepared context, capability, policy, tasks, skill recommendations, verification, and recovery plan.",
                    next_action,
                ),
            )
            record_event(
                conn,
                project=project,
                run_id=run_id,
                goal_id=goal_id,
                event_type="RunCreated",
                source="runtime-run",
                summary=f"Run {run_id} is ready.",
                payload={"capability_status": capability_status, "execution_mode": next((item["decision"] for item in decisions if item["decision_type"] == "execution-mode"), None)},
            )
            for item in decisions:
                conn.execute(
                    """
                    INSERT INTO policy_decisions(project, goal_id, decision_type, decision, rationale, evidence, severity, blocking)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project,
                        goal_id,
                        item["decision_type"],
                        item["decision"],
                        item["rationale"],
                        context["evidence"],
                        item.get("severity", "normal"),
                        int(item.get("blocking", "0")),
                    ),
                )
            for index, task in enumerate(tasks, start=1):
                task_id = f"{run_id}-task-{index}"
                conn.execute(
                    """
                    INSERT INTO agent_tasks(
                        id, goal_id, project, title, task_layer, scale, status,
                        assigned_role, plan, evidence, order_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        goal_id,
                        project,
                        task["title"],
                        task["task_layer"],
                        context["scale"],
                        "pending",
                        task["assigned_role"],
                        task["plan"],
                        "runtime-run generated task plan",
                        index,
                    ),
                )
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    task_id=task_id,
                    event_type="TaskPlanned",
                    source="runtime-run",
                    summary=task["title"],
                    payload=task,
                )
            for item in skills:
                conn.execute(
                    """
                    INSERT INTO skill_recommendations(project, goal_id, run_id, task_layers, stack, skill_name, rationale, evidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project,
                        goal_id,
                        run_id,
                        normalize_csv(context["task_layers"]),
                        context["stack"],
                        item["skill_name"],
                        item["rationale"],
                        "runtime-run",
                    ),
                )
            for check in checks:
                conn.execute(
                    """
                    INSERT INTO verification_runs(project, goal_id, scope, command, result, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project, goal_id, check["scope"], check["command"], "not-run", check["rationale"]),
                )
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="VerificationPlanned",
                    source="runtime-run",
                    summary=check["scope"],
                    payload=check,
                )
            if recovery_strategy:
                conn.execute(
                    """
                    INSERT INTO recovery_points(project, goal_id, strategy, files, status, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project, goal_id, recovery_strategy, normalize_csv(context["files"]), "planned", "runtime-run recovery planning"),
                )
                record_event(
                    conn,
                    project=project,
                    run_id=run_id,
                    goal_id=goal_id,
                    event_type="RecoveryPlanned",
                    source="runtime-run",
                    summary="Recovery path prepared before execution.",
                    payload={
                        "strategy": recovery_strategy,
                        "files": normalize_csv(context["files"]),
                        "checkpoint_required": True,
                    },
                )
            conn.commit()

    print_json(
        {
            "ok": True,
            "run_id": run_id,
            "goal_id": goal_id,
            "context_id": context_id,
            "context": context,
            "capability": {
                "name": capability_name,
                "status": capability_status,
                "confidence": confidence,
                "layers": layer_hits,
                "linkage": linkage,
                "memory_hits": memory_hits,
            },
            "decisions": decisions,
            "tasks": tasks,
            "skills": skills,
            "verification_checks": checks,
            "recovery_strategy": recovery_strategy,
            "next_action": next_action,
        }
    )


def cmd_runtime_orchestrate(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    context = context_for_request(args.project, args.request, args.files)
    project = context["project"]
    goal_id = args.goal_id or f"goal-{uuid.uuid4().hex[:8]}"
    run_id = args.run_id or f"run-{uuid.uuid4().hex[:8]}"
    capability_name = args.capability or normalize_project_slug(args.request)[:60]
    capability_status = "unconfirmed"
    decisions = policy_decisions_for(
        scale=context["scale"],
        capability_status=capability_status,
        task_layers=context["task_layers"],
        signals=list(dict.fromkeys((args.signal or []) + workspace_risk_signals(context["files"]))),
    )
    tasks = plan_tasks_for(context, capability_status)
    skills = recommend_skills(context["task_layers"], context["stack"], args.request)
    checks = verification_checks_for(context["task_layers"], context["scale"], context["files"])
    subagent_chain = subagent_chain_for(["planner", "executor", "reviewer", "verifier"])
    verifier_command = args.verification_command

    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="UserRequest", source="runtime-orchestrate", summary=args.request, payload={"files": context["files"]})
        context_id = record_runtime_context(conn, context)
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="ContextReady", source="runtime-orchestrate", summary=f"Context ready for {context['scale']} task.", payload=context)
        conn.execute(
            """
            INSERT INTO agent_goals(id, project, objective, status, priority, current_phase, success_criteria, evidence, source_request)
            VALUES (?, ?, ?, 'active', 'normal', 'executing', ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                objective = excluded.objective,
                current_phase = excluded.current_phase,
                evidence = excluded.evidence,
                source_request = excluded.source_request,
                updated_at = datetime('now')
            """,
            (
                goal_id,
                project,
                args.request,
                "Runtime orchestrator completes context, policy, skill, model, subagent, verification, metrics, and trace chain.",
                "runtime-orchestrate",
                args.request,
            ),
        )
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="GoalCreated", source="runtime-orchestrate", summary=f"Goal {goal_id} created.", payload={"objective": args.request})
        conn.execute(
            """
            INSERT INTO runtime_runs(
                id, project, request, goal_id, status, context_id, capability_name,
                capability_status, execution_mode, summary, next_action
            )
            VALUES (?, ?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                context_id = excluded.context_id,
                capability_name = excluded.capability_name,
                capability_status = excluded.capability_status,
                execution_mode = excluded.execution_mode,
                summary = excluded.summary,
                next_action = excluded.next_action,
                updated_at = datetime('now')
            """,
            (
                run_id,
                project,
                args.request,
                goal_id,
                context_id,
                capability_name,
                capability_status,
                "orchestrated",
                "Runtime orchestrator is executing the full chain.",
                "verify-and-trace",
            ),
        )
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="RunCreated", source="runtime-orchestrate", summary=f"Run {run_id} started.", payload={"execution_mode": "orchestrated"})

        for decision in decisions:
            conn.execute(
                """
                INSERT INTO policy_decisions(project, goal_id, decision_type, decision, rationale, evidence, severity, blocking)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project,
                    goal_id,
                    decision["decision_type"],
                    decision["decision"],
                    decision["rationale"],
                    context["evidence"],
                    decision.get("severity", "normal"),
                    int(decision.get("blocking", "0")),
                ),
            )

        for index, task in enumerate(tasks, start=1):
            task_id = f"{run_id}-task-{index}"
            conn.execute(
                """
                INSERT INTO agent_tasks(id, goal_id, project, title, task_layer, scale, status, assigned_role, plan, evidence, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, goal_id, project, task["title"], task["task_layer"], context["scale"], "completed" if index <= 3 else "pending", task["assigned_role"], task["plan"], "runtime-orchestrate generated task", index),
            )
            record_event(conn, project=project, goal_id=goal_id, run_id=run_id, task_id=task_id, event_type="TaskPlanned", source="runtime-orchestrate", summary=task["title"], payload=task)

        for item in skills:
            conn.execute(
                """
                INSERT INTO skill_recommendations(project, goal_id, run_id, task_layers, stack, skill_name, rationale, evidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project, goal_id, run_id, normalize_csv(context["task_layers"]), context["stack"], item["skill_name"], item["rationale"], "runtime-orchestrate"),
            )

        manifests = validate_skill_runtime(ROOT / "skills", None)
        dependency_graph = build_skill_dependency_graph(manifests)
        conflicts = detect_skill_conflicts(manifests, [manifest["skill_name"] for manifest in manifests])
        skill_blockers: list[str] = []
        for manifest in manifests:
            if manifest["status"] != "valid":
                skill_blockers.append(f"{manifest['skill_name']}: {manifest['status']}")
            missing_dependencies = dependency_graph.get(manifest["skill_name"], {}).get("missing_dependencies", [])
            if missing_dependencies:
                skill_blockers.append(f"{manifest['skill_name']}: missing dependencies {', '.join(missing_dependencies)}")
            conn.execute(
                """
                INSERT INTO skill_manifests(
                    project, goal_id, run_id, skill_name, version, description, path, status,
                    dependencies_json, triggers_json, conflicts_json, issues_json, warnings_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project,
                    goal_id,
                    run_id,
                    manifest["skill_name"],
                    manifest.get("version"),
                    manifest["description"],
                    manifest["path"],
                    manifest["status"],
                    json.dumps(manifest.get("dependencies", []), ensure_ascii=False),
                    json.dumps(manifest.get("triggers", []), ensure_ascii=False),
                    json.dumps(manifest.get("conflicts", []), ensure_ascii=False),
                    json.dumps(manifest.get("issues", []), ensure_ascii=False),
                    json.dumps(manifest.get("warnings", []), ensure_ascii=False),
                ),
            )
        skill_blockers.extend(conflict["reason"] for conflict in conflicts)
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="SkillValidated", source="runtime-orchestrate", summary=f"Validated {len(manifests)} skill manifest(s).", payload={"blockers": skill_blockers}, severity="warning" if skill_blockers else "info")

        for item in subagent_chain:
            sub_task_id = f"{run_id}-subagent-{item['order_index']}-{item['role']}"
            conn.execute(
                """
                INSERT INTO agent_tasks(id, goal_id, project, title, task_layer, scale, status, assigned_role, plan, evidence, depends_on, order_index)
                VALUES (?, ?, ?, ?, 'Runtime', ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (
                    sub_task_id,
                    goal_id,
                    project,
                    f"{item['role']} sub-agent task",
                    context["scale"],
                    item["role"],
                    f"{item['role']} handles orchestrated step {item['order_index']}.",
                    "runtime-orchestrate subagent chain",
                    f"{run_id}-subagent-{item['order_index'] - 1}-{subagent_chain[item['order_index'] - 2]['role']}" if item["order_index"] > 1 else None,
                    100 + item["order_index"],
                ),
            )
            conn.execute(
                """
                INSERT INTO subagent_runs(project, goal_id, run_id, task_id, role, status, input_summary, output_summary, boundary, handoff_to, evidence)
                VALUES (?, ?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?)
                """,
                (
                    project,
                    goal_id,
                    run_id,
                    sub_task_id,
                    item["role"],
                    args.request,
                    f"{item['role']} planned by orchestrator.",
                    item["boundary"],
                    item["handoff_to"],
                    f"order_index={item['order_index']}",
                ),
            )

        model_prompt = args.request
        model_response = f"mock adapter response for orchestrator; prompt_sha256={hashlib.sha256(model_prompt.encode('utf-8')).hexdigest()[:12]}."
        model_id = record_model_run(
            conn,
            project=project,
            goal_id=goal_id,
            run_id=run_id,
            task_id=f"{run_id}-subagent-1-planner",
            provider="mock",
            model_name="mock-orchestrator",
            adapter="mock-model-adapter",
            operation="planning",
            status="passed",
            duration_ms=0,
            input_tokens=len(model_prompt.split()),
            output_tokens=len(model_response.split()),
            cost_estimate=0.0,
            prompt_summary=summarize_output(model_prompt),
            response_summary=model_response,
            failure_type=None,
            failure_detail=None,
            evidence=json.dumps({"diagnostics": model_provider_config("mock")}, ensure_ascii=False),
        )
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, task_id=f"{run_id}-subagent-1-planner", event_type="ModelRunRecorded", source="runtime-orchestrate", summary="Mock model adapter completed planning.", payload={"model_run_id": model_id, "provider": "mock"})

        if not command_is_allowed(verifier_command, args.allow_unsafe):
            verify_result = {
                "result": "blocked",
                "exit_code": None,
                "stdout_summary": "Command blocked by safe verification prefix policy.",
                "failure_type": "environment",
                "failure_detail": "policy-blocked",
            }
        else:
            completed = subprocess.run(verifier_command, cwd=ROOT, shell=True, text=True, capture_output=True, timeout=args.timeout)
            output = f"{completed.stdout}\n{completed.stderr}".strip()
            failure_profile = classify_failure_detail(completed.returncode, output, verifier_command)
            verify_result = {
                "result": "passed" if completed.returncode == 0 else "failed",
                "exit_code": completed.returncode,
                "stdout_summary": summarize_output(output),
                "failure_type": failure_profile["type"],
                "failure_detail": failure_profile["detail"],
            }
        verifier_status = "completed" if verify_result["result"] == "passed" else "failed"
        conn.execute(
            """
            INSERT INTO subagent_runs(project, goal_id, run_id, task_id, role, status, input_summary, output_summary, boundary, failure_type, evidence, started_at, completed_at)
            VALUES (?, ?, ?, ?, 'verifier', ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                project,
                goal_id,
                run_id,
                f"{run_id}-subagent-4-verifier",
                verifier_status,
                "Run orchestrator verification.",
                f"Verifier result: {verify_result['result']} for {verifier_command}.",
                "Verify only.",
                verify_result["failure_type"],
                json.dumps({"verification": verify_result, "command": verifier_command}, ensure_ascii=False),
            ),
        )
        verification_cur = conn.execute(
            """
            INSERT INTO verification_runs(project, goal_id, task_id, scope, command, result, evidence, exit_code, stdout_summary, failure_type, ran_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                project,
                goal_id,
                f"{run_id}-subagent-4-verifier",
                "runtime orchestrator verification",
                verifier_command,
                verify_result["result"],
                verify_result["stdout_summary"],
                verify_result["exit_code"],
                verify_result["stdout_summary"],
                verify_result["failure_type"],
            ),
        )
        verification_id = verification_cur.lastrowid
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, task_id=f"{run_id}-subagent-4-verifier", event_type="VerificationPassed" if verify_result["result"] == "passed" else "VerificationFailed", source="runtime-orchestrate", summary=f"Verifier {verify_result['result']}.", payload={"verification_id": verification_id, "command": verifier_command}, severity="info" if verify_result["result"] == "passed" else "error")

        metrics = calculate_runtime_metrics(conn, project, goal_id, run_id)
        conn.execute(
            """
            INSERT INTO runtime_metrics(
                project, goal_id, run_id, scope, tool_call_count, model_call_count,
                verification_count, failure_count, retry_count, avg_duration_ms,
                verification_pass_rate, failure_rate, metrics_json
            )
            VALUES (?, ?, ?, 'run', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project,
                goal_id,
                run_id,
                metrics["tool_call_count"],
                metrics["model_call_count"],
                metrics["verification_count"],
                metrics["failure_count"],
                metrics["retry_count"],
                metrics["avg_duration_ms"],
                metrics["verification_pass_rate"],
                metrics["failure_rate"],
                json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            ),
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        conn.execute(
            """
            UPDATE agent_tasks
            SET status = 'completed',
                completed_evidence = COALESCE(completed_evidence, 'runtime-orchestrate completed chain'),
                updated_at = datetime('now')
            WHERE project = ? AND goal_id = ?
            """,
            (project, goal_id),
        )
        conn.execute(
            """
            UPDATE subagent_runs
            SET status = CASE WHEN status = 'planned' THEN 'completed' ELSE status END,
                completed_at = COALESCE(completed_at, datetime('now')),
                output_summary = COALESCE(output_summary, 'Completed by runtime orchestrator.')
            WHERE project = ? AND goal_id = ? AND run_id = ?
            """,
            (project, goal_id, run_id),
        )
        conn.execute(
            """
            UPDATE runtime_runs
            SET status = ?, summary = ?, next_action = ?, updated_at = datetime('now')
            WHERE project = ? AND id = ?
            """,
            ("completed", "Runtime orchestrator completed context, policy, skill, model, subagent, verification, metrics, and trace chain.", "done", project, run_id),
        )
        trace = build_runtime_trace(conn, project, goal_id, run_id)
        trace_cur = conn.execute(
            "INSERT INTO runtime_traces(project, goal_id, run_id, trace_json) VALUES (?, ?, ?, ?)",
            (project, goal_id, run_id, json.dumps(trace, ensure_ascii=False, sort_keys=True)),
        )
        trace_id = trace_cur.lastrowid
        record_event(conn, project=project, goal_id=goal_id, run_id=run_id, event_type="TraceExported", source="runtime-orchestrate", summary="Runtime orchestrator exported final trace.", payload={"trace_id": trace_id, "duration_ms": duration_ms})
        conn.commit()
        trace = build_runtime_trace(conn, project, goal_id, run_id)

    print_json(
        {
            "ok": verify_result["result"] == "passed" and not skill_blockers,
            "project": project,
            "goal_id": goal_id,
            "run_id": run_id,
            "duration_ms": duration_ms,
            "skill_blockers": skill_blockers,
            "model_run_id": model_id,
            "verification_id": verification_id,
            "trace_id": trace_id,
            "trace": trace,
        }
    )


def cmd_runtime_record(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)

        if args.kind == "goal":
            status = args.status or "active"
            runtime_id = args.id or str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO agent_goals(
                    id, project, objective, status, priority, current_phase,
                    success_criteria, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project = excluded.project,
                    objective = excluded.objective,
                    status = excluded.status,
                    priority = excluded.priority,
                    current_phase = excluded.current_phase,
                    success_criteria = excluded.success_criteria,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    require_arg(args, "objective"),
                    status,
                    args.priority,
                    args.current_phase,
                    args.success_criteria,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "task":
            status = args.status or "pending"
            runtime_id = args.id or str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO agent_tasks(
                    id, goal_id, project, title, task_layer, scale, status,
                    assigned_role, plan, evidence, blocker
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    goal_id = excluded.goal_id,
                    project = excluded.project,
                    title = excluded.title,
                    task_layer = excluded.task_layer,
                    scale = excluded.scale,
                    status = excluded.status,
                    assigned_role = excluded.assigned_role,
                    plan = excluded.plan,
                    evidence = excluded.evidence,
                    blocker = excluded.blocker,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.goal_id,
                    args.project,
                    require_arg(args, "title"),
                    args.task_layer,
                    args.scale,
                    status,
                    args.assigned_role,
                    args.plan,
                    args.evidence,
                    args.blocker,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "observation":
            cur = conn.execute(
                """
                INSERT INTO agent_observations(project, goal_id, source, summary, evidence, severity)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    require_arg(args, "source"),
                    require_arg(args, "summary"),
                    args.evidence,
                    args.severity,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "capability":
            conn.execute(
                """
                INSERT INTO capability_nodes(
                    project, name, status, frontend, api, backend,
                    data_state, verification, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, name) DO UPDATE SET
                    status = excluded.status,
                    frontend = excluded.frontend,
                    api = excluded.api,
                    backend = excluded.backend,
                    data_state = excluded.data_state,
                    verification = excluded.verification,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (
                    args.project,
                    require_arg(args, "name"),
                    args.capability_status,
                    args.frontend,
                    args.api,
                    args.backend,
                    args.data_state,
                    args.verification,
                    args.evidence,
                ),
            )
            capability = conn.execute(
                "SELECT id FROM capability_nodes WHERE project = ? AND name = ?",
                (args.project, args.name),
            ).fetchone()
            capability_id = capability["id"]
            if args.links is not None:
                conn.execute("DELETE FROM capability_links WHERE capability_id = ?", (capability_id,))
            for relation, target in parse_runtime_links(args.links):
                conn.execute(
                    """
                    INSERT INTO capability_links(capability_id, relation, target, evidence)
                    VALUES (?, ?, ?, ?)
                    """,
                    (capability_id, relation, target, args.evidence),
                )
            result = {"ok": True, "kind": args.kind, "id": capability_id, "project": args.project}

        elif args.kind == "policy":
            cur = conn.execute(
                """
                INSERT INTO policy_decisions(
                    project, goal_id, task_id, decision_type, decision, rationale, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    require_arg(args, "decision_type"),
                    require_arg(args, "decision"),
                    args.rationale,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "verification":
            cur = conn.execute(
                """
                INSERT INTO verification_runs(
                    project, goal_id, task_id, scope, command, result, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    require_arg(args, "scope"),
                    args.command,
                    args.result,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "recovery":
            status = args.status or "planned"
            cur = conn.execute(
                """
                INSERT INTO recovery_points(
                    project, goal_id, task_id, strategy, files, status, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.task_id,
                    require_arg(args, "strategy"),
                    normalize_csv(args.files),
                    status,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "improvement":
            status = args.status or "candidate"
            conn.execute(
                """
                INSERT INTO improvement_reviews(
                    project, goal_id, run_id, candidate_name, source_type, trigger, evidence,
                    scope, boundary, status, review_result
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, candidate_name, source_type) DO UPDATE SET
                    goal_id = excluded.goal_id,
                    run_id = excluded.run_id,
                    trigger = excluded.trigger,
                    evidence = excluded.evidence,
                    scope = excluded.scope,
                    boundary = excluded.boundary,
                    status = excluded.status,
                    review_result = excluded.review_result,
                    updated_at = datetime('now')
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    require_arg(args, "candidate_name"),
                    require_arg(args, "source_type"),
                    require_arg(args, "trigger"),
                    require_arg(args, "evidence"),
                    args.scope,
                    args.boundary,
                    status,
                    args.review_result,
                ),
            )
            row = conn.execute(
                """
                SELECT id FROM improvement_reviews
                WHERE project = ? AND candidate_name = ? AND source_type = ?
                """,
                (args.project, args.candidate_name, args.source_type),
            ).fetchone()
            result = {"ok": True, "kind": args.kind, "id": row["id"], "project": args.project}

        else:
            raise SystemExit(f"Unsupported runtime kind: {args.kind}")

        conn.commit()
    print_json(result)


def cmd_runtime_list(args: argparse.Namespace) -> None:
    table_by_kind = {
        "goal": ("agent_goals", "updated_at"),
        "task": ("agent_tasks", "updated_at"),
        "observation": ("agent_observations", "created_at"),
        "capability": ("capability_nodes", "updated_at"),
        "policy": ("policy_decisions", "created_at"),
        "verification": ("verification_runs", "created_at"),
        "tool": ("tool_runs", "created_at"),
        "skill": ("skill_manifests", "validated_at"),
        "model": ("model_runs", "created_at"),
        "subagent": ("subagent_runs", "created_at"),
        "adapter": ("host_adapters", "updated_at"),
        "metrics": ("runtime_metrics", "created_at"),
        "trace": ("runtime_traces", "exported_at"),
        "recovery": ("recovery_points", "created_at"),
        "reflection": ("reflections", "created_at"),
        "improvement": ("improvement_reviews", "updated_at"),
        "event": ("agent_events", "created_at"),
    }
    table, order_column = table_by_kind[args.kind]
    where = ["project = ?"]
    params: list[Any] = [args.project]

    if args.status and args.kind in {"goal", "task", "capability", "recovery", "improvement", "tool", "skill", "model", "subagent", "adapter"}:
        status_column = "status"
        where.append(f"{status_column} = ?")
        params.append(args.status)
    if args.goal_id and args.kind in {"task", "observation", "policy", "verification", "tool", "skill", "model", "subagent", "metrics", "recovery", "event"}:
        where.append("goal_id = ?")
        params.append(args.goal_id)

    params.append(args.limit)
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE {' AND '.join(where)}
            ORDER BY {order_column} DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    print_json({"ok": True, "kind": args.kind, "results": [row_to_dict(row) for row in rows]})


def cmd_runtime_summary(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        active_goals = conn.execute(
            "SELECT COUNT(*) AS count FROM agent_goals WHERE project = ? AND status = 'active'",
            (args.project,),
        ).fetchone()["count"]
        tasks_by_status = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM agent_tasks
            WHERE project = ?
            GROUP BY status
            ORDER BY status
            """,
            (args.project,),
        ).fetchall()
        capabilities_by_status = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM capability_nodes
            WHERE project = ?
            GROUP BY status
            ORDER BY status
            """,
            (args.project,),
        ).fetchall()
        recent_observations = conn.execute(
            """
            SELECT id, source, summary, severity, created_at
            FROM agent_observations
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_verifications = conn.execute(
            """
            SELECT id, scope, command, result, created_at
            FROM verification_runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_tools = conn.execute(
            """
            SELECT id, tool_type, adapter, status, duration_ms, failure_type, created_at
            FROM tool_runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_skills = conn.execute(
            """
            SELECT id, skill_name, status, path, validated_at
            FROM skill_manifests
            WHERE project = ?
            ORDER BY validated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_models = conn.execute(
            """
            SELECT id, provider, model_name, adapter, operation, status, duration_ms, input_tokens, output_tokens, cost_estimate, created_at
            FROM model_runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_subagents = conn.execute(
            """
            SELECT id, role, status, handoff_to, input_summary, output_summary, created_at
            FROM subagent_runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_adapters = conn.execute(
            """
            SELECT id, host_type, adapter_name, status, capabilities_json, config_path, updated_at
            FROM host_adapters
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_metrics = conn.execute(
            """
            SELECT id, scope, tool_call_count, model_call_count, verification_count,
                   failure_count, retry_count, avg_duration_ms, verification_pass_rate,
                   failure_rate, created_at
            FROM runtime_metrics
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_traces = conn.execute(
            """
            SELECT id, goal_id, run_id, exported_at
            FROM runtime_traces
            WHERE project = ?
            ORDER BY exported_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_reflections = conn.execute(
            """
            SELECT id, source_type, root_cause, summary, created_at
            FROM reflections
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_events = conn.execute(
            """
            SELECT id, event_type, source, summary, severity, created_at
            FROM agent_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        open_improvements = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM improvement_reviews
            WHERE project = ? AND status IN ('candidate', 'reviewing')
            """,
            (args.project,),
        ).fetchone()["count"]
    print_json(
        {
            "ok": True,
            "project": args.project,
            "active_goals": active_goals,
            "tasks_by_status": [row_to_dict(row) for row in tasks_by_status],
            "capabilities_by_status": [row_to_dict(row) for row in capabilities_by_status],
            "recent_observations": [row_to_dict(row) for row in recent_observations],
            "recent_verifications": [row_to_dict(row) for row in recent_verifications],
            "recent_tools": [row_to_dict(row) for row in recent_tools],
            "recent_skills": [row_to_dict(row) for row in recent_skills],
            "recent_models": [row_to_dict(row) for row in recent_models],
            "recent_subagents": [row_to_dict(row) for row in recent_subagents],
            "recent_adapters": [row_to_dict(row) for row in recent_adapters],
            "recent_metrics": [row_to_dict(row) for row in recent_metrics],
            "recent_traces": [row_to_dict(row) for row in recent_traces],
            "recent_reflections": [row_to_dict(row) for row in recent_reflections],
            "recent_events": [row_to_dict(row) for row in recent_events],
            "open_improvements": open_improvements,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent OS Agent Runtime controllers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    context_parser = subparsers.add_parser("runtime-detect-context", help="Detect project, stack, task layer, and scale")
    add_common_args(context_parser)
    context_parser.add_argument("--project")
    context_parser.add_argument("--request", required=True)
    context_parser.add_argument("--files", nargs="*")
    context_parser.add_argument("--record", action="store_true")
    context_parser.set_defaults(func=cmd_runtime_detect_context)

    snapshot_parser = subparsers.add_parser("runtime-workspace-snapshot", help="Capture workspace state snapshot")
    add_common_args(snapshot_parser)
    snapshot_parser.add_argument("--project")
    snapshot_parser.add_argument("--record", action="store_true")
    snapshot_parser.set_defaults(func=cmd_runtime_workspace_snapshot)

    rank_context_parser = subparsers.add_parser("runtime-rank-context", help="Rank context items by relevance")
    add_common_args(rank_context_parser)
    rank_context_parser.add_argument("--project")
    rank_context_parser.add_argument("--request", required=True)
    rank_context_parser.add_argument("--files", nargs="*")
    rank_context_parser.add_argument("--limit", type=int, default=5)
    rank_context_parser.add_argument("--use-memory", action="store_true")
    rank_context_parser.set_defaults(func=cmd_runtime_rank_context)

    kernel_parser = subparsers.add_parser("kernel-step", help="Run one Agent Kernel decision step")
    add_common_args(kernel_parser)
    kernel_parser.add_argument("--run-id")
    kernel_parser.add_argument("--goal-id")
    kernel_parser.add_argument("--project")
    kernel_parser.add_argument("--request", required=True)
    kernel_parser.add_argument("--files", nargs="*")
    kernel_parser.add_argument("--signal", nargs="*")
    kernel_parser.add_argument(
        "--capability-status",
        choices=("complete", "partial", "broken-chain", "absent", "unconfirmed"),
        default="unconfirmed",
    )
    kernel_parser.add_argument("--record", action="store_true")
    kernel_parser.set_defaults(func=cmd_kernel_step)

    event_parser = subparsers.add_parser("runtime-record-event", help="Record an Agent Kernel event")
    add_common_args(event_parser)
    event_parser.add_argument("--project", required=True)
    event_parser.add_argument("--run-id")
    event_parser.add_argument("--goal-id")
    event_parser.add_argument("--task-id")
    event_parser.add_argument("--event-type", choices=EVENT_TYPES, required=True)
    event_parser.add_argument("--source", default="runtime")
    event_parser.add_argument("--summary", required=True)
    event_parser.add_argument("--payload-json")
    event_parser.add_argument("--severity", choices=("info", "warning", "error", "critical"), default="info")
    event_parser.set_defaults(func=cmd_runtime_record_event)

    run_parser = subparsers.add_parser("runtime-run", help="Run the full Agent Runtime planning loop")
    add_common_args(run_parser)
    run_parser.add_argument("--id")
    run_parser.add_argument("--project")
    run_parser.add_argument("--goal-id")
    run_parser.add_argument("--request", required=True)
    run_parser.add_argument("--capability")
    run_parser.add_argument("--term", nargs="*")
    run_parser.add_argument("--roots", nargs="*")
    run_parser.add_argument("--files", nargs="*")
    run_parser.add_argument("--signal", nargs="*")
    run_parser.add_argument("--max-files", type=int, default=2000)
    run_parser.add_argument("--max-hits", type=int, default=8)
    run_parser.add_argument("--require-data", action="store_true")
    run_parser.add_argument("--require-verification", action="store_true")
    run_parser.add_argument("--use-memory", action="store_true")
    run_parser.add_argument("--record", action="store_true")
    run_parser.set_defaults(func=cmd_runtime_run)

    orchestrate_parser = subparsers.add_parser("runtime-orchestrate", help="Run an end-to-end Agent Runtime orchestration loop")
    add_common_args(orchestrate_parser)
    orchestrate_parser.add_argument("--project")
    orchestrate_parser.add_argument("--goal-id")
    orchestrate_parser.add_argument("--run-id")
    orchestrate_parser.add_argument("--request", required=True)
    orchestrate_parser.add_argument("--capability")
    orchestrate_parser.add_argument("--term", nargs="*")
    orchestrate_parser.add_argument("--roots", nargs="*")
    orchestrate_parser.add_argument("--files", nargs="*")
    orchestrate_parser.add_argument("--signal", nargs="*")
    orchestrate_parser.add_argument("--max-files", type=int, default=2000)
    orchestrate_parser.add_argument("--max-hits", type=int, default=8)
    orchestrate_parser.add_argument("--require-data", action="store_true")
    orchestrate_parser.add_argument("--require-verification", action="store_true")
    orchestrate_parser.add_argument("--use-memory", action="store_true")
    orchestrate_parser.add_argument("--verification-command", default="python -m py_compile scripts/agent-runtime.py")
    orchestrate_parser.add_argument("--timeout", type=int, default=60)
    orchestrate_parser.add_argument("--allow-unsafe", action="store_true")
    orchestrate_parser.set_defaults(func=cmd_runtime_orchestrate)

    skill_parser = subparsers.add_parser("runtime-select-skills", help="Recommend skills for a task")
    add_common_args(skill_parser)
    skill_parser.add_argument("--project", required=True)
    skill_parser.add_argument("--goal-id")
    skill_parser.add_argument("--run-id")
    skill_parser.add_argument("--request")
    skill_parser.add_argument("--task-layer", nargs="*")
    skill_parser.add_argument("--stack")
    skill_parser.add_argument("--files", nargs="*")
    skill_parser.add_argument("--skills-dir", type=Path)
    skill_parser.add_argument("--record", action="store_true")
    skill_parser.set_defaults(func=cmd_runtime_select_skills)

    skill_validate_parser = subparsers.add_parser("runtime-validate-skills", help="Validate skill manifests as runtime capability packages")
    add_common_args(skill_validate_parser)
    skill_validate_parser.add_argument("--project", required=True)
    skill_validate_parser.add_argument("--goal-id")
    skill_validate_parser.add_argument("--run-id")
    skill_validate_parser.add_argument("--skills-dir", type=Path)
    skill_validate_parser.add_argument("--skill", nargs="*")
    skill_validate_parser.add_argument("--request")
    skill_validate_parser.add_argument("--task-layer", nargs="*")
    skill_validate_parser.add_argument("--stack")
    skill_validate_parser.add_argument("--record", action="store_true")
    skill_validate_parser.set_defaults(func=cmd_runtime_validate_skills)

    task_plan_parser = subparsers.add_parser("runtime-plan-tasks", help="Create a runtime task queue from context")
    add_common_args(task_plan_parser)
    task_plan_parser.add_argument("--project", required=True)
    task_plan_parser.add_argument("--goal-id")
    task_plan_parser.add_argument("--request", required=True)
    task_plan_parser.add_argument("--task-layer", nargs="*")
    task_plan_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"))
    task_plan_parser.add_argument(
        "--capability-status",
        choices=("complete", "partial", "broken-chain", "absent", "unconfirmed"),
        default="unconfirmed",
    )
    task_plan_parser.add_argument("--files", nargs="*")
    task_plan_parser.add_argument("--task-prefix", default="runtime-task")
    task_plan_parser.add_argument("--record", action="store_true")
    task_plan_parser.set_defaults(func=cmd_runtime_plan_tasks)

    complete_task_parser = subparsers.add_parser("runtime-complete-task", help="Mark a runtime task completed")
    add_common_args(complete_task_parser)
    complete_task_parser.add_argument("--project", required=True)
    complete_task_parser.add_argument("--id", required=True)
    complete_task_parser.add_argument("--evidence", required=True)
    complete_task_parser.add_argument("--complete-goal", action="store_true")
    complete_task_parser.set_defaults(func=cmd_runtime_complete_task)

    validation_profile_parser = subparsers.add_parser(
        "runtime-detect-validation-profile",
        help="Detect validation commands for stack and task layers",
    )
    add_common_args(validation_profile_parser)
    validation_profile_parser.add_argument("--project", required=True)
    validation_profile_parser.add_argument("--request")
    validation_profile_parser.add_argument("--stack")
    validation_profile_parser.add_argument("--task-layer", nargs="*")
    validation_profile_parser.add_argument("--files", nargs="*")
    validation_profile_parser.set_defaults(func=cmd_runtime_detect_validation_profile)

    verification_pipeline_parser = subparsers.add_parser("runtime-verification-pipeline", help="Build a multi-stage verification pipeline")
    add_common_args(verification_pipeline_parser)
    verification_pipeline_parser.add_argument("--project", required=True)
    verification_pipeline_parser.add_argument("--goal-id")
    verification_pipeline_parser.add_argument("--task-id")
    verification_pipeline_parser.add_argument("--request")
    verification_pipeline_parser.add_argument("--stack")
    verification_pipeline_parser.add_argument("--task-layer", nargs="*")
    verification_pipeline_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"))
    verification_pipeline_parser.add_argument("--files", nargs="*")
    verification_pipeline_parser.add_argument("--record", action="store_true")
    verification_pipeline_parser.set_defaults(func=cmd_runtime_verification_pipeline)

    run_verification_parser = subparsers.add_parser("runtime-run-verification", help="Run and record a verification command")
    add_common_args(run_verification_parser)
    run_verification_parser.add_argument("--id", type=int)
    run_verification_parser.add_argument("--project", required=True)
    run_verification_parser.add_argument("--goal-id")
    run_verification_parser.add_argument("--task-id")
    run_verification_parser.add_argument("--scope", default="runtime verification")
    run_verification_parser.add_argument("--command")
    run_verification_parser.add_argument("--evidence")
    run_verification_parser.add_argument("--timeout", type=int, default=60)
    run_verification_parser.add_argument("--allow-unsafe", action="store_true")
    run_verification_parser.add_argument("--record", action="store_true")
    run_verification_parser.set_defaults(func=cmd_runtime_run_verification)

    run_tool_parser = subparsers.add_parser("runtime-run-tool", help="Run or record a Tool Runtime call")
    add_common_args(run_tool_parser)
    run_tool_parser.add_argument("--project", required=True)
    run_tool_parser.add_argument("--goal-id")
    run_tool_parser.add_argument("--run-id")
    run_tool_parser.add_argument("--task-id")
    run_tool_parser.add_argument("--tool-type", choices=("shell", "git", "api", "browser"))
    run_tool_parser.add_argument("--adapter")
    run_tool_parser.add_argument("--command")
    run_tool_parser.add_argument("--target")
    run_tool_parser.add_argument("--git-action", choices=("status", "diff", "log", "branch", "check-clean"))
    run_tool_parser.add_argument("--method", default="GET")
    run_tool_parser.add_argument("--header", nargs="*")
    run_tool_parser.add_argument("--body")
    run_tool_parser.add_argument("--expect-text")
    run_tool_parser.add_argument(
        "--browser-action",
        choices=("open", "check-text", "click", "type", "screenshot"),
        default="check-text",
    )
    run_tool_parser.add_argument("--selector")
    run_tool_parser.add_argument("--text")
    run_tool_parser.add_argument("--screenshot-path")
    run_tool_parser.add_argument("--timeout", type=int, default=60)
    run_tool_parser.add_argument("--allow-unsafe", action="store_true")
    run_tool_parser.add_argument("--evidence")
    run_tool_parser.set_defaults(func=cmd_runtime_run_tool)

    run_model_parser = subparsers.add_parser("runtime-run-model", help="Record a Model Runtime call through a provider adapter")
    add_common_args(run_model_parser)
    run_model_parser.add_argument("--project", required=True)
    run_model_parser.add_argument("--goal-id")
    run_model_parser.add_argument("--run-id")
    run_model_parser.add_argument("--task-id")
    run_model_parser.add_argument("--provider", choices=MODEL_PROVIDERS, required=True)
    run_model_parser.add_argument("--model", required=True)
    run_model_parser.add_argument("--adapter")
    run_model_parser.add_argument(
        "--operation",
        choices=("inference", "planning", "review", "embedding", "rerank", "tool-call"),
        default="inference",
    )
    run_model_parser.add_argument(
        "--status",
        choices=("passed", "failed", "blocked", "not-run"),
    )
    run_model_parser.add_argument("--duration-ms", type=int)
    run_model_parser.add_argument("--input-tokens", type=int)
    run_model_parser.add_argument("--output-tokens", type=int)
    run_model_parser.add_argument("--cost-estimate", type=float)
    run_model_parser.add_argument("--prompt")
    run_model_parser.add_argument("--prompt-summary")
    run_model_parser.add_argument("--response-summary")
    run_model_parser.add_argument(
        "--failure-type",
        choices=("implementation", "test", "environment", "requirement", "unknown"),
    )
    run_model_parser.add_argument("--failure-detail")
    run_model_parser.add_argument("--evidence")
    run_model_parser.add_argument("--record-only", action="store_true")
    run_model_parser.set_defaults(func=cmd_runtime_run_model)

    run_subagent_parser = subparsers.add_parser("runtime-run-subagent", help="Record a Sub-agent Runtime role handoff")
    add_common_args(run_subagent_parser)
    run_subagent_parser.add_argument("--project", required=True)
    run_subagent_parser.add_argument("--goal-id")
    run_subagent_parser.add_argument("--run-id")
    run_subagent_parser.add_argument("--task-id")
    run_subagent_parser.add_argument("--role", choices=SUBAGENT_ROLES, required=True)
    run_subagent_parser.add_argument(
        "--status",
        choices=("planned", "running", "completed", "blocked", "failed"),
        default="planned",
    )
    run_subagent_parser.add_argument("--input-summary", required=True)
    run_subagent_parser.add_argument("--output-summary")
    run_subagent_parser.add_argument("--boundary", required=True)
    run_subagent_parser.add_argument("--handoff-to", choices=SUBAGENT_ROLES)
    run_subagent_parser.add_argument(
        "--failure-type",
        choices=("implementation", "test", "environment", "requirement", "unknown"),
    )
    run_subagent_parser.add_argument("--evidence")
    run_subagent_parser.add_argument("--started-at")
    run_subagent_parser.add_argument("--completed-at")
    run_subagent_parser.set_defaults(func=cmd_runtime_run_subagent)

    plan_subagents_parser = subparsers.add_parser("runtime-plan-subagents", help="Create an ordered sub-agent task chain")
    add_common_args(plan_subagents_parser)
    plan_subagents_parser.add_argument("--project", required=True)
    plan_subagents_parser.add_argument("--goal-id")
    plan_subagents_parser.add_argument("--run-id")
    plan_subagents_parser.add_argument("--request")
    plan_subagents_parser.add_argument("--role", nargs="*", choices=SUBAGENT_ROLES)
    plan_subagents_parser.add_argument("--task-prefix", default="subagent-task")
    plan_subagents_parser.add_argument("--task-layer", default="Runtime")
    plan_subagents_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"), default="L2")
    plan_subagents_parser.set_defaults(func=cmd_runtime_plan_subagents)

    run_subagent_role_parser = subparsers.add_parser("runtime-run-subagent-role", help="Run a concrete reviewer/verifier sub-agent role")
    add_common_args(run_subagent_role_parser)
    run_subagent_role_parser.add_argument("--project", required=True)
    run_subagent_role_parser.add_argument("--goal-id")
    run_subagent_role_parser.add_argument("--run-id")
    run_subagent_role_parser.add_argument("--task-id")
    run_subagent_role_parser.add_argument("--role", choices=SUBAGENT_ROLES, required=True)
    run_subagent_role_parser.add_argument("--input-summary")
    run_subagent_role_parser.add_argument("--output-summary")
    run_subagent_role_parser.add_argument("--boundary")
    run_subagent_role_parser.add_argument("--handoff-to", choices=SUBAGENT_ROLES)
    run_subagent_role_parser.add_argument("--target")
    run_subagent_role_parser.add_argument("--diff-text")
    run_subagent_role_parser.add_argument("--command")
    run_subagent_role_parser.add_argument("--scope", default="sub-agent verification")
    run_subagent_role_parser.add_argument("--timeout", type=int, default=60)
    run_subagent_role_parser.add_argument("--allow-unsafe", action="store_true")
    run_subagent_role_parser.set_defaults(func=cmd_runtime_run_subagent_role)

    adapter_parser = subparsers.add_parser("runtime-register-adapter", help="Register or validate a host adapter")
    add_common_args(adapter_parser)
    adapter_parser.add_argument("--project", required=True)
    adapter_parser.add_argument("--host-type", choices=HOST_TYPES, required=True)
    adapter_parser.add_argument("--adapter-name", required=True)
    adapter_parser.add_argument("--entrypoint")
    adapter_parser.add_argument("--capability", nargs="*")
    adapter_parser.add_argument("--require-capability", nargs="*")
    adapter_parser.add_argument("--config-path")
    adapter_parser.add_argument(
        "--status",
        choices=("available", "missing", "disabled", "invalid"),
    )
    adapter_parser.add_argument("--evidence")
    adapter_parser.set_defaults(func=cmd_runtime_register_adapter)

    detect_adapter_parser = subparsers.add_parser("runtime-detect-host-adapter", help="Detect host adapter capability support")
    add_common_args(detect_adapter_parser)
    detect_adapter_parser.add_argument("--project", required=True)
    detect_adapter_parser.add_argument("--host-type", choices=HOST_TYPES, required=True)
    detect_adapter_parser.add_argument("--require-capability", nargs="*")
    detect_adapter_parser.set_defaults(func=cmd_runtime_detect_host_adapter)

    metrics_parser = subparsers.add_parser("runtime-metrics", help="Calculate observability metrics for runtime activity")
    add_common_args(metrics_parser)
    metrics_parser.add_argument("--project", required=True)
    metrics_parser.add_argument("--goal-id")
    metrics_parser.add_argument("--run-id")
    metrics_parser.add_argument("--request")
    metrics_parser.add_argument("--files", nargs="*")
    metrics_parser.add_argument("--record", action="store_true")
    metrics_parser.set_defaults(func=cmd_runtime_metrics)

    trace_parser = subparsers.add_parser("runtime-trace", help="Export a complete runtime trace report")
    add_common_args(trace_parser)
    trace_parser.add_argument("--project", required=True)
    trace_parser.add_argument("--goal-id")
    trace_parser.add_argument("--run-id")
    trace_parser.add_argument("--record", action="store_true")
    trace_parser.set_defaults(func=cmd_runtime_trace)

    doctor_parser = subparsers.add_parser("runtime-doctor", help="Check Agent OS installation health")
    add_common_args(doctor_parser)
    doctor_parser.add_argument("--root", type=Path)
    doctor_parser.set_defaults(func=cmd_runtime_doctor)

    version_parser = subparsers.add_parser("runtime-version", help="Show Agent OS and runtime schema versions")
    add_common_args(version_parser)
    version_parser.add_argument("--root", type=Path)
    version_parser.set_defaults(func=cmd_runtime_version)

    migrate_parser = subparsers.add_parser("runtime-migrate", help="Safely initialize or migrate Agent OS runtime storage")
    add_common_args(migrate_parser)
    migrate_parser.add_argument("--root", type=Path)
    migrate_parser.add_argument("--dry-run", action="store_true")
    migrate_parser.set_defaults(func=cmd_runtime_migrate)

    dashboard_parser = subparsers.add_parser("runtime-dashboard", help="Generate a local Agent OS runtime dashboard HTML")
    add_common_args(dashboard_parser)
    dashboard_parser.add_argument("--project", required=True)
    dashboard_parser.add_argument("--output", type=Path)
    dashboard_parser.add_argument("--data-output", type=Path)
    dashboard_parser.add_argument("--inline-data", action="store_true")
    dashboard_parser.add_argument("--limit", type=int, default=20)
    dashboard_parser.set_defaults(func=cmd_runtime_dashboard)

    trends_parser = subparsers.add_parser("runtime-quality-trends", help="Report runtime quality trends from metrics snapshots")
    add_common_args(trends_parser)
    trends_parser.add_argument("--project", required=True)
    trends_parser.add_argument("--limit", type=int, default=20)
    trends_parser.add_argument("--output", type=Path)
    trends_parser.set_defaults(func=cmd_runtime_quality_trends)

    policy_packs_parser = subparsers.add_parser("runtime-policy-packs", help="List and validate reusable team policy packs")
    add_common_args(policy_packs_parser)
    policy_packs_parser.add_argument("--packs-dir", type=Path)
    policy_packs_parser.add_argument("--name")
    policy_packs_parser.add_argument("--action", choices=("enable", "disable"))
    policy_packs_parser.add_argument("--override", action="append")
    policy_packs_parser.set_defaults(func=cmd_runtime_policy_packs)

    security_parser = subparsers.add_parser("runtime-security-check", help="Run secret scan and report permission/sandbox policy")
    add_common_args(security_parser)
    security_parser.add_argument("--root", type=Path)
    security_parser.add_argument("--max-files", type=int, default=2000)
    security_parser.add_argument("--command")
    security_parser.add_argument("--output", type=Path)
    security_parser.set_defaults(func=cmd_runtime_security_check)

    distribution_parser = subparsers.add_parser("runtime-distribution", help="Report supported Agent OS distribution channels")
    add_common_args(distribution_parser)
    distribution_parser.add_argument("--root", type=Path)
    distribution_parser.add_argument("--channel")
    distribution_parser.set_defaults(func=cmd_runtime_distribution)

    vscode_parser = subparsers.add_parser("runtime-vscode-protocol", help="Emit VSCode extension integration protocol")
    add_common_args(vscode_parser)
    vscode_parser.add_argument("--root", type=Path)
    vscode_parser.add_argument("--project", required=True)
    vscode_parser.add_argument("--output", type=Path)
    vscode_parser.set_defaults(func=cmd_runtime_vscode_protocol)

    team_parser = subparsers.add_parser("runtime-team-workspace", help="Report team workspace policy/template readiness")
    add_common_args(team_parser)
    team_parser.add_argument("--root", type=Path)
    team_parser.set_defaults(func=cmd_runtime_team_workspace)

    release_parser = subparsers.add_parser("runtime-release-check", help="Run Agent OS release readiness checks")
    add_common_args(release_parser)
    release_parser.add_argument("--root", type=Path)
    release_parser.add_argument("--output", type=Path)
    release_parser.set_defaults(func=cmd_runtime_release_check)

    transition_parser = subparsers.add_parser("runtime-transition", help="Transition goal/task/run state and record an event")
    add_common_args(transition_parser)
    transition_parser.add_argument("--project", required=True)
    transition_parser.add_argument("--entity-type", choices=("goal", "task", "run"), required=True)
    transition_parser.add_argument("--id", required=True)
    transition_parser.add_argument("--status", required=True)
    transition_parser.add_argument("--goal-id")
    transition_parser.add_argument("--task-id")
    transition_parser.add_argument("--run-id")
    transition_parser.add_argument("--summary")
    transition_parser.add_argument("--reason")
    transition_parser.add_argument("--current-phase")
    transition_parser.add_argument("--final-result")
    transition_parser.add_argument("--completed-evidence")
    transition_parser.add_argument("--blocker")
    transition_parser.add_argument("--next-action")
    transition_parser.set_defaults(func=cmd_runtime_transition)

    checkpoint_parser = subparsers.add_parser("runtime-create-checkpoint", help="Record an available recovery checkpoint")
    add_common_args(checkpoint_parser)
    checkpoint_parser.add_argument("--project", required=True)
    checkpoint_parser.add_argument("--goal-id")
    checkpoint_parser.add_argument("--task-id")
    checkpoint_parser.add_argument("--files", nargs="*")
    checkpoint_parser.add_argument("--checkpoint")
    checkpoint_parser.add_argument("--strategy")
    checkpoint_parser.add_argument("--evidence")
    checkpoint_parser.set_defaults(func=cmd_runtime_create_checkpoint)

    mark_recovery_parser = subparsers.add_parser("runtime-mark-recovery", help="Mark a recovery point as used or obsolete")
    add_common_args(mark_recovery_parser)
    mark_recovery_parser.add_argument("--id", type=int, required=True)
    mark_recovery_parser.add_argument("--status", choices=("used", "obsolete", "available", "planned"), required=True)
    mark_recovery_parser.add_argument("--reason")
    mark_recovery_parser.set_defaults(func=cmd_runtime_mark_recovery)

    reflect_parser = subparsers.add_parser("runtime-reflect", help="Record a reflection from a task, run, or failure")
    add_common_args(reflect_parser)
    reflect_parser.add_argument("--project", required=True)
    reflect_parser.add_argument("--goal-id")
    reflect_parser.add_argument("--run-id")
    reflect_parser.add_argument("--source-type", choices=("failure", "success", "partial", "manual"), required=True)
    reflect_parser.add_argument("--summary", required=True)
    reflect_parser.add_argument("--evidence")
    reflect_parser.add_argument("--failure-type")
    reflect_parser.add_argument("--failure-detail")
    reflect_parser.add_argument("--pattern")
    reflect_parser.add_argument("--next-step")
    reflect_parser.add_argument("--confidence", type=float, default=0.7)
    reflect_parser.set_defaults(func=cmd_runtime_reflect)

    docs_check_parser = subparsers.add_parser("runtime-check-docs", help="Check docs freshness and impact for a request")
    add_common_args(docs_check_parser)
    docs_check_parser.add_argument("--project", required=True)
    docs_check_parser.add_argument("--request")
    docs_check_parser.add_argument("--files", nargs="*")
    docs_check_parser.set_defaults(func=cmd_runtime_check_docs)

    knowledge_check_parser = subparsers.add_parser("runtime-check-knowledge", help="Check knowledge conflict between memory/docs/code/runtime")
    add_common_args(knowledge_check_parser)
    knowledge_check_parser.add_argument("--project", required=True)
    knowledge_check_parser.add_argument("--request")
    knowledge_check_parser.add_argument("--capability")
    knowledge_check_parser.add_argument("--files", nargs="*")
    knowledge_check_parser.add_argument("--goal-id")
    knowledge_check_parser.add_argument("--run-id")
    knowledge_check_parser.add_argument("--limit", type=int, default=5)
    knowledge_check_parser.set_defaults(func=cmd_runtime_check_knowledge)

    final_check_parser = subparsers.add_parser("runtime-final-check", help="Check final runtime gate completeness")
    add_common_args(final_check_parser)
    final_check_parser.add_argument("--project", required=True)
    final_check_parser.add_argument("--goal-id")
    final_check_parser.add_argument("--run-id")
    final_check_parser.add_argument("--require-recovery", action="store_true")
    final_check_parser.add_argument("--require-skills", action="store_true")
    final_check_parser.add_argument("--require-docs", action="store_true")
    final_check_parser.add_argument("--require-memory", action="store_true")
    final_check_parser.set_defaults(func=cmd_runtime_final_check)

    pipeline_parser = subparsers.add_parser("runtime-pipeline", help="Show execution pipeline stages for a run or goal")
    add_common_args(pipeline_parser)
    pipeline_parser.add_argument("--project", required=True)
    pipeline_parser.add_argument("--goal-id")
    pipeline_parser.add_argument("--run-id")
    pipeline_parser.set_defaults(func=cmd_runtime_pipeline)

    improvement_parser = subparsers.add_parser("runtime-review-improvements", help="Review candidate skills/rules for promotion readiness")
    add_common_args(improvement_parser)
    improvement_parser.add_argument("--project")
    improvement_parser.add_argument("--goal-id")
    improvement_parser.add_argument("--run-id")
    improvement_parser.add_argument("--limit", type=int, default=20)
    improvement_parser.add_argument("--min-count", type=int, default=2)
    improvement_parser.add_argument("--record", action="store_true")
    improvement_parser.set_defaults(func=cmd_runtime_review_improvements)

    report_parser = subparsers.add_parser("runtime-report", help="Generate a scoped runtime audit report")
    add_common_args(report_parser)
    report_parser.add_argument("--project", required=True)
    report_parser.add_argument("--goal-id")
    report_parser.add_argument("--run-id")
    report_parser.set_defaults(func=cmd_runtime_report)

    runtime_record_parser = subparsers.add_parser("runtime-record", help="Record Agent Runtime state")
    add_common_args(runtime_record_parser)
    runtime_record_parser.add_argument("--kind", choices=RUNTIME_KINDS, required=True)
    runtime_record_parser.add_argument("--project", required=True)
    runtime_record_parser.add_argument("--id")
    runtime_record_parser.add_argument("--goal-id")
    runtime_record_parser.add_argument("--run-id")
    runtime_record_parser.add_argument("--task-id")
    runtime_record_parser.add_argument("--objective")
    runtime_record_parser.add_argument("--title")
    runtime_record_parser.add_argument("--summary")
    runtime_record_parser.add_argument("--source")
    runtime_record_parser.add_argument("--name")
    runtime_record_parser.add_argument("--status")
    runtime_record_parser.add_argument("--priority", choices=("low", "normal", "high", "critical"), default="normal")
    runtime_record_parser.add_argument("--current-phase")
    runtime_record_parser.add_argument("--success-criteria")
    runtime_record_parser.add_argument("--task-layer")
    runtime_record_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"))
    runtime_record_parser.add_argument(
        "--assigned-role",
        choices=("planner", "executor", "reviewer", "memory-recorder", "verifier"),
    )
    runtime_record_parser.add_argument("--plan")
    runtime_record_parser.add_argument("--blocker")
    runtime_record_parser.add_argument(
        "--severity",
        choices=("info", "warning", "error", "critical"),
        default="info",
    )
    runtime_record_parser.add_argument(
        "--capability-status",
        choices=("complete", "partial", "broken-chain", "absent", "unconfirmed"),
        default="unconfirmed",
    )
    runtime_record_parser.add_argument("--frontend")
    runtime_record_parser.add_argument("--api")
    runtime_record_parser.add_argument("--backend")
    runtime_record_parser.add_argument("--data-state")
    runtime_record_parser.add_argument("--verification")
    runtime_record_parser.add_argument("--links", nargs="*")
    runtime_record_parser.add_argument(
        "--decision-type",
        choices=("plan", "tdd", "review", "rollback", "worktree", "performance", "execution-mode"),
    )
    runtime_record_parser.add_argument("--decision")
    runtime_record_parser.add_argument("--rationale")
    runtime_record_parser.add_argument("--scope")
    runtime_record_parser.add_argument("--command")
    runtime_record_parser.add_argument(
        "--result",
        choices=("passed", "failed", "blocked", "not-run"),
        default="not-run",
    )
    runtime_record_parser.add_argument("--strategy")
    runtime_record_parser.add_argument("--files", nargs="*")
    runtime_record_parser.add_argument("--candidate-name")
    runtime_record_parser.add_argument(
        "--source-type",
        choices=("preference", "lesson", "pattern", "skill", "rule"),
    )
    runtime_record_parser.add_argument("--trigger")
    runtime_record_parser.add_argument("--boundary")
    runtime_record_parser.add_argument("--review-result")
    runtime_record_parser.add_argument("--evidence")
    runtime_record_parser.set_defaults(func=cmd_runtime_record)

    runtime_list_parser = subparsers.add_parser("runtime-list", help="List Agent Runtime records")
    add_common_args(runtime_list_parser)
    runtime_list_parser.add_argument("--kind", choices=RUNTIME_KINDS, required=True)
    runtime_list_parser.add_argument("--project", required=True)
    runtime_list_parser.add_argument("--status")
    runtime_list_parser.add_argument("--goal-id")
    runtime_list_parser.add_argument("--limit", type=int, default=20)
    runtime_list_parser.set_defaults(func=cmd_runtime_list)

    runtime_summary_parser = subparsers.add_parser("runtime-summary", help="Summarize Agent Runtime state")
    add_common_args(runtime_summary_parser)
    runtime_summary_parser.add_argument("--project", required=True)
    runtime_summary_parser.add_argument("--limit", type=int, default=5)
    runtime_summary_parser.set_defaults(func=cmd_runtime_summary)

    policy_eval_parser = subparsers.add_parser("runtime-evaluate-policy", help="Evaluate Agent Runtime policy decisions")
    add_common_args(policy_eval_parser)
    policy_eval_parser.add_argument("--project", required=True)
    policy_eval_parser.add_argument("--goal-id")
    policy_eval_parser.add_argument("--task-id")
    policy_eval_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"), required=True)
    policy_eval_parser.add_argument(
        "--capability-status",
        choices=("complete", "partial", "broken-chain", "absent", "unconfirmed"),
        required=True,
    )
    policy_eval_parser.add_argument("--task-layer", nargs="*")
    policy_eval_parser.add_argument("--signal", nargs="*")
    policy_eval_parser.add_argument("--files", nargs="*")
    policy_eval_parser.add_argument("--record", action="store_true")
    policy_eval_parser.set_defaults(func=cmd_runtime_evaluate_policy)

    capability_scan_parser = subparsers.add_parser("runtime-scan-capability", help="Scan project files and classify capability state")
    add_common_args(capability_scan_parser)
    capability_scan_parser.add_argument("--project", required=True)
    capability_scan_parser.add_argument("--goal-id")
    capability_scan_parser.add_argument("--name", required=True)
    capability_scan_parser.add_argument("--term", nargs="*")
    capability_scan_parser.add_argument("--roots", nargs="*")
    capability_scan_parser.add_argument("--max-files", type=int, default=2000)
    capability_scan_parser.add_argument("--max-hits", type=int, default=8)
    capability_scan_parser.add_argument("--require-data", action="store_true")
    capability_scan_parser.add_argument("--require-verification", action="store_true")
    capability_scan_parser.add_argument("--use-memory", action="store_true")
    capability_scan_parser.add_argument("--record", action="store_true")
    capability_scan_parser.set_defaults(func=cmd_runtime_scan_capability)

    runtime_next_parser = subparsers.add_parser("runtime-next", help="Select the next runtime action from current state")
    add_common_args(runtime_next_parser)
    runtime_next_parser.add_argument("--project", required=True)
    runtime_next_parser.add_argument("--goal-id")
    runtime_next_parser.add_argument("--advance", action="store_true", help="Move the selected pending task to in_progress")
    runtime_next_parser.set_defaults(func=cmd_runtime_next)

    verification_plan_parser = subparsers.add_parser("runtime-plan-verification", help="Plan verification checks for a task")
    add_common_args(verification_plan_parser)
    verification_plan_parser.add_argument("--project", required=True)
    verification_plan_parser.add_argument("--goal-id")
    verification_plan_parser.add_argument("--task-id")
    verification_plan_parser.add_argument("--task-layer", nargs="*")
    verification_plan_parser.add_argument("--scale", choices=("L1", "L2", "L3", "L4"), default="L1")
    verification_plan_parser.add_argument("--files", nargs="*")
    verification_plan_parser.add_argument("--record", action="store_true")
    verification_plan_parser.set_defaults(func=cmd_runtime_plan_verification)

    recovery_plan_parser = subparsers.add_parser("runtime-plan-recovery", help="Plan a recovery or rollback strategy")
    add_common_args(recovery_plan_parser)
    recovery_plan_parser.add_argument("--project", required=True)
    recovery_plan_parser.add_argument("--goal-id")
    recovery_plan_parser.add_argument("--task-id")
    recovery_plan_parser.add_argument("--files", nargs="*")
    recovery_plan_parser.add_argument("--checkpoint")
    recovery_plan_parser.add_argument("--migration", action="store_true")
    recovery_plan_parser.add_argument("--feature-flag")
    recovery_plan_parser.add_argument("--evidence")
    recovery_plan_parser.add_argument("--record", action="store_true")
    recovery_plan_parser.set_defaults(func=cmd_runtime_plan_recovery)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
