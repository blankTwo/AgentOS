#!/usr/bin/env python3
"""Agent Runtime controllers for Codex Agent OS."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

from codex_store import (
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
    "recovery",
    "improvement",
)

CONTAINER_PROJECT_NAMES = {".codex", ".config", ".meta", "workspace"}

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
    return ROOT.parent if ROOT.name == ".codex" else ROOT


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
    if test_files_available():
        signals.append("tests-available")
    else:
        signals.append("tests-missing")
    return list(dict.fromkeys(signals))


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


def recommend_skills(task_layers: list[str], stack: str) -> list[dict[str, str]]:
    available = load_skill_metadata()
    recommendations: list[dict[str, str]] = []
    for layer in task_layers:
        for skill in SKILL_BY_LAYER.get(layer, ()):
            meta = available.get(skill, {})
            recommendations.append(
                {
                    "skill_name": skill,
                    "rationale": meta.get("description") or f"{skill} matches {layer} layer work.",
                }
            )
    if "React" in stack and "feature-react" not in [item["skill_name"] for item in recommendations]:
        meta = available.get("feature-react", {})
        recommendations.append(
            {
                "skill_name": "feature-react",
                "rationale": meta.get("description")
                or "React stack detected; use as implementation helper when UI/API state code is touched.",
            }
        )
    deduped: dict[str, dict[str, str]] = {}
    for item in recommendations:
        deduped.setdefault(item["skill_name"], item)
    return list(deduped.values())


def load_skill_metadata() -> dict[str, dict[str, str]]:
    skills_dir = ROOT / "skills"
    metadata: dict[str, dict[str, str]] = {}
    if not skills_dir.exists():
        return metadata
    for skill_file in skills_dir.glob("*/SKILL.md"):
        name = skill_file.parent.name
        description = ""
        try:
            for line in skill_file.read_text(encoding="utf-8", errors="ignore").splitlines()[:20]:
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    description = line.split(":", 1)[1].strip()
        except OSError:
            continue
        metadata[name] = {
            "name": name,
            "description": description,
            "path": workspace_relative(skill_file).as_posix(),
        }
    return metadata


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
        }
    )


def verification_checks_for(task_layers: list[str], scale: str, changed_files: list[str]) -> list[dict[str, str]]:
    layers = {layer.lower() for layer in task_layers}
    files = [Path(value) for value in changed_files]
    suffixes = {path.suffix.lower() for path in files}
    checks: list[dict[str, str]] = []

    runtime_files = {"scripts/agent-runtime.py", "scripts/codex_store.py"}
    if "runtime" in layers or any(path.as_posix() in runtime_files for path in files):
        checks.extend(
            [
                {
                    "scope": "agent runtime syntax",
                    "command": "python -m py_compile scripts\\agent-runtime.py scripts\\codex_store.py",
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
                    conn.execute(
                        "UPDATE agent_tasks SET status = 'in_progress', updated_at = datetime('now') WHERE id = ?",
                        (task["id"],),
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


def cmd_runtime_select_skills(args: argparse.Namespace) -> None:
    layers = args.task_layer or []
    if not layers and args.request:
        layers = detect_task_layers(args.request, args.files)
    if not layers:
        layers = ["Runtime"]
    stack = args.stack or detect_stack(args.files)[0]
    recommendations = recommend_skills(layers, stack)
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
    print_json({"ok": True, "project": args.project, "task_layers": layers, "stack": stack, "skills": recommendations})


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
            "SELECT goal_id FROM agent_tasks WHERE id = ? AND project = ?",
            (args.id, args.project),
        ).fetchone()
        if not row:
            raise SystemExit(f"Runtime task not found: {args.id}")
        conn.execute(
            """
            UPDATE agent_tasks
            SET status = 'completed',
                completed_evidence = ?,
                evidence = COALESCE(?, evidence),
                updated_at = datetime('now')
            WHERE id = ? AND project = ?
            """,
            (args.evidence, args.evidence, args.id, args.project),
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
                conn.execute(
                    """
                    UPDATE agent_goals
                    SET status = 'completed',
                        current_phase = 'completed',
                        final_result = ?,
                        updated_at = datetime('now')
                    WHERE id = ? AND project = ?
                    """,
                    (args.evidence, row["goal_id"], args.project),
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


def command_is_allowed(command: str, allow_unsafe: bool = False) -> bool:
    if allow_unsafe:
        return True
    normalized = command.strip()
    return any(normalized.startswith(prefix) for prefix in SAFE_VERIFICATION_PREFIXES)


def summarize_output(text: str, limit: int = 1200) -> str:
    compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def classify_failure(exit_code: int | None, output: str) -> str | None:
    if exit_code == 0:
        return None
    lower = output.lower()
    if any(token in lower for token in ("assert", "expected", "actual", "failed")):
        return "implementation"
    if any(token in lower for token in ("syntaxerror", "traceback", "exception")):
        return "implementation"
    if any(token in lower for token in ("no such file", "not found", "permission", "environment")):
        return "environment"
    return "unknown"


def cmd_runtime_run_verification(args: argparse.Namespace) -> None:
    command = args.command
    verification_id = args.id
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = None
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
        else:
            completed = subprocess.run(command, cwd=ROOT, shell=True, text=True, capture_output=True, timeout=args.timeout)
            output = f"{completed.stdout}\n{completed.stderr}".strip()
            result = "passed" if completed.returncode == 0 else "failed"
            exit_code = completed.returncode
            stdout_summary = summarize_output(output)
            failure_type = classify_failure(exit_code, output)

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
            "stdout_summary": stdout_summary,
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
        conn.commit()
    print_json({"ok": True, "id": args.id, "status": args.status})


def cmd_runtime_final_check(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        goal_id = args.goal_id
        context_id = None
        if args.run_id:
            run = conn.execute(
                "SELECT goal_id, context_id FROM runtime_runs WHERE id = ? AND project = ?",
                (args.run_id, args.project),
            ).fetchone()
            if not run:
                raise SystemExit(f"Runtime run not found: {args.run_id}")
            goal_id = goal_id or run["goal_id"]
            context_id = run["context_id"]

        context_query = "SELECT COUNT(*) AS count FROM runtime_contexts WHERE project = ?"
        context_params: list[Any] = [args.project]
        if context_id:
            context_query += " AND id = ?"
            context_params.append(context_id)
        context_count = conn.execute(context_query, context_params).fetchone()["count"]

        goal_clause = " AND goal_id = ?" if goal_id else ""
        goal_params: list[Any] = [args.project] + ([goal_id] if goal_id else [])
        policy_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM policy_decisions WHERE project = ?{goal_clause}",
            goal_params,
        ).fetchone()["count"]
        verification_rows = conn.execute(
            f"SELECT result, COUNT(*) AS count FROM verification_runs WHERE project = ?{goal_clause} GROUP BY result",
            goal_params,
        ).fetchall()
        recovery_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM recovery_points WHERE project = ?{goal_clause}",
            goal_params,
        ).fetchone()["count"]
        skill_clause = ""
        skill_params: list[Any] = [args.project]
        if goal_id:
            skill_clause = " AND goal_id = ?"
            skill_params.append(goal_id)
        if args.run_id:
            skill_clause += " AND run_id = ?"
            skill_params.append(args.run_id)
        skill_count = conn.execute(
            f"SELECT COUNT(*) AS count FROM skill_recommendations WHERE project = ?{skill_clause}",
            skill_params,
        ).fetchone()["count"]
        open_tasks = conn.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM agent_tasks
            WHERE project = ?{goal_clause}
              AND status IN ('pending', 'in_progress', 'blocked')
            """,
            goal_params,
        ).fetchone()["count"]
    verification = {row["result"]: row["count"] for row in verification_rows}
    missing: list[str] = []
    if context_count == 0:
        missing.append("runtime context")
    if policy_count == 0:
        missing.append("policy decisions")
    if not verification:
        missing.append("verification records")
    if args.require_recovery and recovery_count == 0:
        missing.append("recovery point")
    if args.require_skills and skill_count == 0:
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
            "context_count": context_count,
            "policy_count": policy_count,
            "verification": verification,
            "recovery_count": recovery_count,
            "skill_recommendation_count": skill_count,
            "open_tasks": open_tasks,
        }
    )


def cmd_runtime_review_improvements(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        candidates = conn.execute(
            """
            SELECT name, project, trigger, evidence, validation, scope, boundary,
                   status, count, confidence
            FROM skill_candidates
            WHERE (? IS NULL OR project = ? OR project = '*')
              AND status IN ('candidate', 'reviewing', 'approved')
            ORDER BY count DESC, updated_at DESC
            LIMIT ?
            """,
            (args.project, args.project, args.limit),
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
                        project, candidate_name, source_type, trigger, evidence,
                        scope, boundary, status, review_result
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(project, candidate_name, source_type) DO UPDATE SET
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
    print_json({"ok": True, "project": args.project, "reviews": reviews})


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

    context_id = None
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            context_id = record_runtime_context(conn, context)
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
                    "execute-planned-tasks",
                ),
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
                conn.execute(
                    """
                    INSERT INTO agent_tasks(
                        id, goal_id, project, title, task_layer, scale, status,
                        assigned_role, plan, evidence, order_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{run_id}-task-{index}",
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
            if recovery_strategy:
                conn.execute(
                    """
                    INSERT INTO recovery_points(project, goal_id, strategy, files, status, evidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (project, goal_id, recovery_strategy, normalize_csv(context["files"]), "planned", "runtime-run recovery planning"),
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
            "next_action": "execute-planned-tasks",
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
                    project, candidate_name, source_type, trigger, evidence,
                    scope, boundary, status, review_result
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project, candidate_name, source_type) DO UPDATE SET
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
        "recovery": ("recovery_points", "created_at"),
        "improvement": ("improvement_reviews", "updated_at"),
    }
    table, order_column = table_by_kind[args.kind]
    where = ["project = ?"]
    params: list[Any] = [args.project]

    if args.status and args.kind in {"goal", "task", "capability", "recovery", "improvement"}:
        status_column = "status"
        where.append(f"{status_column} = ?")
        params.append(args.status)
    if args.goal_id and args.kind in {"task", "observation", "policy", "verification", "recovery"}:
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
            "open_improvements": open_improvements,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex Agent OS Agent Runtime controllers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    context_parser = subparsers.add_parser("runtime-detect-context", help="Detect project, stack, task layer, and scale")
    add_common_args(context_parser)
    context_parser.add_argument("--project")
    context_parser.add_argument("--request", required=True)
    context_parser.add_argument("--files", nargs="*")
    context_parser.add_argument("--record", action="store_true")
    context_parser.set_defaults(func=cmd_runtime_detect_context)

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

    skill_parser = subparsers.add_parser("runtime-select-skills", help="Recommend skills for a task")
    add_common_args(skill_parser)
    skill_parser.add_argument("--project", required=True)
    skill_parser.add_argument("--goal-id")
    skill_parser.add_argument("--run-id")
    skill_parser.add_argument("--request")
    skill_parser.add_argument("--task-layer", nargs="*")
    skill_parser.add_argument("--stack")
    skill_parser.add_argument("--files", nargs="*")
    skill_parser.add_argument("--record", action="store_true")
    skill_parser.set_defaults(func=cmd_runtime_select_skills)

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

    final_check_parser = subparsers.add_parser("runtime-final-check", help="Check final runtime gate completeness")
    add_common_args(final_check_parser)
    final_check_parser.add_argument("--project", required=True)
    final_check_parser.add_argument("--goal-id")
    final_check_parser.add_argument("--run-id")
    final_check_parser.add_argument("--require-recovery", action="store_true")
    final_check_parser.add_argument("--require-skills", action="store_true")
    final_check_parser.set_defaults(func=cmd_runtime_final_check)

    improvement_parser = subparsers.add_parser("runtime-review-improvements", help="Review candidate skills/rules for promotion readiness")
    add_common_args(improvement_parser)
    improvement_parser.add_argument("--project")
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
