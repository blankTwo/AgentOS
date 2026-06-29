#!/usr/bin/env python3
"""Shared SQLite store helpers for Agent OS tools."""

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


def table_sql(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row["sql"] if row and row["sql"] else ""


def ensure_agent_events_event_types(conn: sqlite3.Connection) -> None:
    required_types = {
        "RecoveryPlanned",
        "RecoveryCheckpointCreated",
        "RecoveryMarked",
        "SkillValidated",
        "ModelRunRecorded",
        "SubAgentRunRecorded",
        "AdapterRegistered",
        "MetricsRecorded",
        "TraceExported",
    }
    current_sql = table_sql(conn, "agent_events")
    if not current_sql or required_types.issubset(set(re.findall(r"'([^']+)'", current_sql))):
        return

    conn.execute("ALTER TABLE agent_events RENAME TO agent_events_old")
    conn.execute(
        """
        CREATE TABLE agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            run_id TEXT,
            goal_id TEXT,
            task_id TEXT,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'UserRequest',
                'ContextReady',
                'GoalCreated',
                'RunCreated',
                'TaskPlanned',
                'TaskStarted',
                'TaskCompleted',
                'GoalStateChanged',
                'TaskStateChanged',
                'RunStateChanged',
                'VerificationPlanned',
                'VerificationPassed',
                'VerificationFailed',
                'DocumentationChecked',
                'MemoryUpdated',
                'KernelStep',
                'Blocked',
                'Recovered',
                'RecoveryPlanned',
                'RecoveryCheckpointCreated',
                'RecoveryMarked',
                'SkillValidated',
                'ModelRunRecorded',
                'SubAgentRunRecorded',
                'AdapterRegistered',
                'MetricsRecorded',
                'TraceExported'
            )),
            source TEXT NOT NULL DEFAULT 'runtime',
            summary TEXT NOT NULL,
            payload_json TEXT,
            severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN (
                'info',
                'warning',
                'error',
                'critical'
            )),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        INSERT INTO agent_events(
            id, project, run_id, goal_id, task_id, event_type, source, summary, payload_json, severity, created_at
        )
        SELECT id, project, run_id, goal_id, task_id, event_type, source, summary, payload_json, severity, created_at
        FROM agent_events_old
        """
    )
    conn.execute("DROP TABLE agent_events_old")


def ensure_model_runs_provider_types(conn: sqlite3.Connection) -> None:
    current_sql = table_sql(conn, "model_runs")
    if not current_sql or "'mock'" in current_sql:
        return

    conn.execute("ALTER TABLE model_runs RENAME TO model_runs_old")
    conn.execute(
        """
        CREATE TABLE model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            task_id TEXT,
            provider TEXT NOT NULL CHECK (provider IN (
                'openai',
                'anthropic',
                'google',
                'qwen',
                'deepseek',
                'local',
                'mock',
                'custom'
            )),
            model_name TEXT NOT NULL,
            adapter TEXT NOT NULL,
            operation TEXT NOT NULL DEFAULT 'inference' CHECK (operation IN (
                'inference',
                'planning',
                'review',
                'embedding',
                'rerank',
                'tool-call'
            )),
            status TEXT NOT NULL CHECK (status IN (
                'passed',
                'failed',
                'blocked',
                'not-run'
            )),
            duration_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_estimate REAL,
            prompt_summary TEXT,
            response_summary TEXT,
            failure_type TEXT CHECK (failure_type IN (
                'implementation',
                'test',
                'environment',
                'requirement',
                'unknown'
            )),
            failure_detail TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        INSERT INTO model_runs(
            id, project, goal_id, run_id, task_id, provider, model_name, adapter,
            operation, status, duration_ms, input_tokens, output_tokens, cost_estimate,
            prompt_summary, response_summary, failure_type, failure_detail, evidence, created_at
        )
        SELECT id, project, goal_id, run_id, task_id, provider, model_name, adapter,
               operation, status, duration_ms, input_tokens, output_tokens, cost_estimate,
               prompt_summary, response_summary, failure_type, failure_detail, evidence, created_at
        FROM model_runs_old
        """
    )
    conn.execute("DROP TABLE model_runs_old")


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
    add_column_if_missing(conn, "skill_manifests", "version", "TEXT")
    add_column_if_missing(conn, "skill_manifests", "conflicts_json", "TEXT")
    add_column_if_missing(conn, "skill_candidates", "goal_id", "TEXT")
    add_column_if_missing(conn, "skill_candidates", "run_id", "TEXT")
    add_column_if_missing(conn, "improvement_reviews", "goal_id", "TEXT")
    add_column_if_missing(conn, "improvement_reviews", "run_id", "TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            task_id TEXT,
            tool_type TEXT NOT NULL CHECK (tool_type IN (
                'shell',
                'git',
                'api',
                'browser'
            )),
            adapter TEXT NOT NULL,
            command TEXT,
            target TEXT,
            status TEXT NOT NULL CHECK (status IN (
                'passed',
                'failed',
                'blocked',
                'not-run'
            )),
            exit_code INTEGER,
            duration_ms INTEGER,
            stdout_summary TEXT,
            failure_type TEXT CHECK (failure_type IN (
                'implementation',
                'test',
                'environment',
                'requirement',
                'unknown'
            )),
            failure_detail TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            skill_name TEXT NOT NULL,
            version TEXT,
            description TEXT,
            path TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN (
                'valid',
                'invalid',
                'missing'
            )),
            dependencies_json TEXT,
            triggers_json TEXT,
            conflicts_json TEXT,
            issues_json TEXT,
            warnings_json TEXT,
            validated_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            task_id TEXT,
            provider TEXT NOT NULL CHECK (provider IN (
                'openai',
                'anthropic',
                'google',
                'qwen',
                'deepseek',
                'local',
                'mock',
                'custom'
            )),
            model_name TEXT NOT NULL,
            adapter TEXT NOT NULL,
            operation TEXT NOT NULL DEFAULT 'inference' CHECK (operation IN (
                'inference',
                'planning',
                'review',
                'embedding',
                'rerank',
                'tool-call'
            )),
            status TEXT NOT NULL CHECK (status IN (
                'passed',
                'failed',
                'blocked',
                'not-run'
            )),
            duration_ms INTEGER,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_estimate REAL,
            prompt_summary TEXT,
            response_summary TEXT,
            failure_type TEXT CHECK (failure_type IN (
                'implementation',
                'test',
                'environment',
                'requirement',
                'unknown'
            )),
            failure_detail TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS subagent_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            task_id TEXT,
            role TEXT NOT NULL CHECK (role IN (
                'planner',
                'executor',
                'reviewer',
                'verifier',
                'memory-recorder'
            )),
            status TEXT NOT NULL CHECK (status IN (
                'planned',
                'running',
                'completed',
                'blocked',
                'failed'
            )),
            input_summary TEXT NOT NULL,
            output_summary TEXT,
            boundary TEXT NOT NULL,
            handoff_to TEXT CHECK (handoff_to IN (
                'planner',
                'executor',
                'reviewer',
                'verifier',
                'memory-recorder'
            )),
            failure_type TEXT CHECK (failure_type IN (
                'implementation',
                'test',
                'environment',
                'requirement',
                'unknown'
            )),
            evidence TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS host_adapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            host_type TEXT NOT NULL CHECK (host_type IN (
                'codex',
                'claude',
                'cursor',
                'vscode',
                'cli',
                'mcp',
                'custom'
            )),
            adapter_name TEXT NOT NULL,
            entrypoint TEXT,
            capabilities_json TEXT,
            config_path TEXT,
            status TEXT NOT NULL DEFAULT 'available' CHECK (status IN (
                'available',
                'missing',
                'disabled',
                'invalid'
            )),
            issues_json TEXT,
            evidence TEXT,
            registered_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(project, host_type, adapter_name)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            scope TEXT NOT NULL DEFAULT 'project' CHECK (scope IN (
                'project',
                'goal',
                'run'
            )),
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            model_call_count INTEGER NOT NULL DEFAULT 0,
            verification_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            retry_count INTEGER NOT NULL DEFAULT 0,
            avg_duration_ms REAL,
            verification_pass_rate REAL,
            failure_rate REAL,
            metrics_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runtime_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            trace_json TEXT NOT NULL,
            exported_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            goal_id TEXT,
            run_id TEXT,
            source_type TEXT NOT NULL CHECK (source_type IN (
                'failure',
                'success',
                'partial',
                'manual'
            )),
            root_cause TEXT NOT NULL,
            summary TEXT NOT NULL,
            evidence TEXT,
            pattern TEXT,
            next_step TEXT,
            confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            run_id TEXT,
            goal_id TEXT,
            task_id TEXT,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'UserRequest',
                'ContextReady',
                'GoalCreated',
                'RunCreated',
                'TaskPlanned',
                'TaskStarted',
                'TaskCompleted',
                'GoalStateChanged',
                'TaskStateChanged',
                'RunStateChanged',
                'VerificationPlanned',
                'VerificationPassed',
                'VerificationFailed',
                'DocumentationChecked',
                'MemoryUpdated',
                'KernelStep',
                'Blocked',
                'Recovered',
                'RecoveryPlanned',
                'RecoveryCheckpointCreated',
                'RecoveryMarked',
                'SkillValidated',
                'ModelRunRecorded',
                'SubAgentRunRecorded',
                'AdapterRegistered',
                'MetricsRecorded',
                'TraceExported'
            )),
            source TEXT NOT NULL DEFAULT 'runtime',
            summary TEXT NOT NULL,
            payload_json TEXT,
            severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN (
                'info',
                'warning',
                'error',
                'critical'
            )),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    ensure_agent_events_event_types(conn)
    ensure_model_runs_provider_types(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_recommendations_goal ON skill_recommendations(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_recommendations_run ON skill_recommendations(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_candidates_goal ON skill_candidates(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_candidates_run ON skill_candidates(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_improvement_reviews_goal ON improvement_reviews(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_improvement_reviews_run ON improvement_reviews(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_project ON tool_runs(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_goal ON tool_runs(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_run ON tool_runs(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_tool_type ON tool_runs(tool_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_status ON tool_runs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_manifests_project ON skill_manifests(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_manifests_goal ON skill_manifests(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_manifests_run ON skill_manifests(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_manifests_skill ON skill_manifests(skill_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_manifests_status ON skill_manifests(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_project ON model_runs(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_goal ON model_runs(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_run ON model_runs(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_provider ON model_runs(provider)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_model_runs_status ON model_runs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagent_runs_project ON subagent_runs(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagent_runs_goal ON subagent_runs(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagent_runs_run ON subagent_runs(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagent_runs_role ON subagent_runs(role)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_subagent_runs_status ON subagent_runs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_host_adapters_project ON host_adapters(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_host_adapters_host_type ON host_adapters(host_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_host_adapters_status ON host_adapters(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_metrics_project ON runtime_metrics(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_metrics_goal ON runtime_metrics(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_metrics_run ON runtime_metrics(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_metrics_created_at ON runtime_metrics(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_traces_project ON runtime_traces(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_traces_goal ON runtime_traces(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_traces_run ON runtime_traces(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_traces_exported_at ON runtime_traces(exported_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_project ON reflections(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_goal ON reflections(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_run ON reflections(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reflections_source_type ON reflections(source_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_project ON agent_events(project)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_goal ON agent_events(goal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_type ON agent_events(event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at)")
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
        VALUES ('schema_version', '15')
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
