PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO schema_meta(key, value)
VALUES ('schema_version', '15')
ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now');

CREATE TABLE IF NOT EXISTS memory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN (
        'lesson',
        'feature',
        'decision',
        'pattern',
        'validation',
        'candidate',
        'note'
    )),
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    problem TEXT,
    solution TEXT,
    patterns TEXT,
    files TEXT,
    tags TEXT,
    validation TEXT,
    confidence REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
    source_session TEXT,
    import_key TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_items_project ON memory_items(project);
CREATE INDEX IF NOT EXISTS idx_memory_items_type ON memory_items(type);
CREATE INDEX IF NOT EXISTS idx_memory_items_created_at ON memory_items(created_at);
CREATE INDEX IF NOT EXISTS idx_memory_items_tags ON memory_items(tags);
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_items_import_key
ON memory_items(import_key)
WHERE import_key IS NOT NULL;

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    title,
    summary,
    problem,
    solution,
    patterns,
    files,
    tags,
    validation,
    project,
    content='memory_items',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memory_items_ai AFTER INSERT ON memory_items
BEGIN
    INSERT INTO memory_fts(
        rowid,
        title,
        summary,
        problem,
        solution,
        patterns,
        files,
        tags,
        validation,
        project
    )
    VALUES (
        new.id,
        new.title,
        new.summary,
        new.problem,
        new.solution,
        new.patterns,
        new.files,
        new.tags,
        new.validation,
        new.project
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_items_ad AFTER DELETE ON memory_items
BEGIN
    INSERT INTO memory_fts(
        memory_fts,
        rowid,
        title,
        summary,
        problem,
        solution,
        patterns,
        files,
        tags,
        validation,
        project
    )
    VALUES (
        'delete',
        old.id,
        old.title,
        old.summary,
        old.problem,
        old.solution,
        old.patterns,
        old.files,
        old.tags,
        old.validation,
        old.project
    );
END;

CREATE TRIGGER IF NOT EXISTS memory_items_au AFTER UPDATE ON memory_items
BEGIN
    INSERT INTO memory_fts(
        memory_fts,
        rowid,
        title,
        summary,
        problem,
        solution,
        patterns,
        files,
        tags,
        validation,
        project
    )
    VALUES (
        'delete',
        old.id,
        old.title,
        old.summary,
        old.problem,
        old.solution,
        old.patterns,
        old.files,
        old.tags,
        old.validation,
        old.project
    );

    INSERT INTO memory_fts(
        rowid,
        title,
        summary,
        problem,
        solution,
        patterns,
        files,
        tags,
        validation,
        project
    )
    VALUES (
        new.id,
        new.title,
        new.summary,
        new.problem,
        new.solution,
        new.patterns,
        new.files,
        new.tags,
        new.validation,
        new.project
    );
END;

CREATE TABLE IF NOT EXISTS skill_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '*',
    goal_id TEXT,
    run_id TEXT,
    trigger TEXT NOT NULL,
    evidence TEXT NOT NULL,
    validation TEXT,
    scope TEXT,
    boundary TEXT,
    suggested_skill TEXT,
    tags TEXT,
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN (
        'candidate',
        'reviewing',
        'approved',
        'rejected',
        'promoted'
    )),
    count INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(name, project)
);

CREATE INDEX IF NOT EXISTS idx_skill_candidates_project ON skill_candidates(project);
CREATE INDEX IF NOT EXISTS idx_skill_candidates_status ON skill_candidates(status);
CREATE INDEX IF NOT EXISTS idx_skill_candidates_updated_at ON skill_candidates(updated_at);

CREATE TABLE IF NOT EXISTS skill_candidate_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER NOT NULL,
    project TEXT NOT NULL,
    memory_item_id INTEGER,
    evidence TEXT NOT NULL,
    validation TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(candidate_id) REFERENCES skill_candidates(id) ON DELETE CASCADE,
    FOREIGN KEY(memory_item_id) REFERENCES memory_items(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    task_summary TEXT NOT NULL,
    key_decisions TEXT,
    validation_summary TEXT,
    memory_updated INTEGER NOT NULL DEFAULT 0 CHECK (memory_updated IN (0, 1)),
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN (
        'completed',
        'partial',
        'blocked',
        'failed'
    )),
    started_at TEXT,
    ended_at TEXT NOT NULL DEFAULT (datetime('now')),
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
CREATE INDEX IF NOT EXISTS idx_sessions_ended_at ON sessions(ended_at);

CREATE TABLE IF NOT EXISTS session_memory_links (
    session_id TEXT NOT NULL,
    memory_item_id INTEGER NOT NULL,
    relation TEXT NOT NULL DEFAULT 'created',
    PRIMARY KEY(session_id, memory_item_id, relation),
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(memory_item_id) REFERENCES memory_items(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS skill_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_name TEXT NOT NULL,
    project TEXT NOT NULL DEFAULT '*',
    task_summary TEXT,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    notes TEXT,
    used_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_skill_usage_skill ON skill_usage(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_usage_project ON skill_usage(project);
CREATE INDEX IF NOT EXISTS idx_skill_usage_used_at ON skill_usage(used_at);

CREATE TABLE IF NOT EXISTS maintenance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agent_goals (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN (
        'active',
        'completed',
        'blocked',
        'cancelled'
    )),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN (
        'low',
        'normal',
        'high',
        'critical'
    )),
    current_phase TEXT,
    success_criteria TEXT,
    evidence TEXT,
    source_request TEXT,
    final_result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_agent_goals_project ON agent_goals(project);
CREATE INDEX IF NOT EXISTS idx_agent_goals_status ON agent_goals(status);
CREATE INDEX IF NOT EXISTS idx_agent_goals_updated_at ON agent_goals(updated_at);

CREATE TABLE IF NOT EXISTS agent_tasks (
    id TEXT PRIMARY KEY,
    goal_id TEXT,
    project TEXT NOT NULL,
    title TEXT NOT NULL,
    task_layer TEXT,
    scale TEXT CHECK (scale IN ('L1', 'L2', 'L3', 'L4')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'in_progress',
        'completed',
        'blocked',
        'cancelled'
    )),
    assigned_role TEXT CHECK (assigned_role IN (
        'planner',
        'executor',
        'reviewer',
        'memory-recorder',
        'verifier'
    )),
    plan TEXT,
    evidence TEXT,
    blocker TEXT,
    depends_on TEXT,
    order_index INTEGER NOT NULL DEFAULT 0,
    completed_evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_tasks_goal ON agent_tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_project ON agent_tasks(project);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_scale ON agent_tasks(scale);

CREATE TABLE IF NOT EXISTS agent_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    source TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence TEXT,
    observation_type TEXT NOT NULL DEFAULT 'manual' CHECK (observation_type IN (
        'file',
        'test',
        'memory',
        'git',
        'user',
        'runtime',
        'manual'
    )),
    severity TEXT NOT NULL DEFAULT 'info' CHECK (severity IN (
        'info',
        'warning',
        'error',
        'critical'
    )),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_observations_project ON agent_observations(project);
CREATE INDEX IF NOT EXISTS idx_agent_observations_goal ON agent_observations(goal_id);
CREATE INDEX IF NOT EXISTS idx_agent_observations_created_at ON agent_observations(created_at);

CREATE TABLE IF NOT EXISTS capability_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'complete',
        'partial',
        'broken-chain',
        'absent',
        'unconfirmed'
    )),
    frontend TEXT,
    api TEXT,
    backend TEXT,
    data_state TEXT,
    verification TEXT,
    evidence TEXT,
    confidence REAL NOT NULL DEFAULT 0.7 CHECK (confidence >= 0 AND confidence <= 1),
    memory_evidence TEXT,
    code_evidence TEXT,
    test_evidence TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project, name)
);

CREATE INDEX IF NOT EXISTS idx_capability_nodes_project ON capability_nodes(project);
CREATE INDEX IF NOT EXISTS idx_capability_nodes_status ON capability_nodes(status);

CREATE TABLE IF NOT EXISTS capability_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id INTEGER NOT NULL,
    relation TEXT NOT NULL,
    target TEXT NOT NULL,
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(capability_id) REFERENCES capability_nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capability_links_capability ON capability_links(capability_id);

CREATE TABLE IF NOT EXISTS policy_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    task_id TEXT,
    decision_type TEXT NOT NULL CHECK (decision_type IN (
        'plan',
        'tdd',
        'review',
        'rollback',
        'worktree',
        'performance',
        'execution-mode'
    )),
    decision TEXT NOT NULL,
    rationale TEXT,
    evidence TEXT,
    severity TEXT NOT NULL DEFAULT 'normal' CHECK (severity IN (
        'low',
        'normal',
        'high',
        'critical'
    )),
    blocking INTEGER NOT NULL DEFAULT 0 CHECK (blocking IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_decisions_project ON policy_decisions(project);
CREATE INDEX IF NOT EXISTS idx_policy_decisions_goal ON policy_decisions(goal_id);
CREATE INDEX IF NOT EXISTS idx_policy_decisions_type ON policy_decisions(decision_type);

CREATE TABLE IF NOT EXISTS verification_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    task_id TEXT,
    scope TEXT NOT NULL,
    command TEXT,
    result TEXT NOT NULL CHECK (result IN (
        'passed',
        'failed',
        'blocked',
        'not-run'
    )),
    evidence TEXT,
    exit_code INTEGER,
    stdout_summary TEXT,
    failure_type TEXT CHECK (failure_type IN (
        'implementation',
        'test',
        'environment',
        'requirement',
        'unknown'
    )),
    ran_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_runs_project ON verification_runs(project);
CREATE INDEX IF NOT EXISTS idx_verification_runs_goal ON verification_runs(goal_id);
CREATE INDEX IF NOT EXISTS idx_verification_runs_result ON verification_runs(result);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_runs_project ON tool_runs(project);
CREATE INDEX IF NOT EXISTS idx_tool_runs_goal ON tool_runs(goal_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_run ON tool_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_runs_tool_type ON tool_runs(tool_type);
CREATE INDEX IF NOT EXISTS idx_tool_runs_status ON tool_runs(status);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_model_runs_project ON model_runs(project);
CREATE INDEX IF NOT EXISTS idx_model_runs_goal ON model_runs(goal_id);
CREATE INDEX IF NOT EXISTS idx_model_runs_run ON model_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_model_runs_provider ON model_runs(provider);
CREATE INDEX IF NOT EXISTS idx_model_runs_status ON model_runs(status);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_subagent_runs_project ON subagent_runs(project);
CREATE INDEX IF NOT EXISTS idx_subagent_runs_goal ON subagent_runs(goal_id);
CREATE INDEX IF NOT EXISTS idx_subagent_runs_run ON subagent_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_subagent_runs_role ON subagent_runs(role);
CREATE INDEX IF NOT EXISTS idx_subagent_runs_status ON subagent_runs(status);

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
);

CREATE INDEX IF NOT EXISTS idx_host_adapters_project ON host_adapters(project);
CREATE INDEX IF NOT EXISTS idx_host_adapters_host_type ON host_adapters(host_type);
CREATE INDEX IF NOT EXISTS idx_host_adapters_status ON host_adapters(status);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_metrics_project ON runtime_metrics(project);
CREATE INDEX IF NOT EXISTS idx_runtime_metrics_goal ON runtime_metrics(goal_id);
CREATE INDEX IF NOT EXISTS idx_runtime_metrics_run ON runtime_metrics(run_id);
CREATE INDEX IF NOT EXISTS idx_runtime_metrics_created_at ON runtime_metrics(created_at);

CREATE TABLE IF NOT EXISTS runtime_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    run_id TEXT,
    trace_json TEXT NOT NULL,
    exported_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_traces_project ON runtime_traces(project);
CREATE INDEX IF NOT EXISTS idx_runtime_traces_goal ON runtime_traces(goal_id);
CREATE INDEX IF NOT EXISTS idx_runtime_traces_run ON runtime_traces(run_id);
CREATE INDEX IF NOT EXISTS idx_runtime_traces_exported_at ON runtime_traces(exported_at);

CREATE TABLE IF NOT EXISTS recovery_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    task_id TEXT,
    strategy TEXT NOT NULL,
    files TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN (
        'planned',
        'available',
        'used',
        'obsolete'
    )),
    evidence TEXT,
    checkpoint_ref TEXT,
    applied_at TEXT,
    obsolete_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(task_id) REFERENCES agent_tasks(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_recovery_points_project ON recovery_points(project);
CREATE INDEX IF NOT EXISTS idx_recovery_points_goal ON recovery_points(goal_id);
CREATE INDEX IF NOT EXISTS idx_recovery_points_status ON recovery_points(status);

CREATE TABLE IF NOT EXISTS improvement_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL DEFAULT '*',
    goal_id TEXT,
    run_id TEXT,
    candidate_name TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN (
        'preference',
        'lesson',
        'pattern',
        'skill',
        'rule'
    )),
    trigger TEXT NOT NULL,
    evidence TEXT NOT NULL,
    scope TEXT,
    boundary TEXT,
    status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN (
        'candidate',
        'reviewing',
        'approved',
        'rejected',
        'promoted'
    )),
    review_result TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(project, candidate_name, source_type)
);

CREATE INDEX IF NOT EXISTS idx_improvement_reviews_project ON improvement_reviews(project);
CREATE INDEX IF NOT EXISTS idx_improvement_reviews_status ON improvement_reviews(status);

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
);

CREATE INDEX IF NOT EXISTS idx_reflections_project ON reflections(project);
CREATE INDEX IF NOT EXISTS idx_reflections_goal ON reflections(goal_id);
CREATE INDEX IF NOT EXISTS idx_reflections_run ON reflections(run_id);
CREATE INDEX IF NOT EXISTS idx_reflections_source_type ON reflections(source_type);

CREATE TABLE IF NOT EXISTS runtime_contexts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    request TEXT NOT NULL,
    stack TEXT NOT NULL,
    stack_confidence TEXT NOT NULL CHECK (stack_confidence IN (
        'high',
        'medium',
        'low'
    )),
    task_layers TEXT,
    scale TEXT NOT NULL CHECK (scale IN ('L1', 'L2', 'L3', 'L4')),
    intent TEXT,
    files TEXT,
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_runtime_contexts_project ON runtime_contexts(project);
CREATE INDEX IF NOT EXISTS idx_runtime_contexts_created_at ON runtime_contexts(created_at);

CREATE TABLE IF NOT EXISTS runtime_runs (
    id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    request TEXT NOT NULL,
    goal_id TEXT,
    status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN (
        'planned',
        'ready',
        'running',
        'completed',
        'blocked',
        'failed'
    )),
    context_id INTEGER,
    capability_name TEXT,
    capability_status TEXT CHECK (capability_status IN (
        'complete',
        'partial',
        'broken-chain',
        'absent',
        'unconfirmed'
    )),
    execution_mode TEXT,
    summary TEXT,
    next_action TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(context_id) REFERENCES runtime_contexts(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_runs_project ON runtime_runs(project);
CREATE INDEX IF NOT EXISTS idx_runtime_runs_status ON runtime_runs(status);

CREATE TABLE IF NOT EXISTS skill_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    goal_id TEXT,
    run_id TEXT,
    task_layers TEXT,
    stack TEXT,
    skill_name TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'recommended' CHECK (status IN (
        'recommended',
        'used',
        'skipped'
    )),
    evidence TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_skill_recommendations_project ON skill_recommendations(project);
CREATE INDEX IF NOT EXISTS idx_skill_recommendations_skill ON skill_recommendations(skill_name);

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
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(goal_id) REFERENCES agent_goals(id) ON DELETE SET NULL,
    FOREIGN KEY(run_id) REFERENCES runtime_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_skill_manifests_project ON skill_manifests(project);
CREATE INDEX IF NOT EXISTS idx_skill_manifests_goal ON skill_manifests(goal_id);
CREATE INDEX IF NOT EXISTS idx_skill_manifests_run ON skill_manifests(run_id);
CREATE INDEX IF NOT EXISTS idx_skill_manifests_skill ON skill_manifests(skill_name);
CREATE INDEX IF NOT EXISTS idx_skill_manifests_status ON skill_manifests(status);

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
);

CREATE INDEX IF NOT EXISTS idx_agent_events_project ON agent_events(project);
CREATE INDEX IF NOT EXISTS idx_agent_events_goal ON agent_events(goal_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_run ON agent_events(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_type ON agent_events(event_type);
CREATE INDEX IF NOT EXISTS idx_agent_events_created_at ON agent_events(created_at);
