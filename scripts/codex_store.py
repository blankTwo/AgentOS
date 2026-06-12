#!/usr/bin/env python3
"""Shared SQLite store helpers for Codex Agent OS tools."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "memory" / "index.db"
DEFAULT_SCHEMA = ROOT / "memory" / "schema.sql"
PROJECT_MEMORY_DIR = ROOT / "memory" / "projects"


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


def add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not column_exists(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_schema(conn: sqlite3.Connection) -> None:
    if not column_exists(conn, "memory_items", "import_key"):
        conn.execute("ALTER TABLE memory_items ADD COLUMN import_key TEXT")
    add_column_if_missing(conn, "agent_goals", "source_request", "TEXT")
    add_column_if_missing(conn, "agent_goals", "final_result", "TEXT")
    add_column_if_missing(conn, "agent_tasks", "depends_on", "TEXT")
    add_column_if_missing(conn, "agent_tasks", "order_index", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(conn, "agent_tasks", "completed_evidence", "TEXT")
    add_column_if_missing(conn, "agent_observations", "observation_type", "TEXT NOT NULL DEFAULT 'manual'")
    add_column_if_missing(conn, "capability_nodes", "confidence", "REAL NOT NULL DEFAULT 0.7")
    add_column_if_missing(conn, "capability_nodes", "memory_evidence", "TEXT")
    add_column_if_missing(conn, "capability_nodes", "code_evidence", "TEXT")
    add_column_if_missing(conn, "capability_nodes", "test_evidence", "TEXT")
    add_column_if_missing(conn, "policy_decisions", "severity", "TEXT NOT NULL DEFAULT 'normal'")
    add_column_if_missing(conn, "policy_decisions", "blocking", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(conn, "verification_runs", "exit_code", "INTEGER")
    add_column_if_missing(conn, "verification_runs", "stdout_summary", "TEXT")
    add_column_if_missing(conn, "verification_runs", "failure_type", "TEXT")
    add_column_if_missing(conn, "verification_runs", "ran_at", "TEXT")
    add_column_if_missing(conn, "recovery_points", "checkpoint_ref", "TEXT")
    add_column_if_missing(conn, "recovery_points", "applied_at", "TEXT")
    add_column_if_missing(conn, "recovery_points", "obsolete_reason", "TEXT")
    add_column_if_missing(conn, "skill_recommendations", "goal_id", "TEXT")
    add_column_if_missing(conn, "skill_recommendations", "run_id", "TEXT")
    add_column_if_missing(conn, "skill_candidates", "goal_id", "TEXT")
    add_column_if_missing(conn, "skill_candidates", "run_id", "TEXT")
    add_column_if_missing(conn, "improvement_reviews", "goal_id", "TEXT")
    add_column_if_missing(conn, "improvement_reviews", "run_id", "TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_recommendations_goal ON skill_recommendations(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_recommendations_run ON skill_recommendations(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_candidates_goal ON skill_candidates(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_candidates_run ON skill_candidates(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_improvement_reviews_goal ON improvement_reviews(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_improvement_reviews_run ON improvement_reviews(run_id)")
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
        VALUES ('schema_version', '5')
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
    """Build a forgiving FTS5 query from real-world bug/feature text."""

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
    if any(token in haystack for token in ("pitfall", "bug", "root cause", "fix:")):
        return "lesson"
    if any(token in haystack for token in ("decision", "rationale", "reason:")):
        return "decision"
    if any(token in haystack for token in ("pattern", "trigger:", "scope:")):
        return "pattern"
    if any(token in haystack for token in ("validation", "verified", "pending validation")):
        return "validation"
    if any(token in haystack for token in ("feature", "flow", "done:")):
        return "feature"
    return "note"


def summarize_markdown_body(body: str, max_chars: int = 500) -> str:
    lines = [line.strip(" -	") for line in body.splitlines()]
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


def add_common_args(parser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite index.db")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to schema.sql")
