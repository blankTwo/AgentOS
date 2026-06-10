#!/usr/bin/env python3
"""SQLite-backed memory tools for Codex Agent OS.

This script intentionally uses only Python standard library modules so the
memory backend can run in a fresh project without dependency installation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "memory" / "index.db"
DEFAULT_SCHEMA = ROOT / "memory" / "schema.sql"
PROJECT_MEMORY_DIR = ROOT / "memory" / "projects"

MEMORY_TYPES = (
    "lesson",
    "feature",
    "decision",
    "pattern",
    "validation",
    "candidate",
    "note",
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


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_initialized(conn: sqlite3.Connection, schema_path: Path = DEFAULT_SCHEMA) -> None:
    if not schema_path.exists():
        raise SystemExit(f"Schema file not found: {schema_path}")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    migrate_schema(conn)
    conn.commit()


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def migrate_schema(conn: sqlite3.Connection) -> None:
    if not column_exists(conn, "memory_items", "import_key"):
        conn.execute("ALTER TABLE memory_items ADD COLUMN import_key TEXT")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_items_import_key
        ON memory_items(import_key)
        WHERE import_key IS NOT NULL
        """
    )
    conn.execute(
        """
        INSERT INTO schema_meta(key, value)
        VALUES ('schema_version', '3')
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')
        """
    )


def normalize_csv(values: list[str] | None) -> str | None:
    if not values:
        return None
    flattened: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                flattened.append(part)
    return ",".join(dict.fromkeys(flattened)) if flattened else None


def normalize_project_slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"[^a-z0-9.\-\u4e00-\u9fff]+", "-", value)
    value = value.strip(".-")
    return value or "unknown-project"


def print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def build_safe_fts_query(query: str) -> str:
    """Build a forgiving FTS5 query from real-world bug/feature text.

    Raw FTS5 MATCH input can fail on punctuation-heavy strings such as
    "5MB -> 4.5MB" or file paths. Tokenizing and quoting each term keeps
    search useful without making users think in SQLite query syntax.
    """

    tokens = re.findall(r"[\w.\-/:\u4e00-\u9fff]+", query, flags=re.UNICODE)
    cleaned = [token.strip(".-/:_") for token in tokens]
    cleaned = [token for token in cleaned if token]
    if not cleaned:
        escaped = query.replace('"', '""').strip()
        return f'"{escaped}"' if escaped else '""'
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in cleaned)


def like_pattern(query: str) -> str:
    return f"%{query.replace('%', r'\%').replace('_', r'\_')}%"


def split_markdown_sections(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = "Document"
    current_level = 0
    current_lines: list[str] = []
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append(
                {
                    "title": current_title.strip(),
                    "level": str(current_level),
                    "body": body,
                }
            )

    for line in text.splitlines():
        match = heading_pattern.match(line)
        if match:
            flush()
            current_title = match.group(2).strip()
            current_level = len(match.group(1))
            current_lines = []
            continue
        current_lines.append(line)
    flush()
    return sections


def infer_memory_type(title: str, body: str) -> str:
    haystack = f"{title}\n{body}".lower()
    if any(token in haystack for token in ("pitfall", "bug", "root cause", "fix:", "踩坑", "问题", "修复")):
        return "lesson"
    if any(token in haystack for token in ("decision", "rationale", "reason:", "决策", "决定", "原因")):
        return "decision"
    if any(token in haystack for token in ("pattern", "trigger:", "scope:", "模式", "复用")):
        return "pattern"
    if any(token in haystack for token in ("validation", "verified", "验证", "待验证")):
        return "validation"
    if any(token in haystack for token in ("feature", "flow", "done:", "功能", "流程")):
        return "feature"
    return "note"


def summarize_markdown_body(body: str, max_chars: int = 500) -> str:
    lines = [line.strip(" -\t") for line in body.splitlines()]
    compact = " ".join(line for line in lines if line)
    if not compact:
        compact = body.strip()
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def markdown_import_key(project: str, path: Path, title: str, body: str) -> str:
    digest = hashlib.sha256(f"{project}\n{path.as_posix()}\n{title}\n{body}".encode("utf-8")).hexdigest()
    return f"markdown:{project}:{digest[:24]}"


def default_project_from_path(path: Path) -> str:
    return normalize_project_slug(path.stem)


def should_skip_project_memory(path: Path) -> bool:
    return path.name in {"_template.md", "_index.md"}


def resolve_workspace_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def workspace_relative(path: Path) -> Path:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT)
    except ValueError:
        return resolved


def cmd_init(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name"
        ).fetchall()
        conn.execute(
            "INSERT INTO maintenance_log(action, details) VALUES (?, ?)",
            ("init", f"Initialized memory database at {args.db}"),
        )
        conn.commit()
    print_json(
        {
            "ok": True,
            "db": str(args.db),
            "schema": str(args.schema),
            "tables": [row["name"] for row in tables],
        }
    )


def cmd_record_item(args: argparse.Namespace) -> None:
    metadata_json = args.metadata_json
    if args.metadata:
        metadata_json = json.dumps(args.metadata, ensure_ascii=False)

    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO memory_items(
                project,
                type,
                title,
                summary,
                problem,
                solution,
                patterns,
                files,
                tags,
                validation,
                confidence,
                source_session,
                import_key,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.project,
                args.type,
                args.title,
                args.summary,
                args.problem,
                args.solution,
                normalize_csv(args.patterns),
                normalize_csv(args.files),
                normalize_csv(args.tags),
                args.validation,
                args.confidence,
                args.source_session,
                None,
                metadata_json,
            ),
        )
        item_id = cur.lastrowid
        if args.source_session:
            conn.execute(
                """
                INSERT OR IGNORE INTO session_memory_links(session_id, memory_item_id, relation)
                VALUES (?, ?, ?)
                """,
                (args.source_session, item_id, "created"),
            )
        conn.commit()
    print_json({"ok": True, "id": item_id, "type": args.type, "project": args.project})


def cmd_search(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        fts_query = args.query if args.raw_fts else build_safe_fts_query(args.query)
        params: list[Any] = [fts_query]
        project_filter = ""
        type_filter = ""
        if args.project:
            project_filter = "AND mi.project = ?"
            params.append(args.project)
        if args.type:
            type_filter = "AND mi.type = ?"
            params.append(args.type)
        params.append(args.limit)
        try:
            rows = conn.execute(
                f"""
                SELECT
                    mi.id,
                    mi.project,
                    mi.type,
                    mi.title,
                    mi.summary,
                    mi.solution,
                    mi.patterns,
                    mi.files,
                    mi.tags,
                    mi.validation,
                    mi.confidence,
                    mi.created_at,
                    bm25(memory_fts) AS rank
                FROM memory_fts
                JOIN memory_items mi ON mi.id = memory_fts.rowid
                WHERE memory_fts MATCH ?
                {project_filter}
                {type_filter}
                ORDER BY rank
                LIMIT ?
                """,
                params,
            ).fetchall()
            mode = "fts5"
        except sqlite3.OperationalError as exc:
            if args.raw_fts:
                raise
            like_params: list[Any] = []
            project_where = ""
            type_where = ""
            pattern = like_pattern(args.query)
            like_params.extend([pattern] * 8)
            if args.project:
                project_where = "AND project = ?"
                like_params.append(args.project)
            if args.type:
                type_where = "AND type = ?"
                like_params.append(args.type)
            like_params.append(args.limit)
            rows = conn.execute(
                f"""
                SELECT id, project, type, title, summary, solution, patterns, files,
                       tags, validation, confidence, created_at, NULL AS rank
                FROM memory_items
                WHERE (
                    title LIKE ? ESCAPE '\\' OR
                    summary LIKE ? ESCAPE '\\' OR
                    problem LIKE ? ESCAPE '\\' OR
                    solution LIKE ? ESCAPE '\\' OR
                    patterns LIKE ? ESCAPE '\\' OR
                    files LIKE ? ESCAPE '\\' OR
                    tags LIKE ? ESCAPE '\\' OR
                    validation LIKE ? ESCAPE '\\'
                )
                {project_where}
                {type_where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                like_params,
            ).fetchall()
            mode = f"like-fallback: {exc}"
    print_json(
        {
            "ok": True,
            "query": args.query,
            "fts_query": fts_query,
            "mode": mode,
            "results": [row_to_dict(row) for row in rows],
        }
    )


def cmd_recent(args: argparse.Namespace) -> None:
    params: list[Any] = []
    project_filter = ""
    type_filter = ""
    if args.project:
        project_filter = "WHERE project = ?"
        params.append(args.project)
    if args.type:
        if project_filter:
            type_filter = "AND type = ?"
        else:
            type_filter = "WHERE type = ?"
        params.append(args.type)
    params.append(args.limit)

    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            f"""
            SELECT id, project, type, title, summary, tags, confidence, created_at
            FROM memory_items
            {project_filter}
            {type_filter}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    print_json({"ok": True, "results": [row_to_dict(row) for row in rows]})


def cmd_record_session(args: argparse.Namespace) -> None:
    session_id = args.id or str(uuid.uuid4())
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conn.execute(
            """
            INSERT INTO sessions(
                id,
                project,
                task_summary,
                key_decisions,
                validation_summary,
                memory_updated,
                status,
                started_at,
                metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                project = excluded.project,
                task_summary = excluded.task_summary,
                key_decisions = excluded.key_decisions,
                validation_summary = excluded.validation_summary,
                memory_updated = excluded.memory_updated,
                status = excluded.status,
                ended_at = datetime('now'),
                metadata_json = excluded.metadata_json
            """,
            (
                session_id,
                args.project,
                args.task_summary,
                args.key_decisions,
                args.validation_summary,
                1 if args.memory_updated else 0,
                args.status,
                args.started_at,
                args.metadata_json,
            ),
        )
        conn.commit()
    print_json({"ok": True, "session_id": session_id, "project": args.project})


def cmd_candidate_upsert(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        existing = conn.execute(
            "SELECT id, count FROM skill_candidates WHERE name = ? AND project = ?",
            (args.name, args.project),
        ).fetchone()
        if existing:
            candidate_id = existing["id"]
            new_count = existing["count"] + args.increment
            conn.execute(
                """
                UPDATE skill_candidates
                SET
                    trigger = COALESCE(?, trigger),
                    evidence = COALESCE(?, evidence),
                    validation = COALESCE(?, validation),
                    scope = COALESCE(?, scope),
                    boundary = COALESCE(?, boundary),
                    suggested_skill = COALESCE(?, suggested_skill),
                    tags = COALESCE(?, tags),
                    status = COALESCE(?, status),
                    confidence = ?,
                    count = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    args.trigger,
                    args.evidence,
                    args.validation,
                    args.scope,
                    args.boundary,
                    args.suggested_skill,
                    normalize_csv(args.tags),
                    args.status,
                    args.confidence,
                    new_count,
                    candidate_id,
                ),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO skill_candidates(
                    name,
                    project,
                    trigger,
                    evidence,
                    validation,
                    scope,
                    boundary,
                    suggested_skill,
                    tags,
                    status,
                    count,
                    confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.name,
                    args.project,
                    args.trigger,
                    args.evidence,
                    args.validation,
                    args.scope,
                    args.boundary,
                    args.suggested_skill,
                    normalize_csv(args.tags),
                    args.status,
                    args.increment,
                    args.confidence,
                ),
            )
            candidate_id = cur.lastrowid
        if args.evidence:
            conn.execute(
                """
                INSERT INTO skill_candidate_evidence(
                    candidate_id,
                    project,
                    memory_item_id,
                    evidence,
                    validation
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (candidate_id, args.project, args.memory_item_id, args.evidence, args.validation),
            )
        conn.commit()
    print_json({"ok": True, "candidate_id": candidate_id, "name": args.name, "project": args.project})


def cmd_candidates(args: argparse.Namespace) -> None:
    params: list[Any] = []
    where: list[str] = []
    if args.project:
        where.append("project = ?")
        params.append(args.project)
    if args.status:
        where.append("status = ?")
        params.append(args.status)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(args.limit)
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            f"""
            SELECT id, name, project, trigger, evidence, validation, scope, boundary,
                   suggested_skill, tags, status, count, confidence, updated_at
            FROM skill_candidates
            {where_sql}
            ORDER BY count DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    print_json({"ok": True, "results": [row_to_dict(row) for row in rows]})


def cmd_record_skill_usage(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO skill_usage(skill_name, project, task_summary, success, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (args.skill_name, args.project, args.task_summary, 1 if args.success else 0, args.notes),
        )
        conn.commit()
    print_json({"ok": True, "id": cur.lastrowid, "skill_name": args.skill_name})


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


def import_markdown_file(
    conn: sqlite3.Connection,
    path: Path,
    project: str,
    *,
    dry_run: bool = False,
    include_empty: bool = False,
) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    sections = split_markdown_sections(text)
    imported: list[dict[str, Any]] = []
    skipped = 0

    for section in sections:
        title = section["title"]
        body = section["body"]
        if not include_empty:
            normalized_body = body.strip()
            if not normalized_body or re.fullmatch(r"[-:\s\w/]*", normalized_body):
                skipped += 1
                continue
        memory_type = infer_memory_type(title, body)
        summary = summarize_markdown_body(body)
        source_path = workspace_relative(path)
        import_key = markdown_import_key(project, source_path, title, body)
        metadata = {
            "source": "markdown-import",
            "source_path": str(source_path.as_posix()),
            "heading": title,
            "heading_level": section["level"],
        }
        tags = normalize_csv(["imported", "markdown", memory_type])
        record = {
            "project": project,
            "type": memory_type,
            "title": title,
            "summary": summary,
            "tags": tags,
            "validation": "Imported from existing Markdown memory; verify against source before relying on it.",
            "confidence": 0.6,
            "import_key": import_key,
            "metadata_json": json.dumps(metadata, ensure_ascii=False),
        }
        if not dry_run:
            existing = conn.execute(
                "SELECT id FROM memory_items WHERE import_key = ?",
                (record["import_key"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE memory_items
                    SET
                        type = ?,
                        title = ?,
                        summary = ?,
                        files = ?,
                        tags = ?,
                        validation = ?,
                        confidence = ?,
                        metadata_json = ?,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (
                        record["type"],
                        record["title"],
                        record["summary"],
                        str(source_path.as_posix()),
                        record["tags"],
                        record["validation"],
                        record["confidence"],
                        record["metadata_json"],
                        existing["id"],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO memory_items(
                        project,
                        type,
                        title,
                        summary,
                        problem,
                        solution,
                        patterns,
                        files,
                        tags,
                        validation,
                        confidence,
                        source_session,
                        import_key,
                        metadata_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["project"],
                        record["type"],
                        record["title"],
                        record["summary"],
                        None,
                        None,
                        None,
                        str(source_path.as_posix()),
                        record["tags"],
                        record["validation"],
                        record["confidence"],
                        None,
                        record["import_key"],
                        record["metadata_json"],
                    ),
                )
        imported.append(record)

    return {
        "file": str(path),
        "project": project,
        "imported": len(imported),
        "skipped": skipped,
        "items": imported,
    }


def cmd_import_markdown(args: argparse.Namespace) -> None:
    args.memory_dir = resolve_workspace_path(args.memory_dir)
    if args.file:
        args.file = resolve_workspace_path(args.file)

    if args.all_projects:
        files = sorted(path for path in args.memory_dir.glob("*.md") if not should_skip_project_memory(path))
    else:
        if args.file:
            files = [args.file]
        elif args.project:
            files = [args.memory_dir / f"{normalize_project_slug(args.project)}.md"]
        else:
            raise SystemExit("Expected --project, --file, or --all-projects")

    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise SystemExit(f"Markdown memory file not found: {', '.join(missing)}")

    results: list[dict[str, Any]] = []
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        for path in files:
            project = normalize_project_slug(args.project) if args.project and len(files) == 1 else default_project_from_path(path)
            results.append(
                import_markdown_file(
                    conn,
                    path,
                    project,
                    dry_run=args.dry_run,
                    include_empty=args.include_empty,
                )
            )
        if not args.dry_run:
            conn.execute(
                "INSERT INTO maintenance_log(action, details) VALUES (?, ?)",
                ("import-markdown", f"files={len(files)} dry_run={args.dry_run}"),
            )
            conn.commit()

    print_json(
        {
            "ok": True,
            "dry_run": args.dry_run,
            "files": len(files),
            "imported": sum(result["imported"] for result in results),
            "skipped": sum(result["skipped"] for result in results),
            "results": results if args.verbose or args.dry_run else [
                {key: value for key, value in result.items() if key != "items"} for result in results
            ],
        }
    )


def cmd_stats(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        memory_by_type = conn.execute(
            "SELECT type, COUNT(*) AS count FROM memory_items GROUP BY type ORDER BY type"
        ).fetchall()
        candidates_by_status = conn.execute(
            "SELECT status, COUNT(*) AS count FROM skill_candidates GROUP BY status ORDER BY status"
        ).fetchall()
        skill_usage = conn.execute(
            """
            SELECT skill_name,
                   COUNT(*) AS uses,
                   ROUND(AVG(success) * 100, 2) AS success_rate
            FROM skill_usage
            GROUP BY skill_name
            ORDER BY uses DESC, skill_name
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        sessions = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()["count"]
    print_json(
        {
            "ok": True,
            "memory_by_type": [row_to_dict(row) for row in memory_by_type],
            "candidates_by_status": [row_to_dict(row) for row in candidates_by_status],
            "skill_usage": [row_to_dict(row) for row in skill_usage],
            "sessions": sessions,
        }
    )


def cmd_maintenance(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conn.execute("INSERT INTO memory_fts(memory_fts) VALUES ('optimize')")
        conn.execute("ANALYZE")
        conn.execute(
            "INSERT INTO maintenance_log(action, details) VALUES (?, ?)",
            ("maintenance", f"vacuum={args.vacuum}"),
        )
        conn.commit()
        if args.vacuum:
            conn.execute("VACUUM")
    print_json({"ok": True, "vacuum": args.vacuum})


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite index.db")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to schema.sql")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex Agent OS memory tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize memory database")
    add_common_args(init_parser)
    init_parser.set_defaults(func=cmd_init)

    record_parser = subparsers.add_parser("record-item", help="Record a memory item")
    add_common_args(record_parser)
    record_parser.add_argument("--project", required=True)
    record_parser.add_argument("--type", choices=MEMORY_TYPES, required=True)
    record_parser.add_argument("--title", required=True)
    record_parser.add_argument("--summary", required=True)
    record_parser.add_argument("--problem")
    record_parser.add_argument("--solution")
    record_parser.add_argument("--patterns", nargs="*")
    record_parser.add_argument("--files", nargs="*")
    record_parser.add_argument("--tags", nargs="*")
    record_parser.add_argument("--validation")
    record_parser.add_argument("--confidence", type=float, default=0.8)
    record_parser.add_argument("--source-session")
    record_parser.add_argument("--metadata-json")
    record_parser.add_argument("--metadata", action="append", help="key=value metadata entries")
    record_parser.set_defaults(func=cmd_record_item)

    search_parser = subparsers.add_parser("search", help="Search memory items using FTS5")
    add_common_args(search_parser)
    search_parser.add_argument("query")
    search_parser.add_argument("--project")
    search_parser.add_argument("--type", choices=MEMORY_TYPES)
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.add_argument("--raw-fts", action="store_true", help="Use query as raw FTS5 MATCH syntax")
    search_parser.set_defaults(func=cmd_search)

    recent_parser = subparsers.add_parser("recent", help="List recent memory items")
    add_common_args(recent_parser)
    recent_parser.add_argument("--project")
    recent_parser.add_argument("--type", choices=MEMORY_TYPES)
    recent_parser.add_argument("--limit", type=int, default=10)
    recent_parser.set_defaults(func=cmd_recent)

    session_parser = subparsers.add_parser("record-session", help="Record a session summary")
    add_common_args(session_parser)
    session_parser.add_argument("--id")
    session_parser.add_argument("--project", required=True)
    session_parser.add_argument("--task-summary", required=True)
    session_parser.add_argument("--key-decisions")
    session_parser.add_argument("--validation-summary")
    session_parser.add_argument("--memory-updated", action="store_true")
    session_parser.add_argument("--status", choices=("completed", "partial", "blocked", "failed"), default="completed")
    session_parser.add_argument("--started-at")
    session_parser.add_argument("--metadata-json")
    session_parser.set_defaults(func=cmd_record_session)

    candidate_parser = subparsers.add_parser("candidate-upsert", help="Create or update a skill candidate")
    add_common_args(candidate_parser)
    candidate_parser.add_argument("--name", required=True)
    candidate_parser.add_argument("--project", default="*")
    candidate_parser.add_argument("--trigger", required=True)
    candidate_parser.add_argument("--evidence", required=True)
    candidate_parser.add_argument("--validation")
    candidate_parser.add_argument("--scope")
    candidate_parser.add_argument("--boundary")
    candidate_parser.add_argument("--suggested-skill")
    candidate_parser.add_argument("--tags", nargs="*")
    candidate_parser.add_argument("--status", choices=("candidate", "reviewing", "approved", "rejected", "promoted"), default="candidate")
    candidate_parser.add_argument("--increment", type=int, default=1)
    candidate_parser.add_argument("--confidence", type=float, default=0.7)
    candidate_parser.add_argument("--memory-item-id", type=int)
    candidate_parser.set_defaults(func=cmd_candidate_upsert)

    candidates_parser = subparsers.add_parser("candidates", help="List skill candidates")
    add_common_args(candidates_parser)
    candidates_parser.add_argument("--project")
    candidates_parser.add_argument("--status", choices=("candidate", "reviewing", "approved", "rejected", "promoted"))
    candidates_parser.add_argument("--limit", type=int, default=20)
    candidates_parser.set_defaults(func=cmd_candidates)

    usage_parser = subparsers.add_parser("record-skill-usage", help="Record skill usage result")
    add_common_args(usage_parser)
    usage_parser.add_argument("--skill-name", required=True)
    usage_parser.add_argument("--project", default="*")
    usage_parser.add_argument("--task-summary")
    usage_parser.add_argument("--success", action="store_true")
    usage_parser.add_argument("--notes")
    usage_parser.set_defaults(func=cmd_record_skill_usage)

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

    import_parser = subparsers.add_parser("import-markdown", help="Import existing Markdown memory into SQLite")
    add_common_args(import_parser)
    import_parser.add_argument("--project", help="Project slug to import from memory/projects/<project>.md")
    import_parser.add_argument("--file", type=Path, help="Specific Markdown memory file to import")
    import_parser.add_argument("--all-projects", action="store_true", help="Import all project memory Markdown files")
    import_parser.add_argument("--memory-dir", type=Path, default=PROJECT_MEMORY_DIR, help="Project memory directory")
    import_parser.add_argument("--dry-run", action="store_true", help="Preview import without writing to SQLite")
    import_parser.add_argument("--include-empty", action="store_true", help="Import placeholder-like sections too")
    import_parser.add_argument("--verbose", action="store_true", help="Include imported item details in output")
    import_parser.set_defaults(func=cmd_import_markdown)

    stats_parser = subparsers.add_parser("stats", help="Show memory backend stats")
    add_common_args(stats_parser)
    stats_parser.add_argument("--limit", type=int, default=20)
    stats_parser.set_defaults(func=cmd_stats)

    maintenance_parser = subparsers.add_parser("maintenance", help="Optimize/analyze memory database")
    add_common_args(maintenance_parser)
    maintenance_parser.add_argument("--vacuum", action="store_true")
    maintenance_parser.set_defaults(func=cmd_maintenance)

    return parser


def parse_metadata(values: list[str] | None) -> dict[str, str] | None:
    if not values:
        return None
    data: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"Invalid metadata entry, expected key=value: {value}")
        key, val = value.split("=", 1)
        data[key.strip()] = val.strip()
    return data


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "metadata"):
        args.metadata = parse_metadata(args.metadata)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
