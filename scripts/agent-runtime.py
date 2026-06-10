#!/usr/bin/env python3
"""Agent Runtime controllers for Codex Agent OS."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from codex_store import (
    DEFAULT_DB,
    DEFAULT_SCHEMA,
    ROOT,
    add_common_args,
    connect,
    ensure_initialized,
    normalize_csv,
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
        },
        {
            "decision_type": "execution-mode",
            "decision": execution_mode,
            "rationale": "Execution mode derived from task scale, capability state, and risk signals.",
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
        }
    )

    worktree_needed = scale == "L4" or bool(
        normalized_signals.intersection({"large-refactor", "dependency-upgrade", "parallel-agent", "dirty-worktree", "architecture"})
    )
    decisions.append(
        {
            "decision_type": "worktree",
            "decision": "recommended" if worktree_needed else "not-needed",
            "rationale": "Worktree isolation is recommended for architecture, large refactor, dependency, dirty-worktree, and parallel-agent work.",
        }
    )

    performance_needed = bool(normalized_signals.intersection({"performance", "hot-path", "large-data", "render-path", "cache"}))
    decisions.append(
        {
            "decision_type": "performance",
            "decision": "required" if performance_needed else "not-needed",
            "rationale": "Performance check is required when performance, hot path, large data, render path, or cache risk is present.",
        }
    )

    return decisions


def cmd_runtime_evaluate_policy(args: argparse.Namespace) -> None:
    decisions = policy_decisions_for(
        scale=args.scale,
        capability_status=args.capability_status,
        task_layers=args.task_layer or [],
        signals=args.signal or [],
    )
    evidence = (
        f"scale={args.scale}; capability_status={args.capability_status}; "
        f"task_layers={','.join(args.task_layer or []) or 'none'}; "
        f"signals={','.join(args.signal or []) or 'none'}"
    )
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            for item in decisions:
                conn.execute(
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
                        item["decision_type"],
                        item["decision"],
                        item["rationale"],
                        evidence,
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
                if len(layer_hits[layer]) < max_hits_per_layer:
                    layer_hits[layer].append(rel_path.as_posix())

    status = derive_capability_status(
        layer_hits,
        require_data=args.require_data,
        require_verification=args.require_verification,
    )
    evidence = (
        f"terms={','.join(terms)}; roots={','.join(path.as_posix() for path in roots)}; "
        f"files_scanned={files_scanned}; files_matched={files_matched}"
    )
    links = [(layer, target) for layer, targets in layer_hits.items() for target in targets]

    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
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
                    args.name,
                    status,
                    compact_list(layer_hits["frontend"]),
                    compact_list(layer_hits["api"]),
                    compact_list(layer_hits["backend"]),
                    compact_list(layer_hits["data"]),
                    compact_list(layer_hits["verification"]),
                    evidence,
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
            "evidence": evidence,
            "layers": layer_hits,
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
