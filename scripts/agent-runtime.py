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
from typing import Any, Dict, List, Optional, Tuple

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
    "intent",
    "action-proposal",
    "feedback",
    "drift",
    "approval",
    "plan-version",
    "event-message",
    "schedule-item",
    "resource-lease",
    "quality-score",
    "self-audit-finding",
    "benchmark",
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
    "IntentDetected",
    "ActionProposed",
    "ActionBlocked",
    "ActionApproved",
    "FeedbackRecorded",
    "DriftDetected",
    "ReanchorRequested",
    "PlanRevised",
)

EVENT_BUS_STATUSES = ("pending", "delivered", "acknowledged", "failed", "cancelled")
SCHEDULE_STATUSES = ("queued", "ready", "running", "completed", "blocked", "cancelled")
RESOURCE_TYPES = ("shell", "git", "api", "browser", "model", "subagent", "memory", "workspace", "custom")
RESOURCE_LEASE_STATUSES = ("requested", "granted", "denied", "released", "expired")
SELF_AUDIT_STATUSES = ("open", "acknowledged", "resolved", "ignored")
BENCHMARK_DIRECTIONS = ("lower-is-better", "higher-is-better", "equal")

MODEL_PROVIDERS = ("openai", "anthropic", "google", "qwen", "deepseek", "local", "mock", "custom")
SUBAGENT_ROLES = ("planner", "executor", "reviewer", "verifier", "documentation-recorder", "memory-recorder")
HOST_TYPES = ("codex", "claude", "qwen", "cursor", "vscode", "cli", "mcp", "custom")
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
    "qwen": {
        "shell",
        "git",
        "runtime-cli",
        "skills",
        "memory",
        "tool-runtime",
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
CURRENT_SCHEMA_VERSION = "21"
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
    "Bugfix": ("bug", "fix", "error", "exception", "failure", "broken", "regression", "排查", "分析", "定位", "异常", "报错", "失败"),
    "Refactor": ("refactor", "split", "restructure", "maintainability", "responsibility", "reuse"),
}

READ_ONLY_INTENT_TOKENS = (
    "investigate",
    "diagnose",
    "inspect",
    "review",
    "audit",
    "analyze",
    "analyse",
    "explain why",
    "find the root cause",
    "look into",
    "排查",
    "好好排查",
    "分析",
    "定位原因",
    "看看为什么",
    "检查一下",
)

MUTATION_INTENT_TOKENS = (
    "fix",
    "modify",
    "implement",
    "add",
    "remove",
    "delete",
    "update",
    "refactor",
    "optimize",
    "commit",
    "directly handle",
    "修一下",
    "修复",
    "改一下",
    "修改",
    "实现",
    "加上",
    "删除",
    "更新",
    "落地",
    "直接处理",
    "提交",
    "优化",
    "重构",
)

READ_ONLY_OVERRIDE_TOKENS = (
    "do not modify",
    "don't modify",
    "no changes",
    "read-only",
    "readonly",
    "只读",
    "不要修改",
    "不要改",
    "先别改",
    "不用改",
    "只排查",
    "只分析",
)

INTENT_TYPES = ("query", "diagnosis", "review", "bugfix", "fix", "feature", "refactor", "test", "commit", "task")
MUTATION_AUTHORIZATIONS = ("read-only", "fix-authorized", "ambiguous")
MISSION_TYPES = (
    "diagnose",
    "fix",
    "implement",
    "refactor",
    "review",
    "explain",
    "test",
    "document",
    "release",
    "agent_os_evolution",
)
MISSION_MODES = ("readonly", "plan_first", "execute_allowed", "approval_required")
MISSION_AMBIGUITIES = ("low", "medium", "high")
MISSION_IR_VERSION = "mission-ir/v1"
INTENT_PHASES = (
    "parsed",
    "explaining",
    "planning",
    "awaiting-approval",
    "approved",
    "executing",
    "verifying",
    "completed",
    "blocked",
)
ACTION_TYPES = ("read", "write", "patch", "delete", "commit", "deploy", "memory", "docs", "verify", "shell", "git", "api", "browser")
DRIFT_TYPES = ("mutation", "scope", "tool", "risk", "evidence", "plan", "confidence", "role")

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "file.read": {"actions": {"read"}, "description": "Read files or inspect local content."},
    "file.write": {"actions": {"write"}, "description": "Create or update files."},
    "patch.apply": {"actions": {"patch", "write"}, "description": "Apply source or document patches."},
    "shell.safe": {"actions": {"read", "verify", "shell"}, "description": "Run allowlisted diagnostic or verification shell commands."},
    "shell.unsafe": {"actions": {"shell", "write"}, "description": "Run non-allowlisted shell commands."},
    "git.read": {"actions": {"read", "git"}, "description": "Inspect git status, branch, log, or diff."},
    "git.write": {"actions": {"git", "commit", "write"}, "description": "Mutate git state, commit, reset, clean, merge, or push."},
    "api.read": {"actions": {"read", "api"}, "description": "Call read-only API or HTTP checks."},
    "api.write": {"actions": {"api", "write"}, "description": "Call mutating API requests."},
    "browser.read": {"actions": {"read", "browser"}, "description": "Open, inspect, screenshot, or check browser state."},
    "browser.write": {"actions": {"browser", "write"}, "description": "Click, type, or otherwise mutate browser state."},
    "memory.write": {"actions": {"memory", "write"}, "description": "Write project memory or structured memory records."},
    "docs.write": {"actions": {"docs", "write"}, "description": "Create or update project documentation."},
    "deploy": {"actions": {"deploy", "write"}, "description": "Deploy, publish, release, or alter production runtime."},
}

READ_ONLY_BLOCKED_ACTIONS = {"write", "patch", "delete", "commit", "deploy", "memory", "docs"}

MISSION_TO_INTENT = {
    "diagnose": "diagnosis",
    "fix": "fix",
    "implement": "feature",
    "refactor": "refactor",
    "review": "review",
    "explain": "query",
    "test": "test",
    "document": "task",
    "release": "task",
    "agent_os_evolution": "task",
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


def parse_runtime_links(values: Optional[List[str]]) -> List[Tuple[str, str]]:
    links: List[Tuple[str, str]] = []
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


def split_terms(values: Optional[List[str]], fallback: Optional[str] = None) -> List[str]:
    raw = " ".join(values or [])
    if fallback:
        raw = f"{raw} {fallback}"
    terms = re.findall(r"[\w\u4e00-\u9fff]+", raw.lower(), flags=re.UNICODE)
    return list(dict.fromkeys(term for term in terms if len(term) >= 2))


def compact_list(values: List[str], limit: int = 8) -> str:
    if not values:
        return "none"
    shown = values[:limit]
    suffix = f" (+{len(values) - limit} more)" if len(values) > limit else ""
    return "; ".join(shown) + suffix


def load_json_file(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_project_slug(project: Optional[str] = None) -> Tuple[str, str]:
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


def detect_stack(files: Optional[List[str]] = None) -> tuple[str, str, str]:
    base = agent_workspace_root()
    candidates = [Path(value) for value in files or []]
    suffixes = {path.suffix.lower() for path in candidates}
    package = load_json_file(base / "package.json")
    deps = " ".join((package.get("dependencies") or {}).keys())
    dev_deps = " ".join((package.get("devDependencies") or {}).keys())
    dep_text = f"{deps} {dev_deps}".lower()
    signals: List[str] = []
    stacks: List[str] = []

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


def detect_task_layers(request: str, files: Optional[List[str]] = None) -> List[str]:
    haystack = request.lower()
    file_values = files or []
    suffixes = {Path(value).suffix.lower() for value in file_values}
    paths = " ".join(value.lower().replace("\\", "/") for value in file_values)
    layers: List[str] = []

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
    if any(token in lower for token in READ_ONLY_INTENT_TOKENS):
        return "diagnosis"
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


def detect_mutation_authorization(request: str) -> str:
    lower = request.lower()
    if any(token in lower for token in READ_ONLY_OVERRIDE_TOKENS):
        return "read-only"

    has_read_only = any(token in lower for token in READ_ONLY_INTENT_TOKENS)
    has_mutation = any(token in lower for token in MUTATION_INTENT_TOKENS)

    if has_read_only and has_mutation:
        return "ambiguous"
    if has_read_only:
        return "read-only"
    if has_mutation:
        return "fix-authorized"
    return "ambiguous"


def mission_type_from_intent(intent: str) -> str:
    return {
        "diagnosis": "diagnose",
        "bugfix": "fix",
        "fix": "fix",
        "feature": "implement",
        "refactor": "refactor",
        "review": "review",
        "test": "test",
        "commit": "release",
        "query": "explain",
    }.get(intent, "explain")


def mission_mode_for(intent: str, mutation_authorization: str, scale: str) -> str:
    if mutation_authorization == "read-only" or intent in {"diagnosis", "review", "query"}:
        return "readonly"
    if mutation_authorization == "ambiguous":
        return "approval_required"
    if scale in {"L2", "L3", "L4"}:
        return "plan_first"
    return "execute_allowed"


def mission_constraints_for(mutation_authorization: str) -> Dict[str, bool]:
    readonly = mutation_authorization != "fix-authorized"
    return {
        "readonly": readonly,
        "allowWrite": not readonly,
        "allowCommit": mutation_authorization == "fix-authorized",
        "allowDeploy": False,
        "requireApprovalBeforeMutation": readonly,
    }


def builtin_mission_ir(context: Dict[str, Any]) -> Dict[str, Any]:
    intent = context["intent"]
    mutation_authorization = context["mutation_authorization"]
    mode = mission_mode_for(intent, mutation_authorization, context["scale"])
    evidence_required = intent in {"diagnosis", "bugfix", "review"} or mutation_authorization != "fix-authorized"
    deliverables = ["conclusion"]
    if intent in {"diagnosis", "bugfix"}:
        deliverables = ["root_cause", "evidence", "conclusion", "repair_plan"]
    elif intent == "review":
        deliverables = ["evidence", "conclusion", "recommendation"]
    elif mutation_authorization == "fix-authorized":
        deliverables = ["implementation", "verification"]
    return {
        "specVersion": MISSION_IR_VERSION,
        "source": {"compiler": "builtin-rules", "fallback": False},
        "mission": {"type": mission_type_from_intent(intent), "mode": mode},
        "intent": {
            "primary": intent,
            "confidence": 0.9 if mutation_authorization == "read-only" else 0.72,
            "ambiguity": "medium" if mutation_authorization == "ambiguous" else "low",
        },
        "constraints": mission_constraints_for(mutation_authorization),
        "scope": {
            "targetProject": context["project"],
            "suspectedFiles": context["files"],
            "affectedLayers": context["task_layers"],
        },
        "deliverables": deliverables,
        "evidenceRequirements": {
            "required": evidence_required,
            "types": ["code_location", "logs", "reproduction"] if evidence_required else [],
            "minimumBeforeAction": 2 if evidence_required else 0,
        },
        "successCriteria": (
            ["identify_root_cause", "provide_evidence", "propose_repair_plan"]
            if intent in {"diagnosis", "bugfix"}
            else ["satisfy_user_request", "provide_verification"]
        ),
        "clarification": [],
        "feedbackPolicy": {
            "detectDrift": True,
            "recompileOnNewEvidence": True,
            "stopOnIntentMismatch": True,
        },
    }


def mission_compiler_prompt(request: str) -> Tuple[str, str]:
    system = (
        "You are Agent OS Semantic Compiler.\n"
        "Compile a user's natural language request into Mission IR.\n"
        "Do not execute tasks, inspect files, edit files, commit, deploy, or provide implementation advice.\n"
        "Return strict JSON only. No markdown. No extra text.\n\n"
        "Safety rules:\n"
        "- Diagnosis, investigation, analysis, inspection, review, explanation, troubleshooting, "
        "\"排查\", \"分析\", \"看看为什么\", \"定位原因\" are readonly by default.\n"
        "- Mutation is allowed only when the user explicitly asks to fix, modify, implement, add, "
        "delete, update, refactor, commit, deploy, install, or generate files.\n"
        "- If uncertain, preserve safety: readonly=true, allowWrite=false, "
        "requireApprovalBeforeMutation=true, ambiguity=\"high\"."
    )
    user = (
        "Compile this USER_REQUEST into Mission IR JSON.\n\n"
        "Required JSON shape:\n"
        "{\n"
        "  \"specVersion\": \"mission-ir/v1\",\n"
        "  \"mission\": {\n"
        "    \"type\": \"diagnose|fix|implement|refactor|review|explain|test|document|release|agent_os_evolution\",\n"
        "    \"mode\": \"readonly|plan_first|execute_allowed|approval_required\"\n"
        "  },\n"
        "  \"intent\": {\n"
        "    \"primary\": \"string\",\n"
        "    \"confidence\": 0.0,\n"
        "    \"ambiguity\": \"low|medium|high\"\n"
        "  },\n"
        "  \"constraints\": {\n"
        "    \"readonly\": true,\n"
        "    \"allowWrite\": false,\n"
        "    \"allowCommit\": false,\n"
        "    \"allowDeploy\": false,\n"
        "    \"requireApprovalBeforeMutation\": true\n"
        "  },\n"
        "  \"deliverables\": [\"root_cause\", \"evidence\", \"conclusion\", \"repair_plan\"],\n"
        "  \"evidenceRequirements\": {\n"
        "    \"required\": true,\n"
        "    \"types\": [\"code_location\", \"logs\", \"reproduction\"],\n"
        "    \"minimumBeforeAction\": 2\n"
        "  },\n"
        "  \"successCriteria\": [\"identify_root_cause\", \"provide_evidence\", \"propose_repair_plan\"],\n"
        "  \"clarification\": []\n"
        "}\n\n"
        f"USER_REQUEST:\n{request}\n"
    )
    return system, user


def strip_json_fence(text: str) -> str:
    value = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", value, flags=re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = value.find("{")
    end = value.rfind("}")
    if start >= 0 and end > start:
        return value[start : end + 1].strip()
    return value


def parse_mission_ir_text(text: str) -> Dict[str, Any]:
    cleaned = strip_json_fence(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mission compiler returned invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Mission compiler output must be a JSON object")
    return data


def normalize_deliverables(values: Any, mission_type: str) -> List[str]:
    allowed = {
        "root_cause",
        "evidence",
        "conclusion",
        "repair_plan",
        "implementation",
        "tests",
        "review",
        "documentation",
        "verification",
        "recommendation",
    }
    aliases = {
        "reason": "root_cause",
        "repair": "repair_plan",
        "fix_plan": "repair_plan",
        "reproduction_steps": "evidence",
        "state_inspection": "evidence",
    }
    raw = values if isinstance(values, list) else []
    normalized: List[str] = []
    for item in raw:
        key = aliases.get(str(item), str(item))
        if key in allowed and key not in normalized:
            normalized.append(key)
    if not normalized:
        normalized = ["conclusion"]
    if mission_type == "diagnose":
        for required in ("root_cause", "evidence", "conclusion", "repair_plan"):
            if required not in normalized:
                normalized.append(required)
    return normalized


def normalize_evidence_requirements(value: Any, readonly: bool) -> Dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    types = source.get("types") if isinstance(source.get("types"), list) else []
    allowed = {"code_location", "logs", "reproduction", "test_result", "api_trace", "git_diff", "screenshot"}
    aliases = {
        "state_inspection": "code_location",
        "timing_analysis": "logs",
        "code_evidence": "code_location",
    }
    normalized_types: List[str] = []
    for item in types:
        key = aliases.get(str(item), str(item))
        if key in allowed and key not in normalized_types:
            normalized_types.append(key)
    if readonly and not normalized_types:
        normalized_types = ["code_location", "logs", "reproduction"]
    minimum = source.get("minimumBeforeAction", 2 if readonly else 0)
    try:
        minimum_int = max(0, int(minimum))
    except (TypeError, ValueError):
        minimum_int = 2 if readonly else 0
    return {
        "required": bool(source.get("required", readonly)),
        "types": normalized_types,
        "minimumBeforeAction": minimum_int,
    }


def normalize_mission_ir(raw: Dict[str, Any], context: Dict[str, Any], *, compiler: str, fallback: bool) -> Dict[str, Any]:
    mission = raw.get("mission") if isinstance(raw.get("mission"), dict) else {}
    mission_type = str(mission.get("type") or mission_type_from_intent(context["intent"]))
    if mission_type not in MISSION_TYPES:
        mission_type = mission_type_from_intent(context["intent"])
    mode = str(mission.get("mode") or mission_mode_for(context["intent"], context["mutation_authorization"], context["scale"]))
    if mode not in MISSION_MODES:
        mode = "approval_required"

    constraints = raw.get("constraints") if isinstance(raw.get("constraints"), dict) else {}
    readonly = bool(constraints.get("readonly", mode == "readonly"))
    allow_write = bool(constraints.get("allowWrite", not readonly))
    allow_commit = bool(constraints.get("allowCommit", False))
    allow_deploy = bool(constraints.get("allowDeploy", False))
    require_approval = bool(constraints.get("requireApprovalBeforeMutation", readonly or mode == "approval_required"))

    local_authorization = context["mutation_authorization"]
    if local_authorization == "read-only":
        readonly = True
        allow_write = False
        allow_commit = False
        allow_deploy = False
        require_approval = True
        mode = "readonly"
        if mission_type not in {"diagnose", "review", "explain"}:
            mission_type = "diagnose"
    elif local_authorization == "ambiguous" and allow_write:
        mode = "approval_required"
        allow_write = False
        allow_commit = False
        allow_deploy = False
        require_approval = True

    intent = raw.get("intent") if isinstance(raw.get("intent"), dict) else {}
    try:
        confidence = float(intent.get("confidence", 0.65))
    except (TypeError, ValueError):
        confidence = 0.65
    confidence = min(1.0, max(0.0, confidence))
    ambiguity = str(intent.get("ambiguity") or ("medium" if local_authorization == "ambiguous" else "low"))
    if ambiguity not in MISSION_AMBIGUITIES:
        ambiguity = "medium"

    normalized = {
        "specVersion": MISSION_IR_VERSION,
        "source": {
            "compiler": compiler,
            "fallback": fallback,
        },
        "mission": {"type": mission_type, "mode": mode},
        "intent": {
            "primary": str(intent.get("primary") or context["intent"]),
            "confidence": confidence,
            "ambiguity": ambiguity,
        },
        "constraints": {
            "readonly": readonly,
            "allowWrite": allow_write,
            "allowCommit": allow_commit,
            "allowDeploy": allow_deploy,
            "requireApprovalBeforeMutation": require_approval,
        },
        "scope": {
            "targetProject": context["project"],
            "suspectedFiles": context["files"],
            "affectedLayers": context["task_layers"],
        },
        "deliverables": normalize_deliverables(raw.get("deliverables"), mission_type),
        "evidenceRequirements": normalize_evidence_requirements(raw.get("evidenceRequirements"), readonly),
        "successCriteria": raw.get("successCriteria") if isinstance(raw.get("successCriteria"), list) else [],
        "clarification": raw.get("clarification") if isinstance(raw.get("clarification"), list) else [],
        "feedbackPolicy": {
            "detectDrift": True,
            "recompileOnNewEvidence": True,
            "stopOnIntentMismatch": True,
        },
    }
    if not normalized["successCriteria"]:
        normalized["successCriteria"] = (
            ["identify_root_cause", "provide_evidence", "propose_repair_plan"]
            if mission_type == "diagnose"
            else ["satisfy_user_request", "provide_verification"]
        )
    return normalized


def mission_to_runtime_intent(mission_ir: Dict[str, Any], context: Dict[str, Any]) -> Tuple[str, str, float]:
    mission_type = mission_ir["mission"]["type"]
    constraints = mission_ir["constraints"]
    intent_type = MISSION_TO_INTENT.get(mission_type, context["intent"])
    if constraints["readonly"]:
        mutation_authorization = "read-only"
    elif mission_ir["mission"]["mode"] == "approval_required":
        mutation_authorization = "ambiguous"
    else:
        mutation_authorization = "fix-authorized"
    confidence = float(mission_ir["intent"].get("confidence", 0.65))
    return intent_type, mutation_authorization, confidence


def visible_intent_for(
    mission_ir: Dict[str, Any],
    compiler_metadata: Dict[str, Any],
    runtime_mapping: Dict[str, Any],
) -> Dict[str, Any]:
    source = mission_ir.get("source", {})
    compiler = str(compiler_metadata.get("compiler") or source.get("compiler") or "builtin-rules")
    provider = compiler_metadata.get("provider")
    model = compiler_metadata.get("model")
    fallback = bool(compiler_metadata.get("fallback", source.get("fallback", False)))
    compiler_mode = "llm" if compiler.startswith("llm:") or compiler == "provided-llm-output" else "builtin-rules"
    constraints = mission_ir.get("constraints", {})
    mission = mission_ir.get("mission", {})
    permission_label = "只读" if constraints.get("readonly") or not constraints.get("allowWrite") else "允许写入"
    if constraints.get("allowCommit"):
        permission_label += "，允许提交"
    if constraints.get("allowDeploy"):
        permission_label += "，允许部署"
    if constraints.get("requireApprovalBeforeMutation"):
        permission_label += "，写入前需确认"

    if compiler_mode == "llm":
        compiler_label = f"LLM Semantic Compiler（{provider or compiler.replace('llm:', '')}"
        if model:
            compiler_label += f" / {model}"
        compiler_label += "）"
    else:
        compiler_label = "本地规则算法"
    fallback_label = "已回退" if fallback else "未回退"
    summary = (
        f"Agent OS：意图编译已生效，编译器={compiler_label}，{fallback_label}；"
        f"任务={mission.get('type', 'unknown')}，模式={mission.get('mode', 'unknown')}，权限={permission_label}。"
    )
    return {
        "format": "intent-summary/v1",
        "title": "Agent OS：意图编译已生效",
        "summary": summary,
        "conversation_hint": summary,
        "compiler": {
            "mode": compiler_mode,
            "compiler": compiler,
            "provider": provider,
            "model": model,
            "fallback": fallback,
        },
        "mission": {
            "type": mission.get("type"),
            "mode": mission.get("mode"),
            "intent_type": runtime_mapping.get("intent_type"),
            "mutation_authorization": runtime_mapping.get("mutation_authorization"),
            "confidence": runtime_mapping.get("confidence"),
        },
        "permissions": {
            "readonly": bool(constraints.get("readonly")),
            "allow_write": bool(constraints.get("allowWrite")),
            "allow_commit": bool(constraints.get("allowCommit")),
            "allow_deploy": bool(constraints.get("allowDeploy")),
            "require_approval_before_mutation": bool(constraints.get("requireApprovalBeforeMutation")),
            "label": permission_label,
        },
    }


def visible_plan_for_tasks(
    tasks: List[Dict[str, Any]],
    context: Dict[str, Any],
    *,
    capability_status: Optional[str] = None,
    title: str = "Agent OS：执行计划",
) -> Dict[str, Any]:
    items = []
    markdown_lines = [title]
    for index, task in enumerate(tasks, start=1):
        status = str(task.get("status") or "pending")
        checked = "x" if status == "completed" else " "
        item_title = str(task.get("title") or f"Task {index}")
        layer = str(task.get("task_layer") or "")
        role = str(task.get("assigned_role") or "")
        suffix_parts = [part for part in (layer, role) if part]
        suffix = f"（{' / '.join(suffix_parts)}）" if suffix_parts else ""
        markdown_lines.append(f"- [{checked}] {item_title}{suffix}")
        items.append(
            {
                "order": index,
                "status": status,
                "title": item_title,
                "task_layer": layer,
                "assigned_role": role,
                "plan": task.get("plan", ""),
            }
        )
    validation = "按 Validation Gate 执行并记录结果。"
    if any(task.get("task_layer") == "Test" for task in tasks):
        validation = "执行计划内验证任务，并在完成前说明验证结果与剩余风险。"
    markdown_lines.append(f"\n验证：{validation}")
    if capability_status:
        markdown_lines.append(f"能力链路状态：{capability_status}")
    return {
        "format": "markdown-checklist/v1",
        "title": title,
        "scale": context.get("scale"),
        "task_layers": context.get("task_layers", []),
        "capability_status": capability_status,
        "items": items,
        "markdown": "\n".join(markdown_lines),
        "host_adapters": {
            "codex": "Use update_plan when available; otherwise show markdown.",
            "claude": "Use TodoWrite when available; otherwise show markdown.",
            "cursor_qwen_qoder": "Show markdown checklist and write runtime/output logs when available.",
            "vscode_plugin": "Render in Output and dashboard/panel when available.",
        },
    }


def compile_mission_builtin(context: Dict[str, Any], *, fallback: bool = False, reason: Optional[str] = None) -> Dict[str, Any]:
    raw = builtin_mission_ir(context)
    raw.setdefault("source", {})["fallbackReason"] = reason
    return normalize_mission_ir(raw, context, compiler="builtin-rules", fallback=fallback)


def call_llm_mission_compiler(
    *,
    request: str,
    provider: str,
    base_url: str,
    api_key: str,
    model: str,
    timeout: int = 60,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    system, user = mission_compiler_prompt(request)
    endpoint = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    started = time.time()
    request_data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=request_data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    duration_ms = int((time.time() - started) * 1000)
    content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise ValueError("Mission compiler returned an empty response")
    metadata = {
        "provider": provider,
        "model": model,
        "duration_ms": duration_ms,
        "raw_response": content,
    }
    return parse_mission_ir_text(content), metadata


def compile_mission_ir(
    context: Dict[str, Any],
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    llm_response: Optional[str] = None,
    timeout: int = 60,
    no_fallback: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if llm_response:
        raw = parse_mission_ir_text(llm_response)
        mission_ir = normalize_mission_ir(raw, context, compiler="provided-llm-output", fallback=False)
        return mission_ir, {"compiler": "provided-llm-output", "fallback": False}

    if provider and provider != "builtin":
        try:
            if not base_url or not api_key or not model:
                raise ValueError("provider mode requires --base-url, --api-key or AGENT_OS_LLM_API_KEY, and --model")
            raw, metadata = call_llm_mission_compiler(
                request=context["request"],
                provider=provider,
                base_url=base_url,
                api_key=api_key,
                model=model,
                timeout=timeout,
            )
            mission_ir = normalize_mission_ir(raw, context, compiler=f"llm:{provider}", fallback=False)
            return mission_ir, {"compiler": f"llm:{provider}", "fallback": False, **metadata}
        except Exception as exc:
            if no_fallback:
                raise
            mission_ir = compile_mission_builtin(context, fallback=True, reason=str(exc))
            mission_ir["source"]["fallbackReason"] = str(exc)
            return mission_ir, {"compiler": f"llm:{provider}", "fallback": True, "error": str(exc)}

    mission_ir = compile_mission_builtin(context)
    return mission_ir, {"compiler": "builtin-rules", "fallback": False}


def actions_for_intent(intent_type: str, mutation_authorization: str) -> tuple[list[str], list[str]]:
    if mutation_authorization == "fix-authorized":
        return sorted({action for meta in TOOL_REGISTRY.values() for action in meta["actions"]}), []
    if mutation_authorization == "read-only" or intent_type in {"query", "diagnosis", "review"}:
        allowed = ["read", "verify", "shell", "git", "api", "browser"]
        blocked = sorted(READ_ONLY_BLOCKED_ACTIONS)
        return allowed, blocked
    if intent_type == "commit":
        return ["read", "git", "commit"], ["deploy", "memory", "docs"]
    return sorted({action for meta in TOOL_REGISTRY.values() for action in meta["actions"]}), []


def tool_key_for_action(
    *,
    action_type: str,
    tool: Optional[str],
    command: Optional[str] = None,
    method: Optional[str] = None,
    browser_action: Optional[str] = None,
    allow_unsafe: bool = False,
) -> str:
    if tool and tool in TOOL_REGISTRY:
        return tool
    if action_type in {"write", "patch", "delete"}:
        return "patch.apply" if action_type == "patch" else "file.write"
    if action_type == "memory":
        return "memory.write"
    if action_type == "docs":
        return "docs.write"
    if action_type == "deploy":
        return "deploy"
    if action_type == "commit":
        return "git.write"
    if action_type == "git":
        normalized = (command or "").lower()
        if any(token in normalized for token in (" commit", " reset", " clean", " merge", " push", " checkout ")):
            return "git.write"
        return "git.read"
    if action_type == "api":
        method_upper = (method or "GET").upper()
        return "api.read" if method_upper in {"GET", "HEAD", "OPTIONS"} else "api.write"
    if action_type == "browser":
        return "browser.read" if (browser_action or "check-text") in {"open", "check-text", "screenshot"} else "browser.write"
    if action_type == "shell":
        return "shell.unsafe" if allow_unsafe or not command_is_allowed(command or "") else "shell.safe"
    return "file.read"


def scope_matches(target_paths: Optional[str], approved_scope: Optional[str]) -> tuple[bool, str]:
    targets = [item.strip().replace("\\", "/") for item in (target_paths or "").split(",") if item.strip()]
    scopes = [item.strip().replace("\\", "/") for item in (approved_scope or "").split(",") if item.strip()]
    if not targets or not scopes:
        return True, "no-target-or-scope"
    for target in targets:
        if not any(fnmatch.fnmatch(target, scope) or target.startswith(scope.rstrip("/") + "/") for scope in scopes):
            return False, f"{target} outside approved scope"
    return True, "within-approved-scope"


def evaluate_action_gate(
    *,
    intent_type: str,
    mutation_authorization: str,
    action_type: str,
    tool: str,
    target_paths: Optional[str] = None,
    approved_scope: Optional[str] = None,
    confidence: float = 0.5,
    risk_level: str = "normal",
    user_approved: bool = False,
    validation_plan: Optional[str] = None,
) -> Dict[str, Any]:
    allowed_actions, blocked_actions = actions_for_intent(intent_type, mutation_authorization)
    tool_meta = TOOL_REGISTRY.get(tool, {"actions": {action_type}, "description": "custom tool"})
    tool_actions = set(tool_meta["actions"])
    action_set = {action_type, *tool_actions}
    blocked_hits = sorted(action_set.intersection(blocked_actions))
    scope_ok, scope_reason = scope_matches(target_paths, approved_scope)

    missing: list[str] = []
    if blocked_hits:
        missing.append(f"blocked-actions:{','.join(blocked_hits)}")
    if not scope_ok:
        missing.append(f"scope:{scope_reason}")
    if action_set.intersection(READ_ONLY_BLOCKED_ACTIONS) and mutation_authorization != "fix-authorized" and not user_approved:
        missing.append("mutation-authorization")
    if risk_level in {"high", "critical"} and not user_approved:
        missing.append("high-risk-approval")
    if action_set.intersection({"write", "patch", "delete", "commit", "deploy", "memory", "docs"}) and confidence < 0.7 and not user_approved:
        missing.append("confidence-threshold")
    if action_set.intersection({"write", "patch", "delete", "commit", "deploy"}) and not validation_plan:
        missing.append("validation-plan")

    if blocked_hits:
        decision = "blocked"
    elif missing:
        decision = "requires-approval"
    else:
        decision = "allowed"

    return {
        "decision": decision,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "tool_actions": sorted(tool_actions),
        "missing_requirements": missing,
        "reason": "allowed" if decision == "allowed" else "; ".join(missing),
        "scope": {"ok": scope_ok, "reason": scope_reason},
        "requires_approval": decision == "requires-approval",
    }


def detect_scale(request: str, layers: List[str], files: Optional[List[str]] = None) -> str:
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


def workspace_risk_signals(files: Optional[List[str]] = None) -> List[str]:
    signals: List[str] = []
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


def docs_path_bucket(path: str) -> Optional[str]:
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


def docs_impact_for_files(files: Optional[List[str]]) -> Dict[str, Any]:
    impacted = {"plans": False, "tasks": False, "decisions": False, "reviews": False, "verification": False}
    reasons: List[str] = []
    for value in files or []:
        bucket = docs_path_bucket(value)
        if bucket and bucket in impacted:
            impacted[bucket] = True
            reasons.append(f"changed {bucket} docs file: {value}")
    return {"impacted": impacted, "reasons": list(dict.fromkeys(reasons))}


def docs_freshness_for_request(request: str, files: Optional[List[str]], workspace: Dict[str, Any]) -> Dict[str, Any]:
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
    layer_hits: dict[str, List[str]],
    linkage: Dict[str, Any],
    memory_hits: List[str],
    docs_freshness: Dict[str, Any],
    workspace: Dict[str, Any],
) -> Dict[str, Any]:
    code_present = any(layer_hits[layer] for layer in ("frontend", "api", "backend", "data", "verification"))
    memory_present = bool(memory_hits)
    docs_present = workspace["docs"]["exists"]
    docs_mention = bool(docs_freshness["impact"]["reasons"])
    conflict_sources: List[str] = []
    reasons: List[str] = []
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
    memory_hits: List[str],
    docs_freshness: Dict[str, Any],
    workspace: Dict[str, Any],
    code_evidence: List[str],
    runtime_evidence: List[str],
) -> Dict[str, Any]:
    memory_present = bool(memory_hits)
    docs_present = workspace["docs"]["exists"]
    code_present = bool(code_evidence)
    runtime_present = bool(runtime_evidence)
    conflict_sources: List[str] = []
    reasons: List[str] = []
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


def workspace_snapshot(project: Optional[str] = None) -> Dict[str, Any]:
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


def context_for_request(project: Optional[str], request: str, files: Optional[List[str]]) -> Dict[str, Any]:
    project_slug, project_evidence = detect_project_slug(project)
    stack, stack_confidence, stack_evidence = detect_stack(files)
    layers = detect_task_layers(request, files)
    scale = detect_scale(request, layers, files)
    intent = detect_intent(request)
    mutation_authorization = detect_mutation_authorization(request)
    evidence = (
        f"project={project_evidence}; stack={stack_evidence}; "
        f"layers={','.join(layers)}; risk_signals={','.join(workspace_risk_signals(files))}; "
        f"mutation_authorization={mutation_authorization}; files={','.join(files or []) or 'none'}"
    )
    return {
        "project": project_slug,
        "request": request,
        "stack": stack,
        "stack_confidence": stack_confidence,
        "task_layers": layers,
        "scale": scale,
        "intent": intent,
        "mutation_authorization": mutation_authorization,
        "files": files or [],
        "evidence": evidence,
    }


def record_runtime_context(conn, context: Dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO runtime_contexts(
            project, request, stack, stack_confidence, task_layers,
            scale, intent, mutation_authorization, files, evidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            context["project"],
            context["request"],
            context["stack"],
            context["stack_confidence"],
            normalize_csv(context["task_layers"]),
            context["scale"],
            context["intent"],
            context["mutation_authorization"],
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
    run_id: Optional[str] = None,
    goal_id: Optional[str] = None,
    task_id: Optional[str] = None,
    source: str = "runtime",
    payload: Optional[Dict[str, Any]] = None,
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


def intent_state_from_context(context: Dict[str, Any], *, goal_id: Optional[str] = None, run_id: Optional[str] = None, intent_id: Optional[str] = None) -> Dict[str, Any]:
    mission_ir = context.get("mission_ir")
    if mission_ir:
        intent_type, mutation_authorization, mission_confidence = mission_to_runtime_intent(mission_ir, context)
    else:
        intent_type = context["intent"]
        mutation_authorization = context["mutation_authorization"]
        mission_confidence = None
    allowed_actions, blocked_actions = actions_for_intent(intent_type, mutation_authorization)
    explanation_required = int(intent_type in {"diagnosis", "bugfix"} or context["scale"] in {"L3", "L4"})
    risk_level = "high" if context["scale"] in {"L3", "L4"} else "normal"
    confidence = mission_confidence if mission_confidence is not None else (0.65 if mutation_authorization == "read-only" else 0.55)
    phase = "explaining" if explanation_required else "parsed"
    return {
        "id": intent_id or f"intent-{uuid.uuid4().hex[:8]}",
        "project": context["project"],
        "goal_id": goal_id,
        "run_id": run_id,
        "original_request": context["request"],
        "intent_type": intent_type,
        "mutation_authorization": mutation_authorization,
        "approved_scope": normalize_csv(context["files"]),
        "current_phase": phase,
        "confidence": confidence,
        "risk_level": risk_level,
        "allowed_actions": normalize_csv(allowed_actions),
        "blocked_actions": normalize_csv(blocked_actions),
        "explanation_required": explanation_required,
        "evidence": context["evidence"],
        "mission_ir_json": json.dumps(mission_ir, ensure_ascii=False, sort_keys=True) if mission_ir else None,
        "compiler_metadata_json": json.dumps(context.get("compiler_metadata") or {}, ensure_ascii=False, sort_keys=True)
        if mission_ir
        else None,
    }


def active_intent_pointer_path(conn) -> Optional[Path]:
    """定位与当前 SQLite 库同目录的活动意图指针文件 active-intent.json。"""
    try:
        for row in conn.execute("PRAGMA database_list").fetchall():
            name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
            file = row["file"] if isinstance(row, sqlite3.Row) else row[2]
            if name == "main" and file:
                return Path(file).resolve().parent / "active-intent.json"
    except sqlite3.Error:
        return None
    return None


def write_active_intent_pointer(conn, state: Dict[str, Any]) -> None:
    """把最近锁定/更新的意图写成指针,供 PreToolUse / pre-commit 钩子读取。

    这是执行门控"控制反转"的落点:钩子(PEP)无需理解项目 slug、也无需
    重新编译,只要读取该指针拿到 project 与 intent_id,即可对照 Locked
    Mission IR 调用 execution-gate 做硬门校验。指针是尽力而为,写失败不影响
    运行时主流程(git pre-commit 仍是与宿主无关的最后防线)。
    """
    pointer = active_intent_pointer_path(conn)
    if pointer is None:
        return
    payload = {
        "project": state["project"],
        "intent_id": state["id"],
        "intent_type": state["intent_type"],
        "mutation_authorization": state["mutation_authorization"],
        "risk_level": state.get("risk_level"),
        "approved_scope": state.get("approved_scope"),
    }
    try:
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        pass


def upsert_intent_state(conn, state: Dict[str, Any]) -> str:
    conn.execute(
        """
        INSERT INTO intent_states(
            id, project, goal_id, run_id, original_request, intent_type,
            mutation_authorization, approved_scope, current_phase, confidence,
            risk_level, allowed_actions, blocked_actions, explanation_required, evidence,
            mission_ir_json, compiler_metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            project = excluded.project,
            goal_id = excluded.goal_id,
            run_id = excluded.run_id,
            original_request = excluded.original_request,
            intent_type = excluded.intent_type,
            mutation_authorization = excluded.mutation_authorization,
            approved_scope = excluded.approved_scope,
            current_phase = excluded.current_phase,
            confidence = excluded.confidence,
            risk_level = excluded.risk_level,
            allowed_actions = excluded.allowed_actions,
            blocked_actions = excluded.blocked_actions,
            explanation_required = excluded.explanation_required,
            evidence = excluded.evidence,
            mission_ir_json = excluded.mission_ir_json,
            compiler_metadata_json = excluded.compiler_metadata_json,
            updated_at = datetime('now')
        """,
        (
            state["id"],
            state["project"],
            state.get("goal_id"),
            state.get("run_id"),
            state["original_request"],
            state["intent_type"],
            state["mutation_authorization"],
            state.get("approved_scope"),
            state["current_phase"],
            state["confidence"],
            state["risk_level"],
            state.get("allowed_actions"),
            state.get("blocked_actions"),
            int(state.get("explanation_required", 0)),
            state.get("evidence"),
            state.get("mission_ir_json"),
            state.get("compiler_metadata_json"),
        ),
    )
    # 同步刷新活动意图指针,让外层 PEP 钩子始终对照最新锁定的 Mission IR
    write_active_intent_pointer(conn, state)
    return state["id"]


def fetch_intent_state(conn, *, project: str, intent_id: Optional[str]) -> Optional[sqlite3.Row]:
    if intent_id:
        return conn.execute("SELECT * FROM intent_states WHERE project = ? AND id = ?", (project, intent_id)).fetchone()
    return conn.execute(
        """
        SELECT *
        FROM intent_states
        WHERE project = ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        (project,),
    ).fetchone()


def insert_action_proposal(
    conn,
    *,
    project: str,
    intent_id: Optional[str],
    goal_id: Optional[str],
    run_id: Optional[str],
    action_type: str,
    tool: str,
    target_paths: Optional[str],
    reason: str,
    risk_level: str,
    validation_plan: Optional[str],
    gate: Dict[str, Any],
    proposal_id: Optional[str] = None,
) -> str:
    proposal_id = proposal_id or f"action-{uuid.uuid4().hex[:8]}"
    status = gate["decision"]
    conn.execute(
        """
        INSERT INTO action_proposals(
            id, project, intent_id, goal_id, run_id, action_type, tool, target_paths,
            reason, risk_level, status, gate_decision, gate_reason, requires_approval,
            validation_plan
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            intent_id = excluded.intent_id,
            goal_id = excluded.goal_id,
            run_id = excluded.run_id,
            action_type = excluded.action_type,
            tool = excluded.tool,
            target_paths = excluded.target_paths,
            reason = excluded.reason,
            risk_level = excluded.risk_level,
            status = excluded.status,
            gate_decision = excluded.gate_decision,
            gate_reason = excluded.gate_reason,
            requires_approval = excluded.requires_approval,
            validation_plan = excluded.validation_plan,
            updated_at = datetime('now')
        """,
        (
            proposal_id,
            project,
            intent_id,
            goal_id,
            run_id,
            action_type,
            tool,
            target_paths,
            reason,
            risk_level,
            status,
            gate["decision"],
            gate["reason"],
            int(gate["requires_approval"]),
            validation_plan,
        ),
    )
    return proposal_id


def transition_state(
    conn,
    *,
    project: str,
    entity_type: str,
    entity_id: str,
    new_status: str,
    event_type: str,
    summary: str,
    goal_id: Optional[str] = None,
    task_id: Optional[str] = None,
    run_id: Optional[str] = None,
    extra_fields: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
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


def normalize_skill_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]
    normalized: List[str] = []
    for item in raw_values:
        for part in str(item).split(","):
            part = part.strip().strip("\"'")
            if part:
                normalized.append(part)
    return list(dict.fromkeys(normalized))


def skill_identifiers(manifest: Dict[str, Any]) -> set[str]:
    identifiers = {str(manifest.get("skill_name") or "").strip()}
    path = manifest.get("path")
    if path:
        identifiers.add(Path(str(path)).parent.name)
    return {item for item in identifiers if item}


def match_skill_trigger(
    manifest: Dict[str, Any],
    request: Optional[str],
    task_layers: List[str],
    stack: str,
) -> Dict[str, Any]:
    request_text = (request or "").lower()
    stack_text = (stack or "").lower()
    evidence: List[str] = []
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


def build_skill_dependency_graph(manifests: list[Dict[str, Any]]) -> dict[str, Dict[str, Any]]:
    graph: dict[str, Dict[str, Any]] = {}
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
    manifests: list[Dict[str, Any]],
    selected_skill_names: Optional[List[str]] = None,
) -> list[Dict[str, Any]]:
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

    conflicts: list[Dict[str, Any]] = []
    seen: set[Tuple[str, str]] = set()
    skill_name_counts: Dict[str, int] = {}
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
    task_layers: List[str],
    stack: str,
    request: Optional[str] = None,
    skills_dir: Optional[Path] = None,
) -> list[Dict[str, Any]]:
    available = load_skill_metadata(skills_dir)
    recommendations: list[Dict[str, str]] = []
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
    deduped: dict[str, Dict[str, Any]] = {}
    for item in recommendations:
        deduped.setdefault(item["skill_name"], item)
    return list(deduped.values())


def parse_skill_frontmatter(text: str) -> tuple[Dict[str, Any], bool]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, False
    data: Dict[str, Any] = {}
    current_key: Optional[str] = None
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


def extract_skill_section_headings(text: str) -> List[str]:
    headings: List[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if heading:
                headings.append(heading)
    return headings


def validate_skill_manifest(skill_file: Path) -> Dict[str, Any]:
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
    issues: List[str] = []
    warnings: List[str] = []
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


def load_skill_metadata(skills_dir: Optional[Path] = None) -> dict[str, Dict[str, Any]]:
    skills_dir = skills_dir or ROOT / "skills"
    metadata: dict[str, Dict[str, Any]] = {}
    if not skills_dir.exists():
        return metadata
    for skill_file in skills_dir.glob("*/SKILL.md"):
        manifest = validate_skill_manifest(skill_file)
        metadata[manifest["skill_name"]] = {"name": manifest["skill_name"], **manifest}
    return metadata


def validate_skill_runtime(skills_dir: Optional[Path] = None, skill_names: Optional[List[str]] = None) -> list[Dict[str, Any]]:
    skills_dir = skills_dir or ROOT / "skills"
    if not skills_dir.exists():
        return []
    requested = set(skill_names or [])
    manifests: list[Dict[str, Any]] = []
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


def plan_tasks_for(context: Dict[str, Any], capability_status: str) -> list[Dict[str, str]]:
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


def resolve_scan_roots(values: Optional[List[str]]) -> List[Path]:
    base = agent_workspace_root()
    roots = values or ["."]
    resolved: List[Path] = []
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


def capability_linkage(layer_hits: dict[str, List[str]], route_tokens: dict[str, set[str]]) -> Dict[str, Any]:
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
    layer_hits: dict[str, List[str]],
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


def confidence_for_capability(status: str, layer_hits: dict[str, List[str]], memory_hits: List[str]) -> float:
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
    context: Dict[str, Any],
    workspace: Dict[str, Any],
    memory_hits: Optional[List[str]] = None,
    verification_hits: Optional[List[str]] = None,
) -> list[Dict[str, Any]]:
    memory_hits = memory_hits or []
    verification_hits = verification_hits or []
    request_lower = request.lower()
    ranked: list[Dict[str, Any]] = []

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

    deduped: dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in ranked:
        deduped[(item["kind"], item["title"])] = item
    return sorted(deduped.values(), key=lambda item: item["score"], reverse=True)


def search_memory_for_capability(conn, project: str, query: str, limit: int = 5) -> List[str]:
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
    task_layers: List[str],
    signals: List[str],
) -> list[Dict[str, str]]:
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
    layer_hits: dict[str, List[str]] = {
        "frontend": [],
        "api": [],
        "backend": [],
        "data": [],
        "verification": [],
    }
    files_scanned = 0
    files_matched = 0
    max_hits_per_layer = args.max_hits
    memory_hits: List[str] = []
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


def verification_checks_for(task_layers: List[str], scale: str, changed_files: List[str]) -> list[Dict[str, str]]:
    layers = {layer.lower() for layer in task_layers}
    files = [Path(value) for value in changed_files]
    suffixes = {path.suffix.lower() for path in files}
    checks: list[Dict[str, str]] = []

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

    seen: set[Tuple[str, str]] = set()
    unique: list[Dict[str, str]] = []
    for check in checks:
        key = (check["scope"], check["command"])
        if key not in seen:
            seen.add(key)
            unique.append(check)
    return unique


def pipeline_stages_for(
    *,
    workspace: Dict[str, Any],
    decisions: list[Dict[str, Any]],
    verification_checks: list[Dict[str, Any]],
    docs_required: bool,
    memory_required: bool,
    open_tasks: int,
    recovery_required: bool,
    recoveries: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
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


def validation_profile_for(stack: str, task_layers: List[str], files: Optional[List[str]] = None) -> list[Dict[str, str]]:
    stack_lower = stack.lower()
    layers = {layer.lower() for layer in task_layers}
    checks: list[Dict[str, str]] = []
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


def verification_pipeline_for(stack: str, task_layers: List[str], scale: str, files: Optional[List[str]] = None) -> list[Dict[str, Any]]:
    layers = {layer.lower() for layer in task_layers}
    file_values = files or []
    suffixes = {Path(value).suffix.lower() for value in file_values}
    profile_checks = validation_profile_for(stack, task_layers, file_values)
    planned_checks = verification_checks_for(task_layers, scale, file_values)
    stages: list[Dict[str, Any]] = []

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

    deduped: dict[Tuple[str, str], Dict[str, Any]] = {}
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


def parse_required_resources(value: Optional[str]) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def open_resource_conflicts(
    conn: sqlite3.Connection,
    *,
    project: str,
    required_resources: list[str],
) -> list[Dict[str, Any]]:
    conflicts: list[Dict[str, Any]] = []
    for item in required_resources:
        if ":" in item:
            resource_type, resource_key = item.split(":", 1)
        else:
            resource_type, resource_key = "custom", item
        row = conn.execute(
            """
            SELECT *
            FROM resource_leases
            WHERE project = ?
              AND resource_type = ?
              AND resource_key = ?
              AND status = 'granted'
              AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
            ORDER BY granted_at DESC
            LIMIT 1
            """,
            (project, resource_type, resource_key),
        ).fetchone()
        if row:
            conflicts.append(row_to_dict(row))
    return conflicts


def cmd_runtime_schedule(args: argparse.Namespace) -> None:
    schedule_id = args.id or f"schedule-{uuid.uuid4().hex[:8]}"
    status = args.status or "queued"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conn.execute(
            """
            INSERT INTO runtime_schedule_items(
                id, project, run_id, goal_id, task_id, intent_id, action_type,
                assigned_role, status, priority, depends_on, required_resources,
                schedule_reason, next_action, available_at, blocker, evidence
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                run_id = excluded.run_id,
                goal_id = excluded.goal_id,
                task_id = excluded.task_id,
                intent_id = excluded.intent_id,
                action_type = excluded.action_type,
                assigned_role = excluded.assigned_role,
                status = excluded.status,
                priority = excluded.priority,
                depends_on = excluded.depends_on,
                required_resources = excluded.required_resources,
                schedule_reason = excluded.schedule_reason,
                next_action = excluded.next_action,
                available_at = excluded.available_at,
                blocker = excluded.blocker,
                evidence = excluded.evidence,
                updated_at = datetime('now')
            """,
            (
                schedule_id,
                args.project,
                args.run_id,
                args.goal_id,
                args.task_id,
                args.intent_id,
                args.action_type,
                args.assigned_role,
                status,
                args.priority,
                args.depends_on,
                args.required_resources,
                args.reason,
                args.next_action,
                args.available_at,
                args.blocker,
                args.evidence,
            ),
        )
        record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="KernelStep",
            source="runtime-schedule",
            summary=f"Scheduled {args.action_type} as {schedule_id}.",
            payload={
                "schedule_id": schedule_id,
                "status": status,
                "priority": args.priority,
                "required_resources": parse_required_resources(args.required_resources),
            },
        )
        conn.commit()
    print_json({"ok": True, "id": schedule_id, "project": args.project, "status": status})


def cmd_runtime_scheduler_next(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            """
            SELECT *
            FROM runtime_schedule_items
            WHERE project = ?
              AND (? IS NULL OR goal_id = ?)
              AND status IN ('queued', 'ready')
              AND datetime(available_at) <= datetime('now')
            ORDER BY priority DESC, created_at
            LIMIT ?
            """,
            (args.project, args.goal_id, args.goal_id, args.limit),
        ).fetchall()
        selected = None
        blockers: list[Dict[str, Any]] = []
        for row in rows:
            dependencies = parse_required_resources(row["depends_on"])
            if dependencies:
                placeholders = ",".join("?" for _ in dependencies)
                incomplete = conn.execute(
                    f"""
                    SELECT id, status
                    FROM runtime_schedule_items
                    WHERE project = ? AND id IN ({placeholders}) AND status != 'completed'
                    """,
                    [args.project, *dependencies],
                ).fetchall()
                if incomplete:
                    blockers.append({"id": row["id"], "reason": "dependencies-incomplete", "dependencies": [row_to_dict(item) for item in incomplete]})
                    continue
            conflicts = open_resource_conflicts(
                conn,
                project=args.project,
                required_resources=parse_required_resources(row["required_resources"]),
            )
            if conflicts:
                blockers.append({"id": row["id"], "reason": "resources-busy", "resources": conflicts})
                continue
            selected = row
            break
        if selected and args.advance:
            conn.execute(
                """
                UPDATE runtime_schedule_items
                SET status = 'running',
                    started_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE project = ? AND id = ?
                """,
                (args.project, selected["id"]),
            )
            record_event(
                conn,
                project=args.project,
                run_id=selected["run_id"],
                goal_id=selected["goal_id"],
                task_id=selected["task_id"],
                event_type="KernelStep",
                source="runtime-scheduler-next",
                summary=f"Scheduler advanced {selected['id']} to running.",
                payload={"schedule_id": selected["id"], "action_type": selected["action_type"]},
            )
            conn.commit()
            selected = conn.execute(
                "SELECT * FROM runtime_schedule_items WHERE project = ? AND id = ?",
                (args.project, selected["id"]),
            ).fetchone()
    print_json(
        {
            "ok": selected is not None,
            "project": args.project,
            "selected": row_to_dict(selected) if selected else None,
            "blockers": blockers,
        }
    )


def cmd_runtime_schedule_complete(args: argparse.Namespace) -> None:
    status = "completed" if args.ok else "blocked"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = conn.execute(
            "SELECT * FROM runtime_schedule_items WHERE project = ? AND id = ?",
            (args.project, args.id),
        ).fetchone()
        if row is None:
            raise SystemExit(f"Schedule item not found for project={args.project}: {args.id}")
        conn.execute(
            """
            UPDATE runtime_schedule_items
            SET status = ?,
                completed_at = CASE WHEN ? = 'completed' THEN datetime('now') ELSE completed_at END,
                blocker = ?,
                evidence = COALESCE(?, evidence),
                updated_at = datetime('now')
            WHERE project = ? AND id = ?
            """,
            (status, status, args.blocker, args.evidence, args.project, args.id),
        )
        record_event(
            conn,
            project=args.project,
            run_id=row["run_id"],
            goal_id=row["goal_id"],
            task_id=row["task_id"],
            event_type="KernelStep",
            source="runtime-schedule-complete",
            summary=f"Schedule item {args.id} marked {status}.",
            payload={"schedule_id": args.id, "status": status, "evidence": args.evidence, "blocker": args.blocker},
            severity="info" if args.ok else "warning",
        )
        conn.commit()
    print_json({"ok": args.ok, "id": args.id, "project": args.project, "status": status})


def cmd_runtime_request_resource(args: argparse.Namespace) -> None:
    lease_id = args.id or f"lease-{uuid.uuid4().hex[:8]}"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        conflicts = open_resource_conflicts(
            conn,
            project=args.project,
            required_resources=[f"{args.resource_type}:{args.resource_key}"],
        )
        status = "denied" if conflicts and not args.force else "granted"
        conn.execute(
            """
            INSERT INTO resource_leases(
                id, project, run_id, goal_id, task_id, schedule_id, resource_type,
                resource_key, quantity, status, reason, expires_at, granted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'granted' THEN datetime('now') ELSE NULL END)
            ON CONFLICT(id) DO UPDATE SET
                run_id = excluded.run_id,
                goal_id = excluded.goal_id,
                task_id = excluded.task_id,
                schedule_id = excluded.schedule_id,
                resource_type = excluded.resource_type,
                resource_key = excluded.resource_key,
                quantity = excluded.quantity,
                status = excluded.status,
                reason = excluded.reason,
                expires_at = excluded.expires_at,
                granted_at = excluded.granted_at,
                released_at = NULL,
                updated_at = datetime('now')
            """,
            (
                lease_id,
                args.project,
                args.run_id,
                args.goal_id,
                args.task_id,
                args.schedule_id,
                args.resource_type,
                args.resource_key,
                args.quantity,
                status,
                args.reason,
                args.expires_at,
                status,
            ),
        )
        record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            task_id=args.task_id,
            event_type="KernelStep",
            source="runtime-request-resource",
            summary=f"Resource {args.resource_type}:{args.resource_key} lease {status}.",
            payload={"lease_id": lease_id, "status": status, "conflicts": conflicts},
            severity="info" if status == "granted" else "warning",
        )
        conn.commit()
    print_json(
        {
            "ok": status == "granted",
            "id": lease_id,
            "project": args.project,
            "status": status,
            "conflicts": conflicts,
        }
    )


def cmd_runtime_release_resource(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = conn.execute(
            "SELECT * FROM resource_leases WHERE project = ? AND id = ?",
            (args.project, args.id),
        ).fetchone()
        if row is None:
            raise SystemExit(f"Resource lease not found for project={args.project}: {args.id}")
        conn.execute(
            """
            UPDATE resource_leases
            SET status = 'released',
                released_at = datetime('now'),
                reason = COALESCE(?, reason),
                updated_at = datetime('now')
            WHERE project = ? AND id = ?
            """,
            (args.reason, args.project, args.id),
        )
        record_event(
            conn,
            project=args.project,
            run_id=row["run_id"],
            goal_id=row["goal_id"],
            task_id=row["task_id"],
            event_type="KernelStep",
            source="runtime-release-resource",
            summary=f"Released resource lease {args.id}.",
            payload={"lease_id": args.id, "reason": args.reason},
        )
        conn.commit()
    print_json({"ok": True, "id": args.id, "project": args.project, "status": "released"})


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
    memory_hits: List[str] = []
    verification_hits: List[str] = []
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


def cmd_runtime_publish_event(args: argparse.Namespace) -> None:
    payload = {}
    if args.payload_json:
        try:
            payload = json.loads(args.payload_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid --payload-json: {exc}") from exc
    message_id = args.id or f"event-msg-{uuid.uuid4().hex[:8]}"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        event_id = None
        if args.event_type:
            event_id = record_event(
                conn,
                project=args.project,
                run_id=args.run_id,
                goal_id=args.goal_id,
                task_id=args.task_id,
                event_type=args.event_type,
                source=args.source or "event-bus",
                summary=args.summary,
                payload=payload,
                severity=args.severity,
            )
        conn.execute(
            """
            INSERT INTO event_bus_messages(
                id, project, run_id, goal_id, task_id, event_id, topic, subscriber,
                status, priority, payload_json, available_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, COALESCE(?, datetime('now')))
            ON CONFLICT(id) DO UPDATE SET
                run_id = excluded.run_id,
                goal_id = excluded.goal_id,
                task_id = excluded.task_id,
                event_id = excluded.event_id,
                topic = excluded.topic,
                subscriber = excluded.subscriber,
                status = 'pending',
                priority = excluded.priority,
                payload_json = excluded.payload_json,
                available_at = excluded.available_at,
                delivered_at = NULL,
                acknowledged_at = NULL,
                failure_detail = NULL,
                updated_at = datetime('now')
            """,
            (
                message_id,
                args.project,
                args.run_id,
                args.goal_id,
                args.task_id,
                event_id,
                args.topic,
                args.subscriber,
                args.priority,
                json.dumps(payload, ensure_ascii=False),
                args.available_at,
            ),
        )
        conn.commit()
    print_json(
        {
            "ok": True,
            "id": message_id,
            "event_id": event_id,
            "project": args.project,
            "topic": args.topic,
            "subscriber": args.subscriber,
            "status": "pending",
        }
    )


def cmd_runtime_poll_events(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        rows = conn.execute(
            """
            SELECT *
            FROM event_bus_messages
            WHERE project = ?
              AND status = 'pending'
              AND (subscriber = ? OR subscriber = '*')
              AND datetime(available_at) <= datetime('now')
              AND (? IS NULL OR topic = ?)
            ORDER BY priority DESC, created_at
            LIMIT ?
            """,
            (args.project, args.subscriber, args.topic, args.topic, args.limit),
        ).fetchall()
        ids = [row["id"] for row in rows]
        if args.deliver and ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE event_bus_messages
                SET status = 'delivered',
                    delivered_at = datetime('now'),
                    updated_at = datetime('now')
                WHERE project = ? AND id IN ({placeholders})
                """,
                [args.project, *ids],
            )
            conn.commit()
            rows = conn.execute(
                f"""
                SELECT *
                FROM event_bus_messages
                WHERE project = ? AND id IN ({placeholders})
                ORDER BY priority DESC, created_at
                """,
                [args.project, *ids],
            ).fetchall()
    print_json(
        {
            "ok": True,
            "project": args.project,
            "subscriber": args.subscriber,
            "topic": args.topic,
            "messages": [row_to_dict(row) for row in rows],
        }
    )


def cmd_runtime_ack_event(args: argparse.Namespace) -> None:
    status = "acknowledged" if args.ok else "failed"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        row = conn.execute(
            "SELECT * FROM event_bus_messages WHERE project = ? AND id = ?",
            (args.project, args.id),
        ).fetchone()
        if row is None:
            raise SystemExit(f"Event bus message not found for project={args.project}: {args.id}")
        conn.execute(
            """
            UPDATE event_bus_messages
            SET status = ?,
                acknowledged_at = CASE WHEN ? = 'acknowledged' THEN datetime('now') ELSE acknowledged_at END,
                failure_detail = ?,
                updated_at = datetime('now')
            WHERE project = ? AND id = ?
            """,
            (status, status, args.failure_detail, args.project, args.id),
        )
        conn.commit()
    print_json({"ok": args.ok, "id": args.id, "project": args.project, "status": status})


def cmd_runtime_detect_intent(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    provider = args.provider or os.environ.get("AGENT_OS_LLM_PROVIDER") or "builtin"
    api_key = args.api_key or os.environ.get("AGENT_OS_LLM_API_KEY")
    mission_ir, compiler_metadata = compile_mission_ir(
        context,
        provider=provider,
        base_url=args.base_url or os.environ.get("AGENT_OS_LLM_BASE_URL"),
        api_key=api_key,
        model=args.model or os.environ.get("AGENT_OS_LLM_MODEL"),
        llm_response=args.llm_response,
        timeout=args.timeout,
        no_fallback=args.no_fallback,
    )
    context["mission_ir"] = mission_ir
    context["compiler_metadata"] = {
        key: value for key, value in compiler_metadata.items() if key != "raw_response"
    }
    intent_type, mutation_authorization, confidence = mission_to_runtime_intent(mission_ir, context)
    runtime_mapping = {
        "intent_type": intent_type,
        "mutation_authorization": mutation_authorization,
        "confidence": confidence,
    }
    visible_intent = visible_intent_for(mission_ir, compiler_metadata, runtime_mapping)
    state = intent_state_from_context(
        context,
        goal_id=args.goal_id,
        run_id=args.run_id,
        intent_id=args.intent_id,
    )
    event_id = None
    if args.record:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            upsert_intent_state(conn, state)
            event_id = record_event(
                conn,
                project=state["project"],
                run_id=args.run_id,
                goal_id=args.goal_id,
                event_type="IntentDetected",
                source="runtime-detect-intent",
                summary=(
                    f"Compiled {mission_ir['mission']['type']} mission with "
                    f"{state['mutation_authorization']} mutation authorization."
                ),
                payload={"context": context, "intent": state},
            )
            conn.commit()
    print_json(
        {
            "ok": True,
            "event_id": event_id,
            "context": context,
            "mission_ir": mission_ir,
            "compiler_metadata": compiler_metadata,
            "visible_intent": visible_intent,
            "intent": state,
        }
    )


def cmd_runtime_compile_mission(args: argparse.Namespace) -> None:
    context = context_for_request(args.project, args.request, args.files)
    provider = args.provider or os.environ.get("AGENT_OS_LLM_PROVIDER") or "builtin"
    api_key = args.api_key or os.environ.get("AGENT_OS_LLM_API_KEY")
    mission_ir, compiler_metadata = compile_mission_ir(
        context,
        provider=provider,
        base_url=args.base_url or os.environ.get("AGENT_OS_LLM_BASE_URL"),
        api_key=api_key,
        model=args.model or os.environ.get("AGENT_OS_LLM_MODEL"),
        llm_response=args.llm_response,
        timeout=args.timeout,
        no_fallback=args.no_fallback,
    )
    intent_type, mutation_authorization, confidence = mission_to_runtime_intent(mission_ir, context)
    runtime_mapping = {
        "intent_type": intent_type,
        "mutation_authorization": mutation_authorization,
        "confidence": confidence,
    }
    visible_intent = visible_intent_for(mission_ir, compiler_metadata, runtime_mapping)
    print_json(
        {
            "ok": True,
            "context": context,
            "mission_ir": mission_ir,
            "locked": True,
            "runtime_mapping": runtime_mapping,
            "compiler_metadata": compiler_metadata,
            "visible_intent": visible_intent,
        }
    )


def cmd_runtime_tool_registry(args: argparse.Namespace) -> None:
    tools = []
    for name, meta in sorted(TOOL_REGISTRY.items()):
        actions = sorted(meta["actions"])
        if args.action and args.action not in actions:
            continue
        if args.write_only and not set(actions).intersection(READ_ONLY_BLOCKED_ACTIONS):
            continue
        tools.append({"tool": name, "actions": actions, "description": meta["description"]})
    print_json(
        {
            "ok": True,
            "tools": tools,
            "read_only_blocked_actions": sorted(READ_ONLY_BLOCKED_ACTIONS),
            "action_types": list(ACTION_TYPES),
        }
    )


def action_gate_inputs_from_args(args: argparse.Namespace, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    project = args.project
    intent_row = None
    if conn is not None and getattr(args, "intent_id", None):
        intent_row = fetch_intent_state(conn, project=project, intent_id=args.intent_id)
        if intent_row is None:
            raise SystemExit(f"Intent not found for project={project}: {args.intent_id}")

    intent_type = args.intent_type or (intent_row["intent_type"] if intent_row else "task")
    mutation_authorization = args.mutation_authorization or (
        intent_row["mutation_authorization"] if intent_row else "ambiguous"
    )
    approved_scope = args.approved_scope
    if approved_scope is None and intent_row is not None:
        approved_scope = intent_row["approved_scope"]
    confidence = args.confidence
    if confidence is None and intent_row is not None:
        confidence = float(intent_row["confidence"])
    if confidence is None:
        confidence = 0.5
    risk_level = args.risk_level or (intent_row["risk_level"] if intent_row else "normal")
    action_type = args.action_type
    if not action_type:
        action_type = classify_tool_type(args.command or args.target, args.tool_type or None)
        if action_type not in ACTION_TYPES:
            action_type = "shell" if action_type == "shell" else "read"
    tool = tool_key_for_action(
        action_type=action_type,
        tool=args.tool,
        command=args.command,
        method=getattr(args, "method", None),
        browser_action=getattr(args, "browser_action", None),
        allow_unsafe=getattr(args, "allow_unsafe", False),
    )
    gate = evaluate_action_gate(
        intent_type=intent_type,
        mutation_authorization=mutation_authorization,
        action_type=action_type,
        tool=tool,
        target_paths=args.target_paths,
        approved_scope=approved_scope,
        confidence=confidence,
        risk_level=risk_level,
        user_approved=args.user_approved,
        validation_plan=args.validation_plan,
    )
    return {
        "project": project,
        "intent_id": getattr(args, "intent_id", None),
        "intent_type": intent_type,
        "mutation_authorization": mutation_authorization,
        "approved_scope": approved_scope,
        "confidence": confidence,
        "risk_level": risk_level,
        "action_type": action_type,
        "tool": tool,
        "target_paths": args.target_paths,
        "validation_plan": args.validation_plan,
        "gate": gate,
    }


def cmd_runtime_validate_action(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        data = action_gate_inputs_from_args(args, conn)
        if args.record:
            record_event(
                conn,
                project=args.project,
                run_id=args.run_id,
                goal_id=args.goal_id,
                event_type="ActionBlocked" if data["gate"]["decision"] == "blocked" else "ActionProposed",
                source="runtime-validate-action",
                summary=f"Action {data['action_type']} via {data['tool']} is {data['gate']['decision']}.",
                payload=data,
                severity="warning" if data["gate"]["decision"] != "allowed" else "info",
            )
            conn.commit()
    print_json({"ok": data["gate"]["decision"] == "allowed", **data})


def cmd_runtime_propose_action(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        data = action_gate_inputs_from_args(args, conn)
        proposal_id = insert_action_proposal(
            conn,
            project=args.project,
            intent_id=args.intent_id,
            goal_id=args.goal_id,
            run_id=args.run_id,
            action_type=data["action_type"],
            tool=data["tool"],
            target_paths=args.target_paths,
            reason=args.reason,
            risk_level=data["risk_level"],
            validation_plan=args.validation_plan,
            gate=data["gate"],
            proposal_id=args.id,
        )
        event_type = "ActionBlocked" if data["gate"]["decision"] == "blocked" else "ActionProposed"
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            event_type=event_type,
            source="runtime-propose-action",
            summary=f"Action proposal {proposal_id} is {data['gate']['decision']}.",
            payload={**data, "proposal_id": proposal_id, "reason": args.reason},
            severity="warning" if data["gate"]["decision"] != "allowed" else "info",
        )
        conn.commit()
    print_json({"ok": data["gate"]["decision"] == "allowed", "id": proposal_id, "event_id": event_id, **data})


def proposal_row_or_die(conn: sqlite3.Connection, *, project: str, proposal_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM action_proposals WHERE project = ? AND id = ?",
        (project, proposal_id),
    ).fetchone()
    if row is None:
        raise SystemExit(f"Action proposal not found for project={project}: {proposal_id}")
    return row


def cmd_runtime_execution_gate(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.proposal_id:
            proposal = proposal_row_or_die(conn, project=args.project, proposal_id=args.proposal_id)
            intent = fetch_intent_state(conn, project=args.project, intent_id=proposal["intent_id"])
            intent_type = args.intent_type or (intent["intent_type"] if intent else "task")
            mutation_authorization = args.mutation_authorization or (
                intent["mutation_authorization"] if intent else "ambiguous"
            )
            approved_scope = args.approved_scope or (intent["approved_scope"] if intent else None)
            confidence = args.confidence if args.confidence is not None else (float(intent["confidence"]) if intent else 0.5)
            risk_level = args.risk_level or proposal["risk_level"]
            gate = evaluate_action_gate(
                intent_type=intent_type,
                mutation_authorization=mutation_authorization,
                action_type=proposal["action_type"],
                tool=proposal["tool"],
                target_paths=proposal["target_paths"],
                approved_scope=approved_scope,
                confidence=confidence,
                risk_level=risk_level,
                user_approved=args.user_approved,
                validation_plan=args.validation_plan or proposal["validation_plan"],
            )
            data = {
                "project": args.project,
                "proposal_id": args.proposal_id,
                "intent_id": proposal["intent_id"],
                "intent_type": intent_type,
                "mutation_authorization": mutation_authorization,
                "approved_scope": approved_scope,
                "confidence": confidence,
                "risk_level": risk_level,
                "action_type": proposal["action_type"],
                "tool": proposal["tool"],
                "target_paths": proposal["target_paths"],
                "validation_plan": args.validation_plan or proposal["validation_plan"],
                "gate": gate,
            }
        else:
            data = action_gate_inputs_from_args(args, conn)

        if args.record or args.proposal_id:
            if args.proposal_id:
                conn.execute(
                    """
                    UPDATE action_proposals
                    SET status = ?, gate_decision = ?, gate_reason = ?,
                        requires_approval = ?, updated_at = datetime('now')
                    WHERE project = ? AND id = ?
                    """,
                    (
                        data["gate"]["decision"],
                        data["gate"]["decision"],
                        data["gate"]["reason"],
                        int(data["gate"]["requires_approval"]),
                        args.project,
                        args.proposal_id,
                    ),
                )
            event_id = record_event(
                conn,
                project=args.project,
                run_id=args.run_id,
                goal_id=args.goal_id,
                event_type="ActionBlocked" if data["gate"]["decision"] == "blocked" else "ActionProposed",
                source="runtime-execution-gate",
                summary=f"Execution gate returned {data['gate']['decision']} for {data['action_type']} via {data['tool']}.",
                payload=data,
                severity="warning" if data["gate"]["decision"] != "allowed" else "info",
            )
            conn.commit()
        else:
            event_id = None
    print_json({"ok": data["gate"]["decision"] == "allowed", "event_id": event_id, **data})


def cmd_runtime_approve_action(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.proposal_id:
            proposal_row_or_die(conn, project=args.project, proposal_id=args.proposal_id)
        cur = conn.execute(
            """
            INSERT INTO approval_records(
                project, intent_id, proposal_id, approved_by_user_text, approved_scope, expires_when
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (args.project, args.intent_id, args.proposal_id, args.approved_text, args.approved_scope, args.expires_when),
        )
        if args.intent_id:
            conn.execute(
                """
                UPDATE intent_states
                SET mutation_authorization = 'fix-authorized',
                    current_phase = 'approved',
                    approved_scope = COALESCE(?, approved_scope),
                    updated_at = datetime('now')
                WHERE project = ? AND id = ?
                """,
                (args.approved_scope, args.project, args.intent_id),
            )
        if args.proposal_id:
            conn.execute(
                """
                UPDATE action_proposals
                SET status = 'approved',
                    requires_approval = 0,
                    updated_at = datetime('now')
                WHERE project = ? AND id = ?
                """,
                (args.project, args.proposal_id),
            )
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            event_type="ActionApproved",
            source="runtime-approve-action",
            summary="User approval recorded for action execution.",
            payload={
                "approval_id": cur.lastrowid,
                "intent_id": args.intent_id,
                "proposal_id": args.proposal_id,
                "approved_scope": args.approved_scope,
                "approved_text": args.approved_text,
            },
        )
        conn.commit()
    print_json({"ok": True, "id": cur.lastrowid, "event_id": event_id, "project": args.project})


def cmd_runtime_record_feedback(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        cur = conn.execute(
            """
            INSERT INTO feedback_events(
                project, intent_id, proposal_id, observation_id, confidence_delta,
                risk_delta, scope_delta, evidence_delta, summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.project,
                args.intent_id,
                args.proposal_id,
                args.observation_id,
                args.confidence_delta,
                args.risk_delta,
                args.scope_delta,
                args.evidence_delta,
                args.summary,
            ),
        )
        if args.intent_id:
            conn.execute(
                """
                UPDATE intent_states
                SET confidence = MIN(1, MAX(0, confidence + ?)),
                    current_phase = CASE
                        WHEN ? IN ('contradicts', 'new-evidence') THEN 'planning'
                        ELSE current_phase
                    END,
                    updated_at = datetime('now')
                WHERE project = ? AND id = ?
                """,
                (args.confidence_delta, args.evidence_delta, args.project, args.intent_id),
            )
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            event_type="FeedbackRecorded",
            source="runtime-record-feedback",
            summary=args.summary,
            payload={
                "feedback_id": cur.lastrowid,
                "intent_id": args.intent_id,
                "proposal_id": args.proposal_id,
                "confidence_delta": args.confidence_delta,
                "risk_delta": args.risk_delta,
                "scope_delta": args.scope_delta,
                "evidence_delta": args.evidence_delta,
            },
        )
        conn.commit()
    print_json({"ok": True, "id": cur.lastrowid, "event_id": event_id, "project": args.project})


def detect_drift_from_state(
    *,
    intent: Optional[sqlite3.Row],
    proposal: Optional[sqlite3.Row],
    actual_action: Optional[str],
    actual_tool: Optional[str],
    actual_scope: Optional[str],
    confidence: Optional[float],
) -> List[Dict[str, Any]]:
    drifts: List[Dict[str, Any]] = []
    if intent is not None:
        mutation_authorization = intent["mutation_authorization"]
        expected_scope = intent["approved_scope"]
        expected_actions = {part.strip() for part in (intent["allowed_actions"] or "").split(",") if part.strip()}
        action = actual_action or (proposal["action_type"] if proposal else None)
        tool = actual_tool or (proposal["tool"] if proposal else None)
        tool_actions = set(TOOL_REGISTRY.get(tool or "", {"actions": set()})["actions"])
        action_set = {item for item in {action, *tool_actions} if item}
        if mutation_authorization == "read-only" and action_set.intersection(READ_ONLY_BLOCKED_ACTIONS):
            drifts.append(
                {
                    "drift_type": "mutation",
                    "severity": "error",
                    "expected": "read-only intent must not mutate files, docs, memory, git, deploy, or runtime state",
                    "actual": f"action={action}; tool={tool}; actions={','.join(sorted(action_set))}",
                }
            )
        if expected_actions and action and action not in expected_actions and action_set.isdisjoint(expected_actions):
            drifts.append(
                {
                    "drift_type": "tool",
                    "severity": "warning",
                    "expected": f"allowed actions: {','.join(sorted(expected_actions))}",
                    "actual": f"action={action}; tool={tool}",
                }
            )
        scope_ok, scope_reason = scope_matches(actual_scope or (proposal["target_paths"] if proposal else None), expected_scope)
        if not scope_ok:
            drifts.append(
                {
                    "drift_type": "scope",
                    "severity": "warning",
                    "expected": expected_scope or "approved scope",
                    "actual": scope_reason,
                }
            )
        if confidence is not None and confidence < 0.7 and action_set.intersection(READ_ONLY_BLOCKED_ACTIONS):
            drifts.append(
                {
                    "drift_type": "confidence",
                    "severity": "warning",
                    "expected": "confidence >= 0.7 before mutating actions",
                    "actual": f"confidence={confidence}",
                }
            )
    return drifts


def cmd_runtime_detect_drift(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        intent = fetch_intent_state(conn, project=args.project, intent_id=args.intent_id)
        proposal = proposal_row_or_die(conn, project=args.project, proposal_id=args.proposal_id) if args.proposal_id else None
        drifts = detect_drift_from_state(
            intent=intent,
            proposal=proposal,
            actual_action=args.actual_action,
            actual_tool=args.actual_tool,
            actual_scope=args.actual_scope,
            confidence=args.confidence,
        )
        drift_ids: List[int] = []
        if args.record:
            for drift in drifts:
                cur = conn.execute(
                    """
                    INSERT INTO drift_events(
                        project, intent_id, proposal_id, feedback_id, drift_type,
                        severity, expected, actual, resolution, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
                    """,
                    (
                        args.project,
                        args.intent_id,
                        args.proposal_id,
                        args.feedback_id,
                        drift["drift_type"],
                        drift["severity"],
                        drift["expected"],
                        drift["actual"],
                        args.resolution,
                    ),
                )
                drift_ids.append(cur.lastrowid)
                record_event(
                    conn,
                    project=args.project,
                    run_id=args.run_id,
                    goal_id=args.goal_id,
                    event_type="DriftDetected",
                    source="runtime-detect-drift",
                    summary=f"{drift['drift_type']} drift detected.",
                    payload={**drift, "drift_id": cur.lastrowid},
                    severity=drift["severity"],
                )
            conn.commit()
    print_json({"ok": not drifts, "project": args.project, "drifts": drifts, "drift_ids": drift_ids})


def cmd_runtime_reanchor(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        intent = fetch_intent_state(conn, project=args.project, intent_id=args.intent_id)
        if intent is None:
            raise SystemExit(f"Intent not found for project={args.project}: {args.intent_id}")
        open_drifts = conn.execute(
            """
            SELECT *
            FROM drift_events
            WHERE project = ? AND intent_id = ? AND status = 'open'
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (args.project, args.intent_id),
        ).fetchall()
        prompt = args.prompt or (
            f"Current intent is {intent['intent_type']} with {intent['mutation_authorization']} authorization. "
            "Execution drift was detected. Re-anchor with the user before continuing: confirm whether to stay read-only, revise the plan, or authorize a fix."
        )
        conn.execute(
            """
            UPDATE intent_states
            SET current_phase = 'awaiting-approval', updated_at = datetime('now')
            WHERE project = ? AND id = ?
            """,
            (args.project, args.intent_id),
        )
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            event_type="ReanchorRequested",
            source="runtime-reanchor",
            summary=prompt,
            payload={"intent_id": args.intent_id, "open_drifts": [row_to_dict(row) for row in open_drifts]},
            severity="warning" if open_drifts else "info",
        )
        conn.commit()
    print_json(
        {
            "ok": True,
            "event_id": event_id,
            "project": args.project,
            "intent_id": args.intent_id,
            "prompt": prompt,
            "open_drifts": [row_to_dict(row) for row in open_drifts],
        }
    )


def cmd_runtime_revise_plan(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.intent_id and fetch_intent_state(conn, project=args.project, intent_id=args.intent_id) is None:
            raise SystemExit(f"Intent not found for project={args.project}: {args.intent_id}")
        if args.version is None:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM plan_versions WHERE project = ? AND intent_id IS ?",
                (args.project, args.intent_id),
            ).fetchone()
            version = int(row["version"])
        else:
            version = args.version
        if args.status == "active" and args.intent_id:
            conn.execute(
                """
                UPDATE plan_versions
                SET status = 'superseded'
                WHERE project = ? AND intent_id = ? AND status = 'active'
                """,
                (args.project, args.intent_id),
            )
        cur = conn.execute(
            """
            INSERT INTO plan_versions(
                project, intent_id, version, assumptions, steps, validation, rollback, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(intent_id, version) DO UPDATE SET
                assumptions = excluded.assumptions,
                steps = excluded.steps,
                validation = excluded.validation,
                rollback = excluded.rollback,
                status = excluded.status
            """,
            (
                args.project,
                args.intent_id,
                version,
                args.assumptions,
                args.steps,
                args.validation,
                args.rollback,
                args.status,
            ),
        )
        if args.intent_id:
            conn.execute(
                """
                UPDATE intent_states
                SET current_phase = 'planning', updated_at = datetime('now')
                WHERE project = ? AND id = ?
                """,
                (args.project, args.intent_id),
            )
        event_id = record_event(
            conn,
            project=args.project,
            run_id=args.run_id,
            goal_id=args.goal_id,
            event_type="PlanRevised",
            source="runtime-revise-plan",
            summary=f"Plan version {version} recorded as {args.status}.",
            payload={
                "intent_id": args.intent_id,
                "version": version,
                "assumptions": args.assumptions,
                "steps": args.steps,
                "validation": args.validation,
                "rollback": args.rollback,
                "status": args.status,
            },
        )
        conn.commit()
    print_json({"ok": True, "id": cur.lastrowid, "event_id": event_id, "project": args.project, "version": version})


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
    visible_plan = visible_plan_for_tasks(tasks, context, capability_status=capability_status)
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
            "visible_plan": visible_plan,
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
    blockers: List[str] = []
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
    status_counts: Dict[str, int] = {}
    for manifest in manifests:
        status_counts[manifest["status"]] = status_counts.get(manifest["status"], 0) + 1
    blockers: List[str] = []
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
    visible_plan = visible_plan_for_tasks(tasks, context, capability_status=args.capability_status)
    created: List[str] = []
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
    print_json(
        {
            "ok": True,
            "project": args.project,
            "tasks": tasks,
            "visible_plan": visible_plan,
            "created_task_ids": created,
        }
    )


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
    extra_fields: Dict[str, Any] = {}
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


def classify_tool_type(command: Optional[str], explicit_type: Optional[str] = None) -> str:
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


def redact_secrets(text: Optional[str]) -> Optional[str]:
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


def model_provider_config(provider: str) -> Dict[str, Any]:
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


def execute_model_adapter(args: argparse.Namespace, adapter: str) -> Dict[str, Any]:
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


def classify_failure(exit_code: Optional[int], output: str) -> Optional[str]:
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


def classify_failure_detail(exit_code: Optional[int], output: str, command: Optional[str] = None) -> dict[str, Optional[str]]:
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


def parse_header_values(values: Optional[List[str]]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
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


def run_shell_adapter(command: str, timeout: int, allow_unsafe: bool) -> Dict[str, Any]:
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


def run_git_adapter(action: Optional[str], target: Optional[str], timeout: int) -> Dict[str, Any]:
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


def run_url_fetch_adapter(*, url: str, method: str, headers: Dict[str, str], body: Optional[str], timeout: int, expect_text: Optional[str], browser_mode: bool = False) -> Dict[str, Any]:
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


def run_browser_adapter(*, url: str, action: str, selector: Optional[str], text: Optional[str], expect_text: Optional[str], screenshot_path: Optional[str], timeout: int) -> Dict[str, Any]:
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


def record_tool_run(conn, *, project: str, goal_id: Optional[str], run_id: Optional[str], task_id: Optional[str], tool_type: str, adapter: str, command: Optional[str], target: Optional[str], status: str, exit_code: Optional[int], duration_ms: Optional[int], stdout_summary: Optional[str], failure_type: Optional[str], failure_detail: Optional[str], evidence: Optional[str]) -> int:
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


def model_adapter_name(provider: str, adapter: Optional[str] = None) -> str:
    if adapter:
        return adapter
    return f"{provider}-model-adapter"


def record_model_run(conn, *, project: str, goal_id: Optional[str], run_id: Optional[str], task_id: Optional[str], provider: str, model_name: str, adapter: str, operation: str, status: str, duration_ms: Optional[int], input_tokens: Optional[int], output_tokens: Optional[int], cost_estimate: Optional[float], prompt_summary: Optional[str], response_summary: Optional[str], failure_type: Optional[str], failure_detail: Optional[str], evidence: Optional[str]) -> int:
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
    adapter_result: Dict[str, Any] = {}
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


def subagent_chain_for(roles: List[str]) -> list[Dict[str, Any]]:
    chain: list[Dict[str, Any]] = []
    for index, role in enumerate(roles):
        handoff_to = roles[index + 1] if index + 1 < len(roles) else None
        boundary = {
            "planner": "Plan only; create scoped task decomposition and handoff.",
            "executor": "Execute scoped implementation only; do not approve own work.",
            "reviewer": "Review only; inspect diff and produce findings.",
            "verifier": "Verify only; run validation plan and report evidence.",
            "documentation-recorder": "Write assigned documentation only; do not change implementation or memory.",
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
    created: list[Dict[str, Any]] = []
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


def build_review_findings(diff_text: str) -> list[Dict[str, str]]:
    findings: list[Dict[str, str]] = []
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
    evidence_payload: Dict[str, Any] = {"role": args.role}

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
    declared_capabilities: List[str],
    required_capabilities: Optional[List[str]] = None,
) -> Dict[str, Any]:
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
    issues: List[str] = []
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
    adapters: list[Dict[str, Any]] = []
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


def agent_entrypoint_for_host(host_type: str) -> str:
    mapping = {
        "codex": "AGENTS.md",
        "claude": "CLAUDE.md",
        "qwen": "QWEN.md",
        "cursor": ".cursor/rules/agent-os.md",
        "vscode": "AGENTS.md",
        "cli": "AGENTS.md",
        "mcp": "AGENTS.md",
        "custom": "AGENTS.md",
    }
    return mapping.get(host_type, "AGENTS.md")


def cmd_runtime_compatibility_matrix(args: argparse.Namespace) -> None:
    providers = args.provider or list(MODEL_PROVIDERS)
    hosts = args.host_type or list(HOST_TYPES)
    provider_rows = []
    for provider in providers:
        diagnostics = model_provider_config(provider)
        provider_rows.append(
            {
                "provider": provider,
                "status": diagnostics["status"],
                "missing_env": diagnostics.get("missing_env", []),
                "required_env": diagnostics.get("required_env", []),
                "adapter": model_adapter_name(provider),
            }
        )
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        host_rows = []
        for host in hosts:
            adapters = conn.execute(
                """
                SELECT *
                FROM host_adapters
                WHERE project = ? AND host_type = ?
                ORDER BY updated_at DESC
                """,
                (args.project, host),
            ).fetchall()
            declared = []
            available = []
            for row in adapters:
                capabilities = json.loads(row["capabilities_json"] or "[]")
                declared.extend(capabilities)
                if row["status"] == "available":
                    available.append(row["adapter_name"])
            protocol = sorted(HOST_CAPABILITY_PROTOCOL.get(host, set()))
            supported = sorted(set(declared).intersection(protocol))
            missing = sorted(set(args.require_capability or protocol) - set(declared)) if args.require_capability else []
            host_rows.append(
                {
                    "host_type": host,
                    "entrypoint": agent_entrypoint_for_host(host),
                    "protocol_capabilities": protocol,
                    "declared_capabilities": sorted(set(declared)),
                    "supported_capabilities": supported,
                    "missing_capabilities": missing,
                    "available_adapters": available,
                    "status": "compatible" if available and not missing else "needs-adapter" if not available else "missing-capability",
                }
            )
    ok = all(row["status"] in {"configured", "optional", "custom-adapter-required"} for row in provider_rows) and all(
        row["status"] == "compatible" for row in host_rows
    )
    report = {"ok": ok, "project": args.project, "providers": provider_rows, "hosts": host_rows}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print_json(report)


def cmd_runtime_governance_proposal(args: argparse.Namespace) -> None:
    source_type = args.source_type or "rule"
    status = "reviewing" if args.ready_for_review else "candidate"
    review_result = "requires-human-review"
    if not args.validation:
        review_result = "missing-validation"
    elif not args.scope or not args.boundary:
        review_result = "missing-scope-boundary"
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
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
                args.name,
                source_type,
                args.trigger,
                args.evidence,
                args.scope,
                args.boundary,
                status,
                review_result,
            ),
        )
        row = conn.execute(
            """
            SELECT id, status, review_result
            FROM improvement_reviews
            WHERE project = ? AND candidate_name = ? AND source_type = ?
            """,
            (args.project, args.name, source_type),
        ).fetchone()
        record_event(
            conn,
            project=args.project,
            goal_id=args.goal_id,
            run_id=args.run_id,
            event_type="KernelStep",
            source="runtime-governance-proposal",
            summary=f"Governance proposal recorded for {args.name}.",
            payload={
                "proposal_id": row["id"],
                "candidate_name": args.name,
                "source_type": source_type,
                "status": row["status"],
                "review_result": row["review_result"],
                "auto_promote": False,
            },
            severity="info" if review_result == "requires-human-review" else "warning",
        )
        conn.commit()
    print_json(
        {
            "ok": review_result == "requires-human-review",
            "id": row["id"],
            "project": args.project,
            "name": args.name,
            "source_type": source_type,
            "status": row["status"],
            "review_result": row["review_result"],
            "auto_promote": False,
        }
    )


def count_retries(rows: list[sqlite3.Row], key_fields: Tuple[str, ...], status_field: str) -> int:
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


def calculate_runtime_metrics(conn, project: str, goal_id: Optional[str] = None, run_id: Optional[str] = None, docs_freshness: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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


def scoped_rows(conn, table: str, project: str, goal_id: Optional[str], run_id: Optional[str], order_column: str = "created_at") -> list[Dict[str, Any]]:
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


def scoped_intent_ids(conn, project: str, goal_id: Optional[str], run_id: Optional[str]) -> list[str]:
    where = ["project = ?"]
    params: list[Any] = [project]
    if goal_id:
        where.append("(goal_id = ? OR goal_id IS NULL)")
        params.append(goal_id)
    if run_id:
        where.append("(run_id = ? OR run_id IS NULL)")
        params.append(run_id)
    rows = conn.execute(
        f"SELECT id FROM intent_states WHERE {' AND '.join(where)} ORDER BY updated_at",
        params,
    ).fetchall()
    return [row["id"] for row in rows]


def scoped_intent_rows(
    conn,
    table: str,
    project: str,
    goal_id: Optional[str],
    run_id: Optional[str],
    order_column: str = "created_at",
) -> list[Dict[str, Any]]:
    intent_ids = scoped_intent_ids(conn, project, goal_id, run_id)
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    where = ["project = ?"]
    params: list[Any] = [project]
    if "goal_id" in columns and goal_id:
        where.append("(goal_id = ? OR goal_id IS NULL)")
        params.append(goal_id)
    if "run_id" in columns and run_id:
        where.append("(run_id = ? OR run_id IS NULL)")
        params.append(run_id)
    if "intent_id" in columns and (goal_id or run_id):
        if intent_ids:
            placeholders = ",".join("?" for _ in intent_ids)
            where.append(f"(intent_id IN ({placeholders}) OR intent_id IS NULL)")
            params.extend(intent_ids)
        else:
            where.append("intent_id IS NULL")
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE {' AND '.join(where)} ORDER BY {order_column}",
        params,
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def trace_time_value(item: Dict[str, Any]) -> str:
    for key in ("created_at", "updated_at", "validated_at", "registered_at", "exported_at", "ran_at", "completed_at", "started_at"):
        if item.get(key):
            return str(item[key])
    return ""


def trace_timeline(trace: Dict[str, Any]) -> list[Dict[str, Any]]:
    sources = [
        ("goal", [trace["goal"]] if trace.get("goal") else []),
        ("run", [trace["run"]] if trace.get("run") else []),
        ("context", [trace["context"]] if trace.get("context") else []),
        ("task", trace.get("tasks", [])),
        ("intent", trace.get("intents", [])),
        ("action", trace.get("action_proposals", [])),
        ("feedback", trace.get("feedback", [])),
        ("drift", trace.get("drifts", [])),
        ("plan", trace.get("plan_versions", [])),
        ("policy", trace.get("policies", [])),
        ("skill", trace.get("skill_recommendations", [])),
        ("tool", trace.get("tool_runs", [])),
        ("model", trace.get("model_runs", [])),
        ("subagent", trace.get("subagent_runs", [])),
        ("verification", trace.get("verifications", [])),
        ("event", trace.get("events", [])),
        ("event-message", trace.get("event_messages", [])),
        ("schedule", trace.get("schedule_items", [])),
        ("resource", trace.get("resource_leases", [])),
        ("quality", trace.get("quality_scores", [])),
        ("self-audit", trace.get("self_audit_findings", [])),
        ("benchmark", trace.get("benchmarks", [])),
        ("recovery", trace.get("recoveries", [])),
    ]
    timeline: list[Dict[str, Any]] = []
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


def build_runtime_trace(conn, project: str, goal_id: Optional[str] = None, run_id: Optional[str] = None) -> Dict[str, Any]:
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
        "intents": scoped_rows(conn, "intent_states", project, goal_id, run_id, "updated_at"),
        "action_proposals": scoped_rows(conn, "action_proposals", project, goal_id, run_id, "updated_at"),
        "feedback": scoped_intent_rows(conn, "feedback_events", project, goal_id, run_id),
        "drifts": scoped_intent_rows(conn, "drift_events", project, goal_id, run_id),
        "plan_versions": scoped_intent_rows(conn, "plan_versions", project, goal_id, run_id),
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
        "event_messages": scoped_rows(conn, "event_bus_messages", project, goal_id, run_id, "created_at"),
        "schedule_items": scoped_rows(conn, "runtime_schedule_items", project, goal_id, run_id, "created_at"),
        "resource_leases": scoped_rows(conn, "resource_leases", project, goal_id, run_id, "created_at"),
        "quality_scores": scoped_rows(conn, "quality_scores", project, goal_id, run_id, "created_at"),
        "self_audit_findings": scoped_rows(conn, "self_audit_findings", project, goal_id, run_id, "created_at"),
        "benchmarks": scoped_rows(conn, "benchmark_runs", project, goal_id, run_id, "created_at"),
    }
    timeline = trace_timeline(trace)
    trace["timeline"] = timeline
    trace["duration_ms"] = sum(item["duration_ms"] or 0 for item in timeline)
    trace["input_hash"] = stable_json_hash({"project": project, "goal_id": goal_id, "run_id": run_id, "request": trace.get("run", {}).get("request") if trace.get("run") else None})
    trace["output_hash"] = stable_json_hash({key: trace[key] for key in ("tasks", "intents", "action_proposals", "feedback", "drifts", "plan_versions", "policies", "skill_recommendations", "tool_runs", "model_runs", "subagent_runs", "verifications", "events", "event_messages", "schedule_items", "resource_leases", "quality_scores", "self_audit_findings", "benchmarks")})
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


def check_required_paths(root: Path) -> tuple[str, List[str]]:
    required_dirs = ["context", "rules", "skills", "tools", "workflows", "memory", "scripts", "tests"]
    missing = [path for path in required_dirs if not (root / path).is_dir()]
    return ("passed" if not missing else "failed", [f"missing directory: {path}" for path in missing])


def check_agents_file(root: Path) -> tuple[str, List[str]]:
    agents_path = root / "AGENTS.md"
    if not agents_path.exists():
        return "failed", ["missing AGENTS.md"]
    text = agents_path.read_text(encoding="utf-8", errors="ignore")
    required_terms = ["Agent OS", "Mandatory Gates", "Execution Flow", "Project-Local Asset Priority"]
    missing = [term for term in required_terms if term not in text]
    return ("passed" if not missing else "failed", [f"AGENTS.md missing section: {term}" for term in missing])


def check_rules(root: Path) -> tuple[str, List[str]]:
    rules_dir = root / "rules"
    required_rules = ["coding-style.md", "testing.md", "change-policy.md", "agent-runtime.md", "security-hardening.md"]
    missing = [name for name in required_rules if not (rules_dir / name).exists()]
    return ("passed" if not missing else "failed", [f"missing rule: {name}" for name in missing])


def check_skills(root: Path) -> tuple[str, List[str]]:
    manifests = validate_skill_runtime(root / "skills")
    if not manifests:
        return "failed", ["no skills found"]
    issues = []
    for manifest in manifests:
        if manifest["status"] != "valid":
            issues.append(f"{manifest['skill_name']}: {', '.join(manifest['issues'])}")
    return ("passed" if not issues else "failed", issues)


def check_memory(root: Path, conn) -> tuple[str, List[str]]:
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


def check_runtime(root: Path, conn) -> tuple[str, List[str]]:
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
        "event_bus_messages",
        "runtime_schedule_items",
        "resource_leases",
        "quality_scores",
        "self_audit_findings",
        "benchmark_runs",
    ]
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    existing = {row["name"] for row in rows}
    issues = [f"missing runtime table: {table}" for table in required_tables if table not in existing]
    script_path = root / "scripts" / "agent-runtime.py"
    if not script_path.exists():
        issues.append("missing scripts/agent-runtime.py")
    return ("passed" if not issues else "failed", issues)


def check_bootstrap(root: Path) -> tuple[str, List[str]]:
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


def check_policy_pack_health(root: Path) -> tuple[str, List[str]]:
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


def check_security_health(root: Path) -> tuple[str, List[str]]:
    issues = []
    if not (root / "rules" / "security-hardening.md").exists():
        issues.append("missing rules/security-hardening.md")
    scan = scan_secrets(root, max_files=500)
    if scan["findings"]:
        issues.append(f"secret scan found {len(scan['findings'])} finding(s)")
    return ("passed" if not issues else "failed", issues)


def check_db_writable(db_path: Path, schema_path: Path) -> tuple[str, List[str]]:
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
    checks: list[Dict[str, Any]] = []
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


def read_db_schema_version(db_path: Path, schema_path: Path) -> Optional[str]:
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


def dashboard_rows(conn, query: str, params: tuple[Any, ...]) -> list[Dict[str, Any]]:
    return [row_to_dict(row) for row in conn.execute(query, params).fetchall()]


def build_dashboard_data(conn, project: str, limit: int = 20) -> Dict[str, Any]:
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
        "intents": dashboard_rows(
            conn,
            """
            SELECT id, intent_type, mutation_authorization, current_phase, confidence,
                   risk_level, updated_at
            FROM intent_states
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "actions": dashboard_rows(
            conn,
            """
            SELECT id, intent_id, action_type, tool, status, gate_decision,
                   requires_approval, updated_at
            FROM action_proposals
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "drifts": dashboard_rows(
            conn,
            """
            SELECT id, intent_id, proposal_id, drift_type, severity, status, created_at
            FROM drift_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "feedback": dashboard_rows(
            conn,
            """
            SELECT id, intent_id, proposal_id, confidence_delta, evidence_delta, summary, created_at
            FROM feedback_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "plans": dashboard_rows(
            conn,
            """
            SELECT id, intent_id, version, status, validation, created_at
            FROM plan_versions
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "event_messages": dashboard_rows(
            conn,
            """
            SELECT id, topic, subscriber, status, priority, available_at, delivered_at, acknowledged_at
            FROM event_bus_messages
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "schedule": dashboard_rows(
            conn,
            """
            SELECT id, goal_id, task_id, action_type, assigned_role, status, priority, next_action, updated_at
            FROM runtime_schedule_items
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "resources": dashboard_rows(
            conn,
            """
            SELECT id, schedule_id, resource_type, resource_key, quantity, status, expires_at, updated_at
            FROM resource_leases
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "quality": dashboard_rows(
            conn,
            """
            SELECT id, goal_id, run_id, score, grade, risk_penalty, created_at
            FROM quality_scores
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "self_audit": dashboard_rows(
            conn,
            """
            SELECT id, goal_id, run_id, finding_type, severity, status, summary, updated_at
            FROM self_audit_findings
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "benchmarks": dashboard_rows(
            conn,
            """
            SELECT id, goal_id, run_id, name, metric, current_value, threshold_value, direction, status, created_at
            FROM benchmark_runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (project, limit),
        ),
        "verification": dashboard_rows(
            conn,
            "SELECT id, goal_id, task_id, scope, command, result, failure_type, evidence, created_at FROM verification_runs WHERE project = ? ORDER BY created_at DESC LIMIT ?",
            (project, limit),
        ),
    }


def render_dashboard_table(title: str, rows: list[Dict[str, Any]]) -> str:
    if not rows:
        return f"<section><h2>{html.escape(title)}</h2><p class=\"empty\">暂无记录</p></section>"
    columns = list(rows[0].keys())
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(column) or ''))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return f"<section><h2>{html.escape(title)}</h2><table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></section>"


def render_dashboard_html(data: Dict[str, Any]) -> str:
    sections = [
        render_dashboard_table("目标", data["goals"]),
        render_dashboard_table("运行", data["runs"]),
        render_dashboard_table("任务", data["tasks"]),
        render_dashboard_table("事件", data["events"]),
        render_dashboard_table("意图", data["intents"]),
        render_dashboard_table("动作", data["actions"]),
        render_dashboard_table("漂移", data["drifts"]),
        render_dashboard_table("反馈", data["feedback"]),
        render_dashboard_table("计划版本", data["plans"]),
        render_dashboard_table("事件消息", data["event_messages"]),
        render_dashboard_table("调度", data["schedule"]),
        render_dashboard_table("资源租约", data["resources"]),
        render_dashboard_table("质量评分", data["quality"]),
        render_dashboard_table("自审计", data["self_audit"]),
        render_dashboard_table("基准测试", data["benchmarks"]),
        render_dashboard_table("验证", data["verification"]),
    ]
    summary_cards = "".join(
        f"<div class=\"metric\"><strong>{len(data[key])}</strong><span>{label}</span></div>"
        for key, label in (
            ("goals", "目标"),
            ("runs", "运行"),
            ("tasks", "任务"),
            ("events", "事件"),
            ("intents", "意图"),
            ("actions", "动作"),
            ("drifts", "漂移"),
            ("feedback", "反馈"),
            ("plans", "计划"),
            ("event_messages", "消息"),
            ("schedule", "调度"),
            ("resources", "资源"),
            ("quality", "质量"),
            ("self_audit", "自审"),
            ("benchmarks", "基准"),
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
            "sections": ["goals", "runs", "tasks", "events", "intents", "actions", "drifts", "feedback", "plans", "event_messages", "schedule", "resources", "quality", "self_audit", "benchmarks", "verification"],
            "data_source": data_source if args.inline_data else {"kind": data_source["kind"], "section_counts": data_source["sections"]},
        }
    )


def average(values: list[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def parse_version_parts(version: Optional[str]) -> Tuple[int, ...]:
    if not version:
        return ()
    return tuple(int(part) for part in re.findall(r"\d+", version)[:4])


def compare_versions(current: Optional[str], expected: Optional[str]) -> int:
    current_parts = parse_version_parts(current)
    expected_parts = parse_version_parts(expected)
    max_len = max(len(current_parts), len(expected_parts), 1)
    current_parts = current_parts + (0,) * (max_len - len(current_parts))
    expected_parts = expected_parts + (0,) * (max_len - len(expected_parts))
    if current_parts == expected_parts:
        return 0
    return -1 if current_parts < expected_parts else 1


def sequence_points(rows: list[Dict[str, Any]], field: str) -> list[Dict[str, Any]]:
    ordered = list(reversed(rows))
    points = []
    for index, row in enumerate(ordered, start=1):
        value = row.get(field)
        if value is None:
            continue
        points.append({"index": index, "created_at": row.get("created_at"), "value": value})
    return points


def cluster_failures(snapshots: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    clusters: dict[str, Dict[str, Any]] = {}
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


def dashboard_data_source(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": "vscode-dashboard-data",
        "project": data["project"],
        "generated_at": data["generated_at"],
        "sections": {
            "goals": len(data["goals"]),
            "runs": len(data["runs"]),
            "tasks": len(data["tasks"]),
            "events": len(data["events"]),
            "intents": len(data["intents"]),
            "actions": len(data["actions"]),
            "drifts": len(data["drifts"]),
            "feedback": len(data["feedback"]),
            "plans": len(data["plans"]),
            "event_messages": len(data["event_messages"]),
            "schedule": len(data["schedule"]),
            "resources": len(data["resources"]),
            "quality": len(data["quality"]),
            "self_audit": len(data["self_audit"]),
            "benchmarks": len(data["benchmarks"]),
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


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def compute_quality_score(conn, project: str, goal_id: Optional[str], run_id: Optional[str]) -> Dict[str, Any]:
    goal_clause = " AND goal_id = ?" if goal_id else ""
    run_clause = " AND run_id = ?" if run_id else ""
    goal_params: list[Any] = [project] + ([goal_id] if goal_id else [])
    scoped_params: list[Any] = [project] + ([goal_id] if goal_id else []) + ([run_id] if run_id else [])

    verifications = conn.execute(
        f"SELECT result FROM verification_runs WHERE project = ?{goal_clause}",
        goal_params,
    ).fetchall()
    verification_total = len(verifications)
    verification_passed = sum(1 for row in verifications if row["result"] == "passed")
    verification_failed = sum(1 for row in verifications if row["result"] in {"failed", "blocked"})
    verification_score = 100 if verification_total and verification_failed == 0 else (verification_passed / verification_total * 100 if verification_total else 0)

    action_rows = conn.execute(
        f"SELECT status FROM action_proposals WHERE project = ?{goal_clause}",
        goal_params,
    ).fetchall()
    blocked_actions = sum(1 for row in action_rows if row["status"] in {"blocked", "requires-approval"})
    open_drifts = conn.execute(
        "SELECT COUNT(*) AS count FROM drift_events WHERE project = ? AND status = 'open'",
        (project,),
    ).fetchone()["count"]
    intent_score = max(0, 100 - blocked_actions * 25 - open_drifts * 20)

    schedule_rows = conn.execute(
        f"SELECT status FROM runtime_schedule_items WHERE project = ?{goal_clause}",
        goal_params,
    ).fetchall()
    open_schedule = sum(1 for row in schedule_rows if row["status"] in {"queued", "ready", "running", "blocked"})
    lease_rows = conn.execute(
        f"SELECT status FROM resource_leases WHERE project = ?{goal_clause}",
        goal_params,
    ).fetchall()
    open_leases = sum(1 for row in lease_rows if row["status"] in {"requested", "granted", "denied"})
    schedule_score = max(0, 100 - open_schedule * 20 - open_leases * 20)

    workspace = workspace_snapshot(project)
    docs_freshness = docs_freshness_for_request(project, [], workspace)
    docs_score = 100
    if docs_freshness["missing_docs"]:
        docs_score -= 40
    if docs_freshness["stale_docs"]:
        docs_score -= 30
    if docs_freshness["must_update"]:
        docs_score -= 20
    docs_score = max(0, docs_score)

    recovery_required = bool(conn.execute(
        f"SELECT 1 FROM policy_decisions WHERE project = ?{goal_clause} AND decision_type = 'rollback' AND decision = 'required' LIMIT 1",
        goal_params,
    ).fetchone())
    recovery_ready = bool(conn.execute(
        f"SELECT 1 FROM recovery_points WHERE project = ?{goal_clause} AND (status IN ('available', 'used') OR checkpoint_ref IS NOT NULL) LIMIT 1",
        goal_params,
    ).fetchone())
    recovery_score = 100 if not recovery_required or recovery_ready else 40

    memory_count = conn.execute(
        "SELECT COUNT(*) AS count FROM memory_items WHERE project = ? OR project = '*'",
        (normalize_project_slug(project),),
    ).fetchone()["count"]
    memory_score = 100 if memory_count else 70

    failed_events = conn.execute(
        f"SELECT COUNT(*) AS count FROM event_bus_messages WHERE project = ?{goal_clause} AND status = 'failed'",
        goal_params,
    ).fetchone()["count"]
    failed_benchmarks = conn.execute(
        f"SELECT COUNT(*) AS count FROM benchmark_runs WHERE project = ?{goal_clause} AND status IN ('failed', 'blocked', 'not-run')",
        goal_params,
    ).fetchone()["count"]
    open_audit = conn.execute(
        f"SELECT COUNT(*) AS count FROM self_audit_findings WHERE project = ?{goal_clause}{run_clause} AND status = 'open'",
        scoped_params,
    ).fetchone()["count"]
    risk_penalty = min(40, failed_events * 10 + open_audit * 10 + failed_benchmarks * 10)

    weighted = (
        verification_score * 0.25
        + intent_score * 0.2
        + schedule_score * 0.15
        + docs_score * 0.15
        + recovery_score * 0.15
        + memory_score * 0.1
        - risk_penalty
    )
    score = round(max(0, min(100, weighted)), 2)
    metrics = {
        "verification_total": verification_total,
        "verification_failed": verification_failed,
        "blocked_actions": blocked_actions,
        "open_drifts": open_drifts,
        "open_schedule_items": open_schedule,
        "open_resource_leases": open_leases,
        "failed_event_messages": failed_events,
        "failed_benchmarks": failed_benchmarks,
        "open_self_audit_findings": open_audit,
        "docs_freshness": docs_freshness,
        "recovery_required": recovery_required,
        "recovery_ready": recovery_ready,
        "memory_count": memory_count,
    }
    evidence = (
        f"verification={verification_score:.1f}; intent={intent_score:.1f}; "
        f"schedule={schedule_score:.1f}; docs={docs_score:.1f}; "
        f"recovery={recovery_score:.1f}; memory={memory_score:.1f}; penalty={risk_penalty:.1f}"
    )
    return {
        "score": score,
        "grade": grade_for_score(score),
        "verification_score": round(verification_score, 2),
        "intent_score": round(intent_score, 2),
        "schedule_score": round(schedule_score, 2),
        "docs_score": round(docs_score, 2),
        "recovery_score": round(recovery_score, 2),
        "memory_score": round(memory_score, 2),
        "risk_penalty": round(risk_penalty, 2),
        "evidence": evidence,
        "metrics": metrics,
    }


def cmd_runtime_quality_score(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        result = compute_quality_score(conn, args.project, args.goal_id, args.run_id)
        score_id = None
        if args.record:
            cur = conn.execute(
                """
                INSERT INTO quality_scores(
                    project, goal_id, run_id, score, grade, verification_score,
                    intent_score, schedule_score, docs_score, recovery_score,
                    memory_score, risk_penalty, evidence, metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    result["score"],
                    result["grade"],
                    result["verification_score"],
                    result["intent_score"],
                    result["schedule_score"],
                    result["docs_score"],
                    result["recovery_score"],
                    result["memory_score"],
                    result["risk_penalty"],
                    result["evidence"],
                    json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True),
                ),
            )
            score_id = cur.lastrowid
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                event_type="MetricsRecorded",
                source="runtime-quality-score",
                summary=f"Quality score {result['score']} ({result['grade']}).",
                payload={**result, "score_id": score_id},
                severity="info" if result["score"] >= args.min_score else "warning",
            )
            conn.commit()
    print_json({"ok": result["score"] >= args.min_score, "id": score_id, "project": args.project, **result})


def self_audit_findings_for(conn, project: str, goal_id: Optional[str], run_id: Optional[str]) -> list[Dict[str, Any]]:
    findings: list[Dict[str, Any]] = []
    goal_clause = " AND goal_id = ?" if goal_id else ""
    params: list[Any] = [project] + ([goal_id] if goal_id else [])

    checks = [
        (
            "blocked-action",
            "error",
            "Blocked or approval-pending action proposals remain open.",
            "Resolve blocked proposals, obtain approval, or cancel the proposed mutation.",
            conn.execute(
                f"SELECT COUNT(*) AS count FROM action_proposals WHERE project = ?{goal_clause} AND status IN ('blocked', 'requires-approval')",
                params,
            ).fetchone()["count"],
        ),
        (
            "open-drift",
            "error",
            "Open drift events remain in the intent loop.",
            "Re-anchor with the user, revise the plan, or mark the drift resolved with evidence.",
            conn.execute(
                "SELECT COUNT(*) AS count FROM drift_events WHERE project = ? AND status = 'open'",
                (project,),
            ).fetchone()["count"],
        ),
        (
            "open-scheduler-work",
            "warning",
            "Scheduler queue still has open work.",
            "Complete, block with evidence, or cancel remaining schedule items.",
            conn.execute(
                f"SELECT COUNT(*) AS count FROM runtime_schedule_items WHERE project = ?{goal_clause} AND status IN ('queued', 'ready', 'running', 'blocked')",
                params,
            ).fetchone()["count"],
        ),
        (
            "resource-leak",
            "warning",
            "Resource leases remain unresolved.",
            "Release granted leases and resolve requested or denied leases.",
            conn.execute(
                f"SELECT COUNT(*) AS count FROM resource_leases WHERE project = ?{goal_clause} AND status IN ('requested', 'granted', 'denied')",
                params,
            ).fetchone()["count"],
        ),
        (
            "event-bus-unacked",
            "warning",
            "Event bus messages remain pending, delivered, or failed.",
            "Ack successful messages or record failure handling.",
            conn.execute(
                f"SELECT COUNT(*) AS count FROM event_bus_messages WHERE project = ?{goal_clause} AND status IN ('pending', 'delivered', 'failed')",
                params,
            ).fetchone()["count"],
        ),
        (
            "verification-gap",
            "error",
            "No verification records exist for the scoped work.",
            "Run or record the minimum verification path.",
            0
            if conn.execute(
                f"SELECT 1 FROM verification_runs WHERE project = ?{goal_clause} LIMIT 1",
                params,
            ).fetchone()
            else 1,
        ),
        (
            "benchmark-regression",
            "warning",
            "Benchmark records include failed, blocked, or not-run results.",
            "Re-run benchmark, adjust threshold with evidence, or document the substitute observation.",
            conn.execute(
                f"SELECT COUNT(*) AS count FROM benchmark_runs WHERE project = ?{goal_clause} AND status IN ('failed', 'blocked', 'not-run')",
                params,
            ).fetchone()["count"],
        ),
    ]
    for finding_type, severity, summary, recommendation, count in checks:
        if count:
            findings.append(
                {
                    "finding_type": finding_type,
                    "severity": severity,
                    "summary": summary,
                    "evidence": f"count={count}",
                    "recommendation": recommendation,
                }
            )
    return findings


def cmd_runtime_self_audit(args: argparse.Namespace) -> None:
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        findings = self_audit_findings_for(conn, args.project, args.goal_id, args.run_id)
        ids: list[int] = []
        if args.record:
            for finding in findings:
                cur = conn.execute(
                    """
                    INSERT INTO self_audit_findings(
                        project, goal_id, run_id, finding_type, severity, status,
                        summary, evidence, recommendation
                    )
                    VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        args.project,
                        args.goal_id,
                        args.run_id,
                        finding["finding_type"],
                        finding["severity"],
                        finding["summary"],
                        finding["evidence"],
                        finding["recommendation"],
                    ),
                )
                ids.append(cur.lastrowid)
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                event_type="KernelStep",
                source="runtime-self-audit",
                summary=f"Self-audit found {len(findings)} issue(s).",
                payload={"finding_ids": ids, "findings": findings},
                severity="warning" if findings else "info",
            )
            conn.commit()
    print_json({"ok": not findings, "project": args.project, "finding_ids": ids, "findings": findings})


def benchmark_status(
    *,
    current_value: float,
    baseline_value: Optional[float],
    threshold_value: Optional[float],
    direction: str,
) -> tuple[str, str]:
    comparator = threshold_value if threshold_value is not None else baseline_value
    if comparator is None:
        return "not-run", "missing threshold or baseline"
    if direction == "lower-is-better":
        passed = current_value <= comparator
        return ("passed" if passed else "failed", f"current {current_value} <= limit {comparator}")
    if direction == "higher-is-better":
        passed = current_value >= comparator
        return ("passed" if passed else "failed", f"current {current_value} >= limit {comparator}")
    passed = current_value == comparator
    return ("passed" if passed else "failed", f"current {current_value} == expected {comparator}")


def cmd_runtime_benchmark(args: argparse.Namespace) -> None:
    status, evidence = benchmark_status(
        current_value=args.current_value,
        baseline_value=args.baseline_value,
        threshold_value=args.threshold_value,
        direction=args.direction,
    )
    if args.status:
        status = args.status
    evidence = args.evidence or evidence
    benchmark_id = None
    with connect(args.db) as conn:
        ensure_initialized(conn, args.schema)
        if args.record:
            cur = conn.execute(
                """
                INSERT INTO benchmark_runs(
                    project, goal_id, run_id, name, metric, baseline_value,
                    current_value, threshold_value, direction, unit, status,
                    command, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    args.name,
                    args.metric,
                    args.baseline_value,
                    args.current_value,
                    args.threshold_value,
                    args.direction,
                    args.unit,
                    status,
                    args.command,
                    evidence,
                ),
            )
            benchmark_id = cur.lastrowid
            record_event(
                conn,
                project=args.project,
                goal_id=args.goal_id,
                run_id=args.run_id,
                event_type="MetricsRecorded",
                source="runtime-benchmark",
                summary=f"Benchmark {args.name}/{args.metric} {status}.",
                payload={
                    "benchmark_id": benchmark_id,
                    "name": args.name,
                    "metric": args.metric,
                    "baseline_value": args.baseline_value,
                    "current_value": args.current_value,
                    "threshold_value": args.threshold_value,
                    "direction": args.direction,
                    "status": status,
                    "evidence": evidence,
                },
                severity="info" if status == "passed" else "warning",
            )
            conn.commit()
    print_json(
        {
            "ok": status == "passed",
            "id": benchmark_id,
            "project": args.project,
            "name": args.name,
            "metric": args.metric,
            "baseline_value": args.baseline_value,
            "current_value": args.current_value,
            "threshold_value": args.threshold_value,
            "direction": args.direction,
            "unit": args.unit,
            "status": status,
            "evidence": evidence,
        }
    )


def load_policy_pack(pack_file: Path) -> Dict[str, Any]:
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


def load_policy_state(root: Path) -> Dict[str, Any]:
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


def write_policy_state(root: Path, state: Dict[str, Any]) -> None:
    path = policy_state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def all_policy_packs(packs_dir: Path) -> list[Dict[str, Any]]:
    if not packs_dir.exists():
        return []
    return [load_policy_pack(pack_file) for pack_file in sorted(packs_dir.glob("*/policy-pack.json"))]


def policy_pack_conflicts(packs: list[Dict[str, Any]], enabled: List[str]) -> List[str]:
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


def load_security_ignore_patterns(root: Path) -> List[str]:
    ignore_file = root / ".agent-os-security-ignore"
    if not ignore_file.exists():
        return []
    patterns = []
    for line in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            patterns.append(stripped.replace("\\", "/"))
    return patterns


def is_ignored_security_path(path: Path, root: Path, patterns: List[str]) -> bool:
    rel = path.relative_to(root).as_posix()
    return any(fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns)


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {char: value.count(char) for char in set(value)}
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def high_entropy_findings(line: str) -> list[Dict[str, Any]]:
    findings = []
    for match in HIGH_ENTROPY_VALUE_RE.finditer(line):
        value = match.group(1)
        entropy = shannon_entropy(value)
        if len(value) >= 32 and entropy >= 4.2 and re.search(r"[A-Za-z]", value) and re.search(r"\d", value):
            findings.append({"type": "high_entropy", "entropy": round(entropy, 3), "value_preview": f"{value[:4]}...{value[-4:]}"})
    return findings


def iter_security_scan_files(root: Path, max_files: int, ignore_patterns: Optional[List[str]] = None) -> List[Path]:
    ignore_patterns = ignore_patterns or []
    files: List[Path] = []
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


def scan_secrets(root: Path, max_files: int = 2000) -> Dict[str, Any]:
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


def assess_dangerous_command(command: Optional[str]) -> Dict[str, Any]:
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


def permission_policy_report() -> Dict[str, Any]:
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


def sandbox_strategy_report() -> Dict[str, Any]:
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


def distribution_channels(root: Path) -> list[Dict[str, Any]]:
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


def vscode_integration_protocol(root: Path, project: str) -> Dict[str, Any]:
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


def team_workspace_report(root: Path) -> Dict[str, Any]:
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


def release_checklist(root: Path, db_path: Path, schema_path: Path) -> Dict[str, Any]:
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

    gate_enabled = any(
        (
            args.intent_id,
            args.intent_type,
            args.mutation_authorization,
            args.action_type,
            args.tool,
            args.target_paths,
            args.approved_scope,
            args.confidence is not None,
            args.validation_plan,
            args.user_approved,
            args.risk_level != "normal",
        )
    )
    if gate_enabled:
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            gate_data = action_gate_inputs_from_args(args, conn)

        if not args.target_paths:
            args.target_paths = target or command
            gate_data["target_paths"] = args.target_paths
            gate_data["gate"] = evaluate_action_gate(
                intent_type=gate_data["intent_type"],
                mutation_authorization=gate_data["mutation_authorization"],
                action_type=gate_data["action_type"],
                tool=gate_data["tool"],
                target_paths=args.target_paths,
                approved_scope=gate_data["approved_scope"],
                confidence=gate_data["confidence"],
                risk_level=gate_data["risk_level"],
                user_approved=args.user_approved,
                validation_plan=args.validation_plan,
            )
    else:
        gate_data = {
            "intent_id": None,
            "intent_type": "task",
            "mutation_authorization": "ambiguous",
            "approved_scope": None,
            "confidence": 1.0,
            "risk_level": "normal",
            "action_type": tool_type if tool_type in ACTION_TYPES else "read",
            "tool": tool_key_for_action(
                action_type=tool_type if tool_type in ACTION_TYPES else "read",
                tool=None,
                command=command,
                method=args.method,
                browser_action=args.browser_action,
                allow_unsafe=args.allow_unsafe,
            ),
            "target_paths": args.target_paths,
            "validation_plan": args.validation_plan,
            "gate": {
                "decision": "allowed",
                "allowed_actions": [],
                "blocked_actions": [],
                "tool_actions": [],
                "missing_requirements": [],
                "reason": "no intent gate context supplied; legacy adapter policy applies",
                "scope": {"ok": True, "reason": "not-evaluated"},
                "requires_approval": False,
            },
        }

    if gate_enabled and gate_data["gate"]["decision"] != "allowed":
        result = "blocked"
        stdout_summary = f"Execution gate {gate_data['gate']['decision']}: {gate_data['gate']['reason']}"
        failure_type = "requirement"
        failure_detail = gate_data["gate"]["decision"]
        with connect(args.db) as conn:
            ensure_initialized(conn, args.schema)
            proposal_id = insert_action_proposal(
                conn,
                project=args.project,
                intent_id=args.intent_id,
                goal_id=args.goal_id,
                run_id=args.run_id,
                action_type=gate_data["action_type"],
                tool=gate_data["tool"],
                target_paths=args.target_paths,
                reason=args.evidence or "runtime-run-tool execution request",
                risk_level=gate_data["risk_level"],
                validation_plan=args.validation_plan,
                gate=gate_data["gate"],
            )
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
                exit_code=None,
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
                event_type="ActionBlocked",
                source="runtime-run-tool",
                summary=f"{tool_type} tool blocked by execution gate.",
                payload={**gate_data, "tool_id": tool_id, "proposal_id": proposal_id},
                severity="warning",
            )
            conn.commit()
        print_json(
            {
                "ok": False,
                "id": tool_id,
                "proposal_id": proposal_id,
                "project": args.project,
                "tool_type": tool_type,
                "adapter": adapter,
                "status": result,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "failure_type": failure_type,
                "failure_detail": failure_detail,
                "stdout_summary": stdout_summary,
                "gate": gate_data["gate"],
                "action_type": gate_data["action_type"],
                "tool": gate_data["tool"],
            }
        )
        return

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
            payload={"tool_id": tool_id, "tool_type": tool_type, "adapter": adapter, "status": result, "failure_type": failure_type, "failure_detail": failure_detail, "gate": gate_data["gate"], "action_type": gate_data["action_type"], "tool": gate_data["tool"]},
            severity="info" if result in {"passed", "not-run"} else "error",
        )
        conn.commit()
    print_json({"ok": result == "passed" or result == "not-run", "id": tool_id, "project": args.project, "tool_type": tool_type, "adapter": adapter, "status": result, "exit_code": exit_code, "duration_ms": duration_ms, "failure_type": failure_type, "failure_detail": failure_detail, "stdout_summary": stdout_summary, "gate": gate_data["gate"], "action_type": gate_data["action_type"], "tool": gate_data["tool"]})


def classify_root_cause(source_type: str, failure_type: Optional[str], failure_detail: Optional[str], summary: str) -> str:
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
    evidence: Optional[str],
    goal_id: Optional[str] = None,
    run_id: Optional[str] = None,
    failure_type: Optional[str] = None,
    failure_detail: Optional[str] = None,
    pattern: Optional[str] = None,
    next_step: Optional[str] = None,
    confidence: float = 0.7,
) -> Dict[str, Any]:
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


def record_reflection(conn, reflection: Dict[str, Any]) -> int:
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


def reflection_to_memory_item(reflection: Dict[str, Any]) -> Dict[str, Any]:
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


def reflection_to_candidate(reflection: Dict[str, Any], memory_item_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
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


def learn_from_reflection(conn, reflection: Dict[str, Any]) -> Dict[str, Any]:
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
    goal_id: Optional[str],
    run_id: Optional[str],
    scope: Optional[str],
    result: str,
    failure_type: Optional[str],
    failure_detail: Optional[str],
    stdout_summary: Optional[str],
    command: Optional[str],
) -> Optional[Dict[str, Any]]:
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
        intent_clause = " AND goal_id = ?" if goal_id else ""
        intent_params: list[Any] = [args.project] + ([goal_id] if goal_id else [])
        intents = conn.execute(
            f"SELECT * FROM intent_states WHERE project = ?{intent_clause} ORDER BY updated_at",
            intent_params,
        ).fetchall()
        action_proposals = conn.execute(
            f"SELECT * FROM action_proposals WHERE project = ?{intent_clause} ORDER BY updated_at",
            intent_params,
        ).fetchall()
        intent_ids = [row["id"] for row in intents]
        if goal_id or args.run_id:
            if intent_ids:
                placeholders = ",".join("?" for _ in intent_ids)
                open_drifts = conn.execute(
                    f"""
                    SELECT *
                    FROM drift_events
                    WHERE project = ? AND status = 'open'
                      AND (intent_id IN ({placeholders}) OR intent_id IS NULL)
                    ORDER BY created_at
                    """,
                    [args.project, *intent_ids],
                ).fetchall()
            else:
                open_drifts = []
        else:
            open_drifts = conn.execute(
                """
                SELECT *
                FROM drift_events
                WHERE project = ? AND status = 'open'
                ORDER BY created_at
                """,
                (args.project,),
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
        event_messages = conn.execute(
            f"""
            SELECT *
            FROM event_bus_messages
            WHERE project = ?{goal_clause}
              AND status IN ('pending', 'delivered', 'failed')
            ORDER BY created_at
            """,
            goal_params,
        ).fetchall()
        schedule_items = conn.execute(
            f"""
            SELECT *
            FROM runtime_schedule_items
            WHERE project = ?{goal_clause}
              AND status IN ('queued', 'ready', 'running', 'blocked')
            ORDER BY priority DESC, created_at
            """,
            goal_params,
        ).fetchall()
        resource_leases = conn.execute(
            f"""
            SELECT *
            FROM resource_leases
            WHERE project = ?{goal_clause}
              AND status IN ('requested', 'granted', 'denied')
            ORDER BY created_at
            """,
            goal_params,
        ).fetchall()
        open_self_audit = conn.execute(
            f"""
            SELECT *
            FROM self_audit_findings
            WHERE project = ?{goal_clause}
              AND status = 'open'
            ORDER BY severity DESC, created_at
            """,
            goal_params,
        ).fetchall()
        latest_quality = conn.execute(
            f"""
            SELECT *
            FROM quality_scores
            WHERE project = ?{goal_clause}
            ORDER BY created_at DESC
            LIMIT 1
            """,
            goal_params,
        ).fetchone()
        bad_benchmarks = conn.execute(
            f"""
            SELECT *
            FROM benchmark_runs
            WHERE project = ?{goal_clause}
              AND status IN ('failed', 'blocked', 'not-run')
            ORDER BY created_at
            """,
            goal_params,
        ).fetchall()
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
    missing: List[str] = []
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
    if any(row["status"] == "requires-approval" for row in action_proposals):
        missing.append("action approval pending")
    if any(row["status"] == "blocked" for row in action_proposals):
        missing.append("blocked action proposal")
    if open_drifts:
        missing.append("open drift events")
    if any(row["status"] in {"pending", "delivered"} for row in event_messages):
        missing.append("unacknowledged event messages")
    if any(row["status"] == "failed" for row in event_messages):
        missing.append("failed event messages")
    if schedule_items:
        missing.append("open schedule items")
    if any(row["status"] in {"requested", "denied"} for row in resource_leases):
        missing.append("resource lease unresolved")
    if any(row["status"] == "granted" for row in resource_leases):
        missing.append("resource lease not released")
    if open_self_audit:
        missing.append("open self-audit findings")
    if latest_quality and latest_quality["score"] < 70:
        missing.append("quality score below threshold")
    if bad_benchmarks:
        missing.append("benchmark regression")
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
            "intents": [row_to_dict(row) for row in intents],
            "action_proposals": [row_to_dict(row) for row in action_proposals],
            "open_drifts": [row_to_dict(row) for row in open_drifts],
            "event_messages": [row_to_dict(row) for row in event_messages],
            "schedule_items": [row_to_dict(row) for row in schedule_items],
            "resource_leases": [row_to_dict(row) for row in resource_leases],
            "open_self_audit_findings": [row_to_dict(row) for row in open_self_audit],
            "latest_quality_score": row_to_dict(latest_quality) if latest_quality else None,
            "bad_benchmarks": [row_to_dict(row) for row in bad_benchmarks],
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
        intents = scoped_rows(conn, "intent_states", args.project, goal_id, args.run_id, "updated_at")
        action_proposals = scoped_rows(conn, "action_proposals", args.project, goal_id, args.run_id, "updated_at")
        feedback = scoped_intent_rows(conn, "feedback_events", args.project, goal_id, args.run_id)
        drifts = scoped_intent_rows(conn, "drift_events", args.project, goal_id, args.run_id)
        plan_versions = scoped_intent_rows(conn, "plan_versions", args.project, goal_id, args.run_id)
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
            "intents": intents,
            "action_proposals": action_proposals,
            "feedback": feedback,
            "drifts": drifts,
            "plan_versions": plan_versions,
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

    memory_hits: List[str] = []
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
    visible_plan = visible_plan_for_tasks(tasks, context, capability_status=capability_status)
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
            "visible_plan": visible_plan,
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
    visible_plan = visible_plan_for_tasks(tasks, context, capability_status=capability_status)
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
        skill_blockers: List[str] = []
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
            "visible_plan": visible_plan,
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

        elif args.kind == "intent":
            runtime_id = args.id or f"intent-{uuid.uuid4().hex[:8]}"
            intent_type = args.intent_type or "task"
            mutation_authorization = args.mutation_authorization or "ambiguous"
            allowed_actions = normalize_csv(args.allowed_actions)
            blocked_actions = normalize_csv(args.blocked_actions)
            if allowed_actions is None and blocked_actions is None:
                allowed, blocked = actions_for_intent(intent_type, mutation_authorization)
                allowed_actions = normalize_csv(allowed)
                blocked_actions = normalize_csv(blocked)
            conn.execute(
                """
                INSERT INTO intent_states(
                    id, project, goal_id, run_id, original_request, intent_type,
                    mutation_authorization, approved_scope, current_phase, confidence,
                    risk_level, allowed_actions, blocked_actions, explanation_required, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    project = excluded.project,
                    goal_id = excluded.goal_id,
                    run_id = excluded.run_id,
                    original_request = excluded.original_request,
                    intent_type = excluded.intent_type,
                    mutation_authorization = excluded.mutation_authorization,
                    approved_scope = excluded.approved_scope,
                    current_phase = excluded.current_phase,
                    confidence = excluded.confidence,
                    risk_level = excluded.risk_level,
                    allowed_actions = excluded.allowed_actions,
                    blocked_actions = excluded.blocked_actions,
                    explanation_required = excluded.explanation_required,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    args.goal_id,
                    args.run_id,
                    args.request or require_arg(args, "summary"),
                    intent_type,
                    mutation_authorization,
                    args.approved_scope,
                    args.current_phase or "parsed",
                    args.confidence if args.confidence is not None else 0.5,
                    args.risk_level,
                    allowed_actions,
                    blocked_actions,
                    int(args.explanation_required),
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "action-proposal":
            runtime_id = args.id or f"action-{uuid.uuid4().hex[:8]}"
            status = args.status or "proposed"
            conn.execute(
                """
                INSERT INTO action_proposals(
                    id, project, intent_id, goal_id, run_id, action_type, tool,
                    target_paths, reason, risk_level, status, gate_decision,
                    gate_reason, requires_approval, validation_plan
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    intent_id = excluded.intent_id,
                    goal_id = excluded.goal_id,
                    run_id = excluded.run_id,
                    action_type = excluded.action_type,
                    tool = excluded.tool,
                    target_paths = excluded.target_paths,
                    reason = excluded.reason,
                    risk_level = excluded.risk_level,
                    status = excluded.status,
                    gate_decision = excluded.gate_decision,
                    gate_reason = excluded.gate_reason,
                    requires_approval = excluded.requires_approval,
                    validation_plan = excluded.validation_plan,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    args.intent_id,
                    args.goal_id,
                    args.run_id,
                    require_arg(args, "action_type"),
                    require_arg(args, "tool"),
                    args.target_paths,
                    require_arg(args, "reason"),
                    args.risk_level,
                    status,
                    args.gate_decision,
                    args.gate_reason,
                    int(args.requires_approval),
                    args.validation_plan,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "approval":
            cur = conn.execute(
                """
                INSERT INTO approval_records(
                    project, intent_id, proposal_id, approved_by_user_text, approved_scope, expires_when
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.intent_id,
                    args.proposal_id,
                    require_arg(args, "approved_text"),
                    args.approved_scope,
                    args.expires_when,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "feedback":
            cur = conn.execute(
                """
                INSERT INTO feedback_events(
                    project, intent_id, proposal_id, observation_id, confidence_delta,
                    risk_delta, scope_delta, evidence_delta, summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.intent_id,
                    args.proposal_id,
                    args.observation_id,
                    args.confidence_delta,
                    args.risk_delta,
                    args.scope_delta,
                    args.evidence_delta,
                    require_arg(args, "summary"),
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "drift":
            status = args.status or "open"
            cur = conn.execute(
                """
                INSERT INTO drift_events(
                    project, intent_id, proposal_id, feedback_id, drift_type,
                    severity, expected, actual, resolution, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.intent_id,
                    args.proposal_id,
                    args.feedback_id,
                    require_arg(args, "drift_type"),
                    args.severity,
                    require_arg(args, "expected"),
                    require_arg(args, "actual"),
                    args.resolution or "re-anchor-required",
                    status,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "plan-version":
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM plan_versions WHERE project = ? AND intent_id IS ?",
                (args.project, args.intent_id),
            ).fetchone()
            version = args.version if args.version is not None else int(row["version"])
            status = args.status or "draft"
            cur = conn.execute(
                """
                INSERT INTO plan_versions(
                    project, intent_id, version, assumptions, steps, validation, rollback, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(intent_id, version) DO UPDATE SET
                    assumptions = excluded.assumptions,
                    steps = excluded.steps,
                    validation = excluded.validation,
                    rollback = excluded.rollback,
                    status = excluded.status
                """,
                (
                    args.project,
                    args.intent_id,
                    version,
                    args.assumptions,
                    require_arg(args, "steps"),
                    args.validation,
                    args.rollback,
                    status,
                ),
            )
            result = {
                "ok": True,
                "kind": args.kind,
                "id": cur.lastrowid,
                "project": args.project,
                "version": version,
            }

        elif args.kind == "event-message":
            runtime_id = args.id or f"event-msg-{uuid.uuid4().hex[:8]}"
            status = args.status or "pending"
            payload = {}
            if args.payload_json:
                try:
                    payload = json.loads(args.payload_json)
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"Invalid --payload-json: {exc}") from exc
            conn.execute(
                """
                INSERT INTO event_bus_messages(
                    id, project, run_id, goal_id, task_id, topic, subscriber,
                    status, priority, payload_json, available_at, failure_detail
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    goal_id = excluded.goal_id,
                    task_id = excluded.task_id,
                    topic = excluded.topic,
                    subscriber = excluded.subscriber,
                    status = excluded.status,
                    priority = excluded.priority,
                    payload_json = excluded.payload_json,
                    available_at = excluded.available_at,
                    failure_detail = excluded.failure_detail,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    args.run_id,
                    args.goal_id,
                    args.task_id,
                    require_arg(args, "topic"),
                    args.subscriber,
                    status,
                    args.queue_priority,
                    json.dumps(payload, ensure_ascii=False),
                    args.available_at,
                    args.failure_detail,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "schedule-item":
            runtime_id = args.id or f"schedule-{uuid.uuid4().hex[:8]}"
            status = args.status or "queued"
            conn.execute(
                """
                INSERT INTO runtime_schedule_items(
                    id, project, run_id, goal_id, task_id, intent_id, action_type,
                    assigned_role, status, priority, depends_on, required_resources,
                    schedule_reason, next_action, available_at, blocker, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    goal_id = excluded.goal_id,
                    task_id = excluded.task_id,
                    intent_id = excluded.intent_id,
                    action_type = excluded.action_type,
                    assigned_role = excluded.assigned_role,
                    status = excluded.status,
                    priority = excluded.priority,
                    depends_on = excluded.depends_on,
                    required_resources = excluded.required_resources,
                    schedule_reason = excluded.schedule_reason,
                    next_action = excluded.next_action,
                    available_at = excluded.available_at,
                    blocker = excluded.blocker,
                    evidence = excluded.evidence,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    args.run_id,
                    args.goal_id,
                    args.task_id,
                    args.intent_id,
                    require_arg(args, "action_type"),
                    args.assigned_role,
                    status,
                    args.queue_priority,
                    args.depends_on,
                    args.required_resources,
                    args.reason,
                    args.next_action,
                    args.available_at,
                    args.blocker,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "resource-lease":
            runtime_id = args.id or f"lease-{uuid.uuid4().hex[:8]}"
            status = args.status or "requested"
            conn.execute(
                """
                INSERT INTO resource_leases(
                    id, project, run_id, goal_id, task_id, schedule_id, resource_type,
                    resource_key, quantity, status, reason, expires_at,
                    granted_at, released_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CASE WHEN ? = 'granted' THEN datetime('now') ELSE NULL END,
                    CASE WHEN ? = 'released' THEN datetime('now') ELSE NULL END
                )
                ON CONFLICT(id) DO UPDATE SET
                    run_id = excluded.run_id,
                    goal_id = excluded.goal_id,
                    task_id = excluded.task_id,
                    schedule_id = excluded.schedule_id,
                    resource_type = excluded.resource_type,
                    resource_key = excluded.resource_key,
                    quantity = excluded.quantity,
                    status = excluded.status,
                    reason = excluded.reason,
                    expires_at = excluded.expires_at,
                    granted_at = excluded.granted_at,
                    released_at = excluded.released_at,
                    updated_at = datetime('now')
                """,
                (
                    runtime_id,
                    args.project,
                    args.run_id,
                    args.goal_id,
                    args.task_id,
                    args.schedule_id,
                    require_arg(args, "resource_type"),
                    require_arg(args, "resource_key"),
                    args.quantity,
                    status,
                    args.reason,
                    args.expires_at,
                    status,
                    status,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": runtime_id, "project": args.project}

        elif args.kind == "quality-score":
            cur = conn.execute(
                """
                INSERT INTO quality_scores(
                    project, goal_id, run_id, score, grade, verification_score,
                    intent_score, schedule_score, docs_score, recovery_score,
                    memory_score, risk_penalty, evidence, metrics_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    require_arg(args, "score"),
                    require_arg(args, "grade"),
                    args.verification_score,
                    args.intent_score,
                    args.schedule_score,
                    args.docs_score,
                    args.recovery_score,
                    args.memory_score,
                    args.risk_penalty,
                    args.evidence,
                    args.payload_json,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "self-audit-finding":
            status = args.status or "open"
            cur = conn.execute(
                """
                INSERT INTO self_audit_findings(
                    project, goal_id, run_id, finding_type, severity, status,
                    summary, evidence, recommendation
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    require_arg(args, "finding_type"),
                    args.severity,
                    status,
                    require_arg(args, "summary"),
                    args.evidence,
                    args.recommendation,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

        elif args.kind == "benchmark":
            status = args.status or "not-run"
            cur = conn.execute(
                """
                INSERT INTO benchmark_runs(
                    project, goal_id, run_id, name, metric, baseline_value,
                    current_value, threshold_value, direction, unit, status,
                    command, evidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    args.project,
                    args.goal_id,
                    args.run_id,
                    require_arg(args, "name"),
                    require_arg(args, "metric"),
                    args.baseline_value,
                    require_arg(args, "current_value"),
                    args.threshold_value,
                    args.direction,
                    args.unit,
                    status,
                    args.command,
                    args.evidence,
                ),
            )
            result = {"ok": True, "kind": args.kind, "id": cur.lastrowid, "project": args.project}

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
        "intent": ("intent_states", "updated_at"),
        "action-proposal": ("action_proposals", "updated_at"),
        "feedback": ("feedback_events", "created_at"),
        "drift": ("drift_events", "created_at"),
        "approval": ("approval_records", "created_at"),
        "plan-version": ("plan_versions", "created_at"),
        "event-message": ("event_bus_messages", "created_at"),
        "schedule-item": ("runtime_schedule_items", "created_at"),
        "resource-lease": ("resource_leases", "created_at"),
        "quality-score": ("quality_scores", "created_at"),
        "self-audit-finding": ("self_audit_findings", "updated_at"),
        "benchmark": ("benchmark_runs", "created_at"),
    }
    table, order_column = table_by_kind[args.kind]
    where = ["project = ?"]
    params: list[Any] = [args.project]

    status_columns = {
        "goal": "status",
        "task": "status",
        "capability": "status",
        "recovery": "status",
        "improvement": "status",
        "tool": "status",
        "skill": "status",
        "model": "status",
        "subagent": "status",
        "adapter": "status",
        "intent": "current_phase",
        "action-proposal": "status",
        "drift": "status",
        "plan-version": "status",
        "event-message": "status",
        "schedule-item": "status",
        "resource-lease": "status",
        "self-audit-finding": "status",
        "benchmark": "status",
    }
    if args.status and args.kind in status_columns:
        status_column = status_columns[args.kind]
        where.append(f"{status_column} = ?")
        params.append(args.status)
    if args.goal_id and args.kind in {"task", "observation", "policy", "verification", "tool", "skill", "model", "subagent", "metrics", "recovery", "event", "intent", "action-proposal", "event-message", "schedule-item", "resource-lease", "quality-score", "self-audit-finding", "benchmark"}:
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
        recent_intents = conn.execute(
            """
            SELECT id, intent_type, mutation_authorization, current_phase, confidence, risk_level, updated_at
            FROM intent_states
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_action_proposals = conn.execute(
            """
            SELECT id, intent_id, action_type, tool, status, gate_decision, requires_approval, updated_at
            FROM action_proposals
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_feedback = conn.execute(
            """
            SELECT id, intent_id, proposal_id, confidence_delta, evidence_delta, summary, created_at
            FROM feedback_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_drifts = conn.execute(
            """
            SELECT id, intent_id, proposal_id, drift_type, severity, status, created_at
            FROM drift_events
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_plan_versions = conn.execute(
            """
            SELECT id, intent_id, version, status, validation, created_at
            FROM plan_versions
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_event_messages = conn.execute(
            """
            SELECT id, topic, subscriber, status, priority, available_at, updated_at
            FROM event_bus_messages
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_schedule_items = conn.execute(
            """
            SELECT id, goal_id, task_id, action_type, assigned_role, status, priority, next_action, updated_at
            FROM runtime_schedule_items
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_resource_leases = conn.execute(
            """
            SELECT id, schedule_id, resource_type, resource_key, quantity, status, expires_at, updated_at
            FROM resource_leases
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_quality_scores = conn.execute(
            """
            SELECT id, goal_id, run_id, score, grade, risk_penalty, created_at
            FROM quality_scores
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_self_audit_findings = conn.execute(
            """
            SELECT id, goal_id, run_id, finding_type, severity, status, summary, updated_at
            FROM self_audit_findings
            WHERE project = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (args.project, args.limit),
        ).fetchall()
        recent_benchmarks = conn.execute(
            """
            SELECT id, goal_id, run_id, name, metric, current_value, threshold_value, direction, status, created_at
            FROM benchmark_runs
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
            "recent_intents": [row_to_dict(row) for row in recent_intents],
            "recent_action_proposals": [row_to_dict(row) for row in recent_action_proposals],
            "recent_feedback": [row_to_dict(row) for row in recent_feedback],
            "recent_drifts": [row_to_dict(row) for row in recent_drifts],
            "recent_plan_versions": [row_to_dict(row) for row in recent_plan_versions],
            "recent_event_messages": [row_to_dict(row) for row in recent_event_messages],
            "recent_schedule_items": [row_to_dict(row) for row in recent_schedule_items],
            "recent_resource_leases": [row_to_dict(row) for row in recent_resource_leases],
            "recent_quality_scores": [row_to_dict(row) for row in recent_quality_scores],
            "recent_self_audit_findings": [row_to_dict(row) for row in recent_self_audit_findings],
            "recent_benchmarks": [row_to_dict(row) for row in recent_benchmarks],
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

    compile_mission_parser = subparsers.add_parser("runtime-compile-mission", help="Compile a user request into locked Mission IR")
    add_common_args(compile_mission_parser)
    compile_mission_parser.add_argument("--project")
    compile_mission_parser.add_argument("--request", required=True)
    compile_mission_parser.add_argument("--files", nargs="*")
    compile_mission_parser.add_argument("--provider", default="builtin")
    compile_mission_parser.add_argument("--base-url")
    compile_mission_parser.add_argument("--api-key")
    compile_mission_parser.add_argument("--model")
    compile_mission_parser.add_argument("--llm-response")
    compile_mission_parser.add_argument("--timeout", type=int, default=60)
    compile_mission_parser.add_argument("--no-fallback", action="store_true")
    compile_mission_parser.set_defaults(func=cmd_runtime_compile_mission)

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

    publish_event_parser = subparsers.add_parser("runtime-publish-event", help="Publish a message to the Agent OS event bus")
    add_common_args(publish_event_parser)
    publish_event_parser.add_argument("--project", required=True)
    publish_event_parser.add_argument("--id")
    publish_event_parser.add_argument("--run-id")
    publish_event_parser.add_argument("--goal-id")
    publish_event_parser.add_argument("--task-id")
    publish_event_parser.add_argument("--topic", required=True)
    publish_event_parser.add_argument("--subscriber", default="*")
    publish_event_parser.add_argument("--event-type", choices=EVENT_TYPES)
    publish_event_parser.add_argument("--source")
    publish_event_parser.add_argument("--summary", required=True)
    publish_event_parser.add_argument("--payload-json")
    publish_event_parser.add_argument("--priority", type=int, default=0)
    publish_event_parser.add_argument("--available-at")
    publish_event_parser.add_argument("--severity", choices=("info", "warning", "error", "critical"), default="info")
    publish_event_parser.set_defaults(func=cmd_runtime_publish_event)

    poll_events_parser = subparsers.add_parser("runtime-poll-events", help="Poll pending Agent OS event bus messages")
    add_common_args(poll_events_parser)
    poll_events_parser.add_argument("--project", required=True)
    poll_events_parser.add_argument("--subscriber", required=True)
    poll_events_parser.add_argument("--topic")
    poll_events_parser.add_argument("--limit", type=int, default=10)
    poll_events_parser.add_argument("--deliver", action="store_true")
    poll_events_parser.set_defaults(func=cmd_runtime_poll_events)

    ack_event_parser = subparsers.add_parser("runtime-ack-event", help="Acknowledge or fail an Agent OS event bus message")
    add_common_args(ack_event_parser)
    ack_event_parser.add_argument("--project", required=True)
    ack_event_parser.add_argument("--id", required=True)
    ack_event_parser.add_argument("--ok", action="store_true")
    ack_event_parser.add_argument("--failure-detail")
    ack_event_parser.set_defaults(func=cmd_runtime_ack_event)

    intent_parser = subparsers.add_parser("runtime-detect-intent", help="Detect and optionally record structured intent state")
    add_common_args(intent_parser)
    intent_parser.add_argument("--project")
    intent_parser.add_argument("--goal-id")
    intent_parser.add_argument("--run-id")
    intent_parser.add_argument("--intent-id")
    intent_parser.add_argument("--request", required=True)
    intent_parser.add_argument("--files", nargs="*")
    intent_parser.add_argument("--provider", default="builtin")
    intent_parser.add_argument("--base-url")
    intent_parser.add_argument("--api-key")
    intent_parser.add_argument("--model")
    intent_parser.add_argument("--llm-response")
    intent_parser.add_argument("--timeout", type=int, default=60)
    intent_parser.add_argument("--no-fallback", action="store_true")
    intent_parser.add_argument("--record", action="store_true")
    intent_parser.set_defaults(func=cmd_runtime_detect_intent)

    registry_parser = subparsers.add_parser("runtime-tool-registry", help="List runtime tool action classifications")
    add_common_args(registry_parser)
    registry_parser.add_argument("--action", choices=ACTION_TYPES)
    registry_parser.add_argument("--write-only", action="store_true")
    registry_parser.set_defaults(func=cmd_runtime_tool_registry)

    validate_action_parser = subparsers.add_parser("runtime-validate-action", help="Evaluate the execution gate for an action")
    add_common_args(validate_action_parser)
    validate_action_parser.add_argument("--project", required=True)
    validate_action_parser.add_argument("--goal-id")
    validate_action_parser.add_argument("--run-id")
    validate_action_parser.add_argument("--intent-id")
    validate_action_parser.add_argument("--intent-type", choices=INTENT_TYPES)
    validate_action_parser.add_argument("--mutation-authorization", choices=MUTATION_AUTHORIZATIONS)
    validate_action_parser.add_argument("--action-type", choices=ACTION_TYPES)
    validate_action_parser.add_argument("--tool")
    validate_action_parser.add_argument("--tool-type", choices=("shell", "git", "api", "browser"))
    validate_action_parser.add_argument("--command")
    validate_action_parser.add_argument("--target")
    validate_action_parser.add_argument("--method", default="GET")
    validate_action_parser.add_argument("--browser-action", choices=("open", "check-text", "click", "type", "screenshot"), default="check-text")
    validate_action_parser.add_argument("--target-paths")
    validate_action_parser.add_argument("--approved-scope")
    validate_action_parser.add_argument("--confidence", type=float)
    validate_action_parser.add_argument("--risk-level", choices=("low", "normal", "high", "critical"), default="normal")
    validate_action_parser.add_argument("--validation-plan")
    validate_action_parser.add_argument("--user-approved", action="store_true")
    validate_action_parser.add_argument("--allow-unsafe", action="store_true")
    validate_action_parser.add_argument("--record", action="store_true")
    validate_action_parser.set_defaults(func=cmd_runtime_validate_action)

    propose_action_parser = subparsers.add_parser("runtime-propose-action", help="Create an action proposal and run the execution gate")
    add_common_args(propose_action_parser)
    propose_action_parser.add_argument("--id")
    propose_action_parser.add_argument("--project", required=True)
    propose_action_parser.add_argument("--goal-id")
    propose_action_parser.add_argument("--run-id")
    propose_action_parser.add_argument("--intent-id")
    propose_action_parser.add_argument("--intent-type", choices=INTENT_TYPES)
    propose_action_parser.add_argument("--mutation-authorization", choices=MUTATION_AUTHORIZATIONS)
    propose_action_parser.add_argument("--action-type", choices=ACTION_TYPES)
    propose_action_parser.add_argument("--tool")
    propose_action_parser.add_argument("--tool-type", choices=("shell", "git", "api", "browser"))
    propose_action_parser.add_argument("--command")
    propose_action_parser.add_argument("--target")
    propose_action_parser.add_argument("--method", default="GET")
    propose_action_parser.add_argument("--browser-action", choices=("open", "check-text", "click", "type", "screenshot"), default="check-text")
    propose_action_parser.add_argument("--target-paths")
    propose_action_parser.add_argument("--approved-scope")
    propose_action_parser.add_argument("--confidence", type=float)
    propose_action_parser.add_argument("--risk-level", choices=("low", "normal", "high", "critical"), default="normal")
    propose_action_parser.add_argument("--validation-plan")
    propose_action_parser.add_argument("--user-approved", action="store_true")
    propose_action_parser.add_argument("--allow-unsafe", action="store_true")
    propose_action_parser.add_argument("--reason", required=True)
    propose_action_parser.set_defaults(func=cmd_runtime_propose_action)

    execution_gate_parser = subparsers.add_parser("runtime-execution-gate", help="Re-evaluate a proposal or action before execution")
    add_common_args(execution_gate_parser)
    execution_gate_parser.add_argument("--project", required=True)
    execution_gate_parser.add_argument("--goal-id")
    execution_gate_parser.add_argument("--run-id")
    execution_gate_parser.add_argument("--proposal-id")
    execution_gate_parser.add_argument("--intent-id")
    execution_gate_parser.add_argument("--intent-type", choices=INTENT_TYPES)
    execution_gate_parser.add_argument("--mutation-authorization", choices=MUTATION_AUTHORIZATIONS)
    execution_gate_parser.add_argument("--action-type", choices=ACTION_TYPES)
    execution_gate_parser.add_argument("--tool")
    execution_gate_parser.add_argument("--tool-type", choices=("shell", "git", "api", "browser"))
    execution_gate_parser.add_argument("--command")
    execution_gate_parser.add_argument("--target")
    execution_gate_parser.add_argument("--method", default="GET")
    execution_gate_parser.add_argument("--browser-action", choices=("open", "check-text", "click", "type", "screenshot"), default="check-text")
    execution_gate_parser.add_argument("--target-paths")
    execution_gate_parser.add_argument("--approved-scope")
    execution_gate_parser.add_argument("--confidence", type=float)
    execution_gate_parser.add_argument("--risk-level", choices=("low", "normal", "high", "critical"))
    execution_gate_parser.add_argument("--validation-plan")
    execution_gate_parser.add_argument("--user-approved", action="store_true")
    execution_gate_parser.add_argument("--allow-unsafe", action="store_true")
    execution_gate_parser.add_argument("--record", action="store_true")
    execution_gate_parser.set_defaults(func=cmd_runtime_execution_gate)

    approve_action_parser = subparsers.add_parser("runtime-approve-action", help="Record user approval for a proposal or intent")
    add_common_args(approve_action_parser)
    approve_action_parser.add_argument("--project", required=True)
    approve_action_parser.add_argument("--goal-id")
    approve_action_parser.add_argument("--run-id")
    approve_action_parser.add_argument("--intent-id")
    approve_action_parser.add_argument("--proposal-id")
    approve_action_parser.add_argument("--approved-text", required=True)
    approve_action_parser.add_argument("--approved-scope")
    approve_action_parser.add_argument("--expires-when")
    approve_action_parser.set_defaults(func=cmd_runtime_approve_action)

    feedback_parser = subparsers.add_parser("runtime-record-feedback", help="Record execution feedback into the intent loop")
    add_common_args(feedback_parser)
    feedback_parser.add_argument("--project", required=True)
    feedback_parser.add_argument("--goal-id")
    feedback_parser.add_argument("--run-id")
    feedback_parser.add_argument("--intent-id")
    feedback_parser.add_argument("--proposal-id")
    feedback_parser.add_argument("--observation-id", type=int)
    feedback_parser.add_argument("--confidence-delta", type=float, default=0)
    feedback_parser.add_argument("--risk-delta", choices=("none", "increased", "decreased"), default="none")
    feedback_parser.add_argument("--scope-delta", choices=("none", "expanded", "narrowed", "changed"), default="none")
    feedback_parser.add_argument("--evidence-delta", choices=("none", "supports", "contradicts", "new-evidence"), default="none")
    feedback_parser.add_argument("--summary", required=True)
    feedback_parser.set_defaults(func=cmd_runtime_record_feedback)

    drift_parser = subparsers.add_parser("runtime-detect-drift", help="Detect execution drift from intent, proposal, or actual action")
    add_common_args(drift_parser)
    drift_parser.add_argument("--project", required=True)
    drift_parser.add_argument("--goal-id")
    drift_parser.add_argument("--run-id")
    drift_parser.add_argument("--intent-id")
    drift_parser.add_argument("--proposal-id")
    drift_parser.add_argument("--feedback-id", type=int)
    drift_parser.add_argument("--actual-action", choices=ACTION_TYPES)
    drift_parser.add_argument("--actual-tool")
    drift_parser.add_argument("--actual-scope")
    drift_parser.add_argument("--confidence", type=float)
    drift_parser.add_argument("--resolution", default="re-anchor-required")
    drift_parser.add_argument("--record", action="store_true")
    drift_parser.set_defaults(func=cmd_runtime_detect_drift)

    reanchor_parser = subparsers.add_parser("runtime-reanchor", help="Request user re-anchor after drift or uncertainty")
    add_common_args(reanchor_parser)
    reanchor_parser.add_argument("--project", required=True)
    reanchor_parser.add_argument("--goal-id")
    reanchor_parser.add_argument("--run-id")
    reanchor_parser.add_argument("--intent-id", required=True)
    reanchor_parser.add_argument("--prompt")
    reanchor_parser.set_defaults(func=cmd_runtime_reanchor)

    revise_plan_parser = subparsers.add_parser("runtime-revise-plan", help="Record a revised execution plan version")
    add_common_args(revise_plan_parser)
    revise_plan_parser.add_argument("--project", required=True)
    revise_plan_parser.add_argument("--goal-id")
    revise_plan_parser.add_argument("--run-id")
    revise_plan_parser.add_argument("--intent-id")
    revise_plan_parser.add_argument("--version", type=int)
    revise_plan_parser.add_argument("--assumptions")
    revise_plan_parser.add_argument("--steps", required=True)
    revise_plan_parser.add_argument("--validation")
    revise_plan_parser.add_argument("--rollback")
    revise_plan_parser.add_argument("--status", choices=("draft", "active", "superseded", "completed"), default="draft")
    revise_plan_parser.set_defaults(func=cmd_runtime_revise_plan)

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
    run_tool_parser.add_argument("--tool")
    run_tool_parser.add_argument("--intent-id")
    run_tool_parser.add_argument("--intent-type", choices=INTENT_TYPES)
    run_tool_parser.add_argument("--mutation-authorization", choices=MUTATION_AUTHORIZATIONS)
    run_tool_parser.add_argument("--action-type", choices=ACTION_TYPES)
    run_tool_parser.add_argument("--target-paths")
    run_tool_parser.add_argument("--approved-scope")
    run_tool_parser.add_argument("--confidence", type=float)
    run_tool_parser.add_argument("--risk-level", choices=("low", "normal", "high", "critical"), default="normal")
    run_tool_parser.add_argument("--validation-plan")
    run_tool_parser.add_argument("--user-approved", action="store_true")
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

    compatibility_parser = subparsers.add_parser("runtime-compatibility-matrix", help="Report model provider and host adapter compatibility")
    add_common_args(compatibility_parser)
    compatibility_parser.add_argument("--project", required=True)
    compatibility_parser.add_argument("--provider", choices=MODEL_PROVIDERS, nargs="*")
    compatibility_parser.add_argument("--host-type", choices=HOST_TYPES, nargs="*")
    compatibility_parser.add_argument("--require-capability", nargs="*")
    compatibility_parser.add_argument("--output", type=Path)
    compatibility_parser.set_defaults(func=cmd_runtime_compatibility_matrix)

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

    quality_score_parser = subparsers.add_parser("runtime-quality-score", help="Calculate and optionally record a scoped runtime quality score")
    add_common_args(quality_score_parser)
    quality_score_parser.add_argument("--project", required=True)
    quality_score_parser.add_argument("--goal-id")
    quality_score_parser.add_argument("--run-id")
    quality_score_parser.add_argument("--min-score", type=float, default=70)
    quality_score_parser.add_argument("--record", action="store_true")
    quality_score_parser.set_defaults(func=cmd_runtime_quality_score)

    self_audit_parser = subparsers.add_parser("runtime-self-audit", help="Find open runtime governance and completion risks")
    add_common_args(self_audit_parser)
    self_audit_parser.add_argument("--project", required=True)
    self_audit_parser.add_argument("--goal-id")
    self_audit_parser.add_argument("--run-id")
    self_audit_parser.add_argument("--record", action="store_true")
    self_audit_parser.set_defaults(func=cmd_runtime_self_audit)

    benchmark_parser = subparsers.add_parser("runtime-benchmark", help="Record and evaluate a benchmark or performance non-regression metric")
    add_common_args(benchmark_parser)
    benchmark_parser.add_argument("--project", required=True)
    benchmark_parser.add_argument("--goal-id")
    benchmark_parser.add_argument("--run-id")
    benchmark_parser.add_argument("--name", required=True)
    benchmark_parser.add_argument("--metric", required=True)
    benchmark_parser.add_argument("--baseline-value", type=float)
    benchmark_parser.add_argument("--current-value", type=float, required=True)
    benchmark_parser.add_argument("--threshold-value", type=float)
    benchmark_parser.add_argument("--direction", choices=BENCHMARK_DIRECTIONS, default="lower-is-better")
    benchmark_parser.add_argument("--unit")
    benchmark_parser.add_argument("--status", choices=("passed", "failed", "blocked", "not-run"))
    benchmark_parser.add_argument("--command")
    benchmark_parser.add_argument("--evidence")
    benchmark_parser.add_argument("--record", action="store_true")
    benchmark_parser.set_defaults(func=cmd_runtime_benchmark)

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

    governance_parser = subparsers.add_parser("runtime-governance-proposal", help="Record a governed Agent OS rule or skill evolution proposal")
    add_common_args(governance_parser)
    governance_parser.add_argument("--project", required=True)
    governance_parser.add_argument("--goal-id")
    governance_parser.add_argument("--run-id")
    governance_parser.add_argument("--name", required=True)
    governance_parser.add_argument("--source-type", choices=("skill", "rule"), default="rule")
    governance_parser.add_argument("--trigger", required=True)
    governance_parser.add_argument("--evidence", required=True)
    governance_parser.add_argument("--validation")
    governance_parser.add_argument("--scope")
    governance_parser.add_argument("--boundary")
    governance_parser.add_argument("--ready-for-review", action="store_true")
    governance_parser.set_defaults(func=cmd_runtime_governance_proposal)

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
    runtime_record_parser.add_argument("--topic")
    runtime_record_parser.add_argument("--subscriber", default="*")
    runtime_record_parser.add_argument("--payload-json")
    runtime_record_parser.add_argument("--request")
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
        choices=SUBAGENT_ROLES,
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
    runtime_record_parser.add_argument("--intent-id")
    runtime_record_parser.add_argument("--intent-type", choices=INTENT_TYPES)
    runtime_record_parser.add_argument("--mutation-authorization", choices=MUTATION_AUTHORIZATIONS)
    runtime_record_parser.add_argument("--approved-scope")
    runtime_record_parser.add_argument("--confidence", type=float)
    runtime_record_parser.add_argument("--risk-level", choices=("low", "normal", "high", "critical"), default="normal")
    runtime_record_parser.add_argument("--allowed-actions", nargs="*")
    runtime_record_parser.add_argument("--blocked-actions", nargs="*")
    runtime_record_parser.add_argument("--explanation-required", action="store_true")
    runtime_record_parser.add_argument("--proposal-id")
    runtime_record_parser.add_argument("--action-type", choices=ACTION_TYPES)
    runtime_record_parser.add_argument("--tool")
    runtime_record_parser.add_argument("--target-paths")
    runtime_record_parser.add_argument("--reason")
    runtime_record_parser.add_argument("--gate-decision")
    runtime_record_parser.add_argument("--gate-reason")
    runtime_record_parser.add_argument("--requires-approval", action="store_true")
    runtime_record_parser.add_argument("--validation-plan")
    runtime_record_parser.add_argument("--approved-text")
    runtime_record_parser.add_argument("--expires-when")
    runtime_record_parser.add_argument("--observation-id", type=int)
    runtime_record_parser.add_argument("--feedback-id", type=int)
    runtime_record_parser.add_argument("--confidence-delta", type=float, default=0)
    runtime_record_parser.add_argument("--risk-delta", choices=("none", "increased", "decreased"), default="none")
    runtime_record_parser.add_argument("--scope-delta", choices=("none", "expanded", "narrowed", "changed"), default="none")
    runtime_record_parser.add_argument("--evidence-delta", choices=("none", "supports", "contradicts", "new-evidence"), default="none")
    runtime_record_parser.add_argument("--drift-type", choices=DRIFT_TYPES)
    runtime_record_parser.add_argument("--expected")
    runtime_record_parser.add_argument("--actual")
    runtime_record_parser.add_argument("--resolution")
    runtime_record_parser.add_argument("--version", type=int)
    runtime_record_parser.add_argument("--assumptions")
    runtime_record_parser.add_argument("--steps")
    runtime_record_parser.add_argument("--validation")
    runtime_record_parser.add_argument("--rollback")
    runtime_record_parser.add_argument("--available-at")
    runtime_record_parser.add_argument("--depends-on")
    runtime_record_parser.add_argument("--required-resources")
    runtime_record_parser.add_argument("--next-action")
    runtime_record_parser.add_argument("--schedule-id")
    runtime_record_parser.add_argument("--resource-type", choices=RESOURCE_TYPES)
    runtime_record_parser.add_argument("--resource-key")
    runtime_record_parser.add_argument("--quantity", type=int, default=1)
    runtime_record_parser.add_argument("--queue-priority", type=int, default=0)
    runtime_record_parser.add_argument("--failure-detail")
    runtime_record_parser.add_argument("--score", type=float)
    runtime_record_parser.add_argument("--grade", choices=("A", "B", "C", "D", "F"))
    runtime_record_parser.add_argument("--verification-score", type=float, default=0)
    runtime_record_parser.add_argument("--intent-score", type=float, default=0)
    runtime_record_parser.add_argument("--schedule-score", type=float, default=0)
    runtime_record_parser.add_argument("--docs-score", type=float, default=0)
    runtime_record_parser.add_argument("--recovery-score", type=float, default=0)
    runtime_record_parser.add_argument("--memory-score", type=float, default=0)
    runtime_record_parser.add_argument("--risk-penalty", type=float, default=0)
    runtime_record_parser.add_argument("--finding-type")
    runtime_record_parser.add_argument("--recommendation")
    runtime_record_parser.add_argument("--metric")
    runtime_record_parser.add_argument("--baseline-value", type=float)
    runtime_record_parser.add_argument("--current-value", type=float)
    runtime_record_parser.add_argument("--threshold-value", type=float)
    runtime_record_parser.add_argument("--direction", choices=BENCHMARK_DIRECTIONS, default="lower-is-better")
    runtime_record_parser.add_argument("--unit")
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

    schedule_parser = subparsers.add_parser("runtime-schedule", help="Add or update a Scheduler queue item")
    add_common_args(schedule_parser)
    schedule_parser.add_argument("--project", required=True)
    schedule_parser.add_argument("--id")
    schedule_parser.add_argument("--run-id")
    schedule_parser.add_argument("--goal-id")
    schedule_parser.add_argument("--task-id")
    schedule_parser.add_argument("--intent-id")
    schedule_parser.add_argument("--action-type", choices=ACTION_TYPES, required=True)
    schedule_parser.add_argument("--assigned-role")
    schedule_parser.add_argument("--status", choices=SCHEDULE_STATUSES)
    schedule_parser.add_argument("--priority", type=int, default=0)
    schedule_parser.add_argument("--depends-on")
    schedule_parser.add_argument("--required-resources")
    schedule_parser.add_argument("--reason")
    schedule_parser.add_argument("--next-action")
    schedule_parser.add_argument("--available-at")
    schedule_parser.add_argument("--blocker")
    schedule_parser.add_argument("--evidence")
    schedule_parser.set_defaults(func=cmd_runtime_schedule)

    scheduler_next_parser = subparsers.add_parser("runtime-scheduler-next", help="Select the next schedulable Agent OS queue item")
    add_common_args(scheduler_next_parser)
    scheduler_next_parser.add_argument("--project", required=True)
    scheduler_next_parser.add_argument("--goal-id")
    scheduler_next_parser.add_argument("--limit", type=int, default=20)
    scheduler_next_parser.add_argument("--advance", action="store_true")
    scheduler_next_parser.set_defaults(func=cmd_runtime_scheduler_next)

    schedule_complete_parser = subparsers.add_parser("runtime-schedule-complete", help="Complete or block a Scheduler queue item")
    add_common_args(schedule_complete_parser)
    schedule_complete_parser.add_argument("--project", required=True)
    schedule_complete_parser.add_argument("--id", required=True)
    schedule_complete_parser.add_argument("--ok", action="store_true")
    schedule_complete_parser.add_argument("--blocker")
    schedule_complete_parser.add_argument("--evidence")
    schedule_complete_parser.set_defaults(func=cmd_runtime_schedule_complete)

    request_resource_parser = subparsers.add_parser("runtime-request-resource", help="Request a Resource Manager lease")
    add_common_args(request_resource_parser)
    request_resource_parser.add_argument("--project", required=True)
    request_resource_parser.add_argument("--id")
    request_resource_parser.add_argument("--run-id")
    request_resource_parser.add_argument("--goal-id")
    request_resource_parser.add_argument("--task-id")
    request_resource_parser.add_argument("--schedule-id")
    request_resource_parser.add_argument("--resource-type", choices=RESOURCE_TYPES, required=True)
    request_resource_parser.add_argument("--resource-key", required=True)
    request_resource_parser.add_argument("--quantity", type=int, default=1)
    request_resource_parser.add_argument("--reason")
    request_resource_parser.add_argument("--expires-at")
    request_resource_parser.add_argument("--force", action="store_true")
    request_resource_parser.set_defaults(func=cmd_runtime_request_resource)

    release_resource_parser = subparsers.add_parser("runtime-release-resource", help="Release a Resource Manager lease")
    add_common_args(release_resource_parser)
    release_resource_parser.add_argument("--project", required=True)
    release_resource_parser.add_argument("--id", required=True)
    release_resource_parser.add_argument("--reason")
    release_resource_parser.set_defaults(func=cmd_runtime_release_resource)

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


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
