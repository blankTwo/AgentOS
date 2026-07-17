import json
import http.server
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME = ROOT / "scripts" / "agent-runtime.py"
MEMORY_TOOLS = ROOT / "scripts" / "memory-tools.py"
AGENT_OS_CLI = ROOT / "scripts" / "agent-os.py"


class AgentRuntimeCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(AGENT_RUNTIME), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def run_memory_cli(self, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, str(MEMORY_TOOLS), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def run_agent_os_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(AGENT_OS_CLI), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )

    def test_project_execution_document_paths_are_documented(self) -> None:
        required_paths = [
            "docs/agent-os/plans/",
            "docs/agent-os/tasks/",
            "docs/agent-os/decisions/",
            "docs/agent-os/reviews/",
            "docs/agent-os/verification/",
        ]
        files = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "context" / "language-context.md",
            ROOT / "rules" / "agent-runtime.md",
            ROOT / "rules" / "memory-enhanced.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        for required_path in required_paths:
            self.assertIn(required_path, combined)
        self.assertIn("Do not write project execution documents under `.agent-os/`", combined)

    def test_documentation_gate_is_documented(self) -> None:
        files = [
            ROOT / "AGENTS.md",
            ROOT / "README.md",
            ROOT / "rules" / "review-gate.md",
            ROOT / "workflows" / "feature-implementation.md",
            ROOT / "workflows" / "api-contract-change.md",
            ROOT / "workflows" / "bug-diagnosis.md",
            ROOT / "workflows" / "agent-os-evolution.md",
        ]
        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
        required_terms = [
            "Documentation Gate",
            "README",
            "README or docs",
            "docs/agent-os/",
            "Memory is not documentation",
            "Runtime records are not documentation",
            "why no documentation update was needed",
        ]
        for term in required_terms:
            self.assertIn(term, combined)

    def test_distribution_strategy_is_documented(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        required_terms = [
            "安装与分发",
            "复制到 `.agent-os/`",
            "clone 为 `.agent-os`",
            "Git submodule / subtree",
            "VSCode 插件注入",
            "包管理器分发",
            "runtime-doctor",
            "runtime-version",
            "runtime-migrate --dry-run",
            "runtime-dashboard",
            "runtime-quality-trends",
            "runtime-policy-packs",
        ]
        for term in required_terms:
            self.assertIn(term, readme)

    def test_vscode_plugin_sources_are_present(self) -> None:
        package_json = (ROOT / "vscode-plugin" / "package.json").read_text(encoding="utf-8")
        extension_js = (ROOT / "vscode-plugin" / "extension.js").read_text(encoding="utf-8")
        plugin_readme = (ROOT / "vscode-plugin" / "README.md").read_text(encoding="utf-8")
        sync_script = (ROOT / "vscode-plugin" / "scripts" / "sync-agent-os.js").read_text(encoding="utf-8")
        vscodeignore = (ROOT / "vscode-plugin" / ".vscodeignore").read_text(encoding="utf-8")
        license_text = (ROOT / "vscode-plugin" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("agentOs.injectWorkspace", package_json)
        self.assertIn("Agent OS：注入当前工作区", package_json)
        self.assertIn("agentOs.uninstallWorkspace", package_json)
        self.assertIn("agentOsStatus", package_json)
        self.assertIn('"type": "webview"', package_json)
        self.assertNotIn("viewsWelcome", package_json)
        self.assertIn("https://github.com/blankTwo/AgentOS", package_json)
        self.assertIn("prepack", package_json)
        self.assertIn('"package"', package_json)
        self.assertIn("prepare:agent-os && npx @vscode/vsce package", package_json)
        self.assertIn("registerWebviewViewProvider", extension_js)
        self.assertIn("enableCommandUris", extension_js)
        self.assertIn("doctor", extension_js)
        self.assertIn("runtime-summary", extension_js)
        self.assertIn("dashboard", extension_js)
        self.assertIn("openOverview", extension_js)
        self.assertIn("Agent OS 状态", extension_js)
        self.assertIn("注入工作区", extension_js)
        self.assertIn("卸载工作区", extension_js)
        self.assertIn("rootAgentsCreated", extension_js)
        self.assertIn("rootAgentsLooksGenerated", extension_js)
        self.assertIn(".install-meta.json", extension_js)
        self.assertIn("postMessage", extension_js)
        self.assertIn("openExternal", extension_js)
        self.assertIn("vscode-plugin", sync_script)
        self.assertIn("!agent-os/**", vscodeignore)
        self.assertIn("MIT License", license_text)

    def test_runtime_doctor_checks_install_health(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-doctor",
                "--db",
                db,
            )
            self.assertTrue(result["ok"], result)
            check_names = {check["name"] for check in result["checks"]}
            self.assertTrue({"directories", "agents", "rules", "skills", "memory", "runtime"}.issubset(check_names))
            self.assertTrue({"bootstrap", "policy-packs", "security", "version", "db-writable"}.issubset(check_names))

    def test_runtime_doctor_reports_broken_install(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rules").mkdir()
            (root / "skills").mkdir()
            (root / "memory").mkdir()
            (root / "scripts").mkdir()
            result = self.run_cli(
                "runtime-doctor",
                "--root",
                str(root),
            )
            self.assertFalse(result["ok"])
            failed = {check["name"] for check in result["checks"] if check["status"] == "failed"}
            self.assertIn("agents", failed)
            self.assertIn("skills", failed)

    def test_agent_os_cli_alias_runs_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            completed = self.run_agent_os_cli("doctor", "--db", db)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["ok"], result)
            check_names = {check["name"] for check in result["checks"]}
            self.assertIn("runtime", check_names)

    def test_agent_os_cli_installs_into_empty_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "user-project"
            completed = self.run_agent_os_cli("install", "--target", str(target))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((target / ".agent-os" / "AGENTS.md").exists())
            self.assertTrue((target / ".agent-os" / "scripts" / "agent-runtime.py").exists())
            self.assertFalse((target / ".agent-os" / "vscode-plugin").exists())
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertIn("This project uses Agent OS from `.agent-os/`", (target / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertTrue((target / ".agent-os" / "memory" / "index.db").exists())

            doctor = subprocess.run(
                [
                    sys.executable,
                    str(target / ".agent-os" / "scripts" / "agent-runtime.py"),
                    "runtime-doctor",
                    "--db",
                    str(target / ".agent-os" / "memory" / "index.db"),
                ],
                cwd=target,
                text=True,
                capture_output=True,
                timeout=60,
            )
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            result = json.loads(doctor.stdout)
            self.assertTrue(result["ok"], result)

    def test_agent_os_cli_manages_git_info_exclude(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "user-project"
            target.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=target, check=True, text=True, capture_output=True)
            completed = self.run_agent_os_cli("install", "--target", str(target))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            exclude_path = target / ".git" / "info" / "exclude"
            self.assertTrue(exclude_path.exists())
            exclude_text = exclude_path.read_text(encoding="utf-8")
            self.assertIn("# Agent OS managed excludes", exclude_text)
            self.assertIn("AGENTS.md", exclude_text)
            self.assertIn(".agent-os/", exclude_text)

            uninstall = self.run_agent_os_cli("uninstall", "--target", str(target), "--remove-root-agents")
            self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
            self.assertFalse((target / ".agent-os").exists())
            self.assertFalse((target / "AGENTS.md").exists())
            self.assertNotIn("# Agent OS managed excludes", exclude_path.read_text(encoding="utf-8"))

    def test_agent_os_cli_writes_gitignore_without_git_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "user-project"
            target.mkdir(parents=True)
            completed = self.run_agent_os_cli("ignore", "--target", str(target))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            gitignore_path = target / ".gitignore"
            self.assertTrue(gitignore_path.exists())
            content = gitignore_path.read_text(encoding="utf-8")
            self.assertIn("# Agent OS managed ignores", content)
            self.assertIn("AGENTS.md", content)
            self.assertIn(".agent-os/", content)

    def test_runtime_version_and_migrate_support_safe_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "runtime.db"
            version = self.run_cli(
                "runtime-version",
                "--db",
                str(db_path),
            )
            self.assertEqual(version["agent_os_version"], "2.0.0")
            self.assertEqual(version["expected_schema_version"], "21")
            self.assertFalse(version["db_exists"])
            self.assertTrue(version["migration_required"])

            dry_run = self.run_cli(
                "runtime-migrate",
                "--db",
                str(db_path),
                "--dry-run",
            )
            self.assertFalse(db_path.exists())
            self.assertFalse(dry_run["applied"])
            self.assertIn("create database", dry_run["actions"])

            migrated = self.run_cli(
                "runtime-migrate",
                "--db",
                str(db_path),
            )
            self.assertTrue(migrated["ok"], migrated)
            self.assertTrue(migrated["applied"])
            self.assertEqual(migrated["after_schema_version"], "21")
            self.assertIn("rollback_hint", migrated)

            after = self.run_cli(
                "runtime-version",
                "--db",
                str(db_path),
            )
            self.assertTrue(after["db_exists"])
            self.assertEqual(after["db_schema_version"], "21")
            self.assertFalse(after["migration_required"])

            second = self.run_cli(
                "runtime-migrate",
                "--db",
                str(db_path),
            )
            self.assertTrue(second["ok"], second)
            self.assertTrue(second["report"]["backup_created"])
            self.assertTrue(Path(second["backup"]).exists())
            self.assertIn("Restore backup", second["rollback_hint"])

    def test_runtime_dashboard_generates_local_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = str(root / "runtime.db")
            output = root / "dashboard.html"
            self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-dashboard",
                "--goal-id",
                "goal-dashboard",
                "--project",
                "agent-os",
                "--request",
                "Build dashboard",
                "--record",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-dashboard",
                "--scope",
                "dashboard",
                "--command",
                "open dashboard",
                "--result",
                "passed",
                "--evidence",
                "dashboard visible",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "intent",
                "--project",
                "agent-os",
                "--id",
                "intent-dashboard",
                "--summary",
                "Dashboard intent",
                "--intent-type",
                "diagnosis",
                "--mutation-authorization",
                "read-only",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "action-proposal",
                "--project",
                "agent-os",
                "--id",
                "action-dashboard",
                "--intent-id",
                "intent-dashboard",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--reason",
                "Dashboard action",
                "--status",
                "blocked",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "drift",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-dashboard",
                "--proposal-id",
                "action-dashboard",
                "--drift-type",
                "mutation",
                "--expected",
                "read-only",
                "--actual",
                "patch",
                "--status",
                "open",
            )
            result = self.run_cli(
                "runtime-dashboard",
                "--db",
                db,
                "--project",
                "agent-os",
                "--output",
                str(output),
            )
            self.assertTrue(result["ok"])
            self.assertTrue(output.exists())
            data_output = root / "dashboard.json"
            data_result = self.run_cli(
                "runtime-dashboard",
                "--db",
                db,
                "--project",
                "agent-os",
                "--output",
                str(output),
                "--data-output",
                str(data_output),
                "--inline-data",
            )
            self.assertTrue(data_result["ok"])
            self.assertTrue(data_output.exists())
            self.assertEqual(data_result["data_source"]["kind"], "vscode-dashboard-data")
            self.assertIn("records", data_result["data_source"])
            for section in ("intents", "actions", "drifts", "feedback", "plans"):
                self.assertIn(section, data_result["data_source"]["sections"])
            html_text = output.read_text(encoding="utf-8")
            for heading in ("目标", "运行", "任务", "事件", "意图", "动作", "漂移", "反馈", "计划版本", "验证"):
                self.assertIn(heading, html_text)
            self.assertIn("goal-dashboard", html_text)
            self.assertIn("run-dashboard", html_text)
            self.assertIn("dashboard visible", html_text)
            self.assertIn("intent-dashboard", html_text)
            self.assertIn("action-dashboard", html_text)

    def test_detect_context_classifies_cross_layer_feature(self) -> None:
        result = self.run_cli(
            "runtime-detect-context",
            "--request",
            "Implement phone login",
            "--files",
            "src/pages/Login.tsx",
            "server/auth.ts",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["intent"], "feature")
        self.assertEqual(result["scale"], "L3")
        self.assertIn("Integration", result["task_layers"])
        self.assertIn("UI", result["task_layers"])

    def test_detect_context_keeps_diagnosis_requests_read_only(self) -> None:
        result = self.run_cli(
            "runtime-detect-context",
            "--request",
            "用户反馈第一次检测原创度0 第二次检测就好了，你根据这个反馈好好排查一下",
            "--files",
            "apps/server/src/third_party/lj-api.service.ts",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["intent"], "diagnosis")
        self.assertEqual(result["mutation_authorization"], "read-only")
        self.assertIn("Bugfix", result["task_layers"])
        self.assertIn("mutation_authorization=read-only", result["evidence"])

    def test_runtime_compile_mission_builtin_locks_read_only_diagnosis(self) -> None:
        result = self.run_cli(
            "runtime-compile-mission",
            "--project",
            "agent-os",
            "--request",
            "用户反馈第一次检测原创度0 第二次检测就好了，你根据这个反馈好好排查一下",
            "--files",
            "apps/server/src/third_party/lj-api.service.ts",
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["locked"])
        self.assertEqual(result["mission_ir"]["specVersion"], "mission-ir/v1")
        self.assertEqual(result["mission_ir"]["mission"]["type"], "diagnose")
        self.assertEqual(result["mission_ir"]["mission"]["mode"], "readonly")
        self.assertTrue(result["mission_ir"]["constraints"]["readonly"])
        self.assertFalse(result["mission_ir"]["constraints"]["allowWrite"])
        self.assertEqual(result["runtime_mapping"]["intent_type"], "diagnosis")
        self.assertEqual(result["runtime_mapping"]["mutation_authorization"], "read-only")
        self.assertEqual(result["visible_intent"]["format"], "intent-summary/v1")
        self.assertIn("意图编译已生效", result["visible_intent"]["summary"])
        self.assertEqual(result["visible_intent"]["compiler"]["mode"], "builtin-rules")
        self.assertEqual(result["visible_intent"]["mission"]["mutation_authorization"], "read-only")
        self.assertFalse(result["visible_intent"]["permissions"]["allow_write"])

    def test_runtime_compile_mission_normalizes_markdown_llm_output(self) -> None:
        llm_response = """```json
{
  "specVersion": "mission-ir/v1",
  "mission": {"type": "diagnose", "mode": "readonly"},
  "intent": {"primary": "investigate first originality check returning zero", "confidence": 0.75, "ambiguity": "medium"},
  "constraints": {"readonly": true, "allowWrite": false, "allowCommit": false, "allowDeploy": false, "requireApprovalBeforeMutation": true},
  "deliverables": ["root_cause", "evidence", "conclusion", "reproduction_steps"],
  "evidenceRequirements": {"required": true, "types": ["state_inspection", "timing_analysis"], "minimumBeforeAction": 3},
  "successCriteria": ["identify_why_first_check_returns_zero"],
  "clarification": ["which endpoint is affected"]
}
```"""
        result = self.run_cli(
            "runtime-compile-mission",
            "--project",
            "agent-os",
            "--request",
            "用户反馈第一次检测原创度0 第二次检测就好了，你根据这个反馈好好排查一下",
            "--llm-response",
            llm_response,
        )
        self.assertTrue(result["ok"], result)
        mission_ir = result["mission_ir"]
        self.assertEqual(mission_ir["source"]["compiler"], "provided-llm-output")
        self.assertEqual(mission_ir["mission"]["mode"], "readonly")
        self.assertFalse(mission_ir["constraints"]["allowWrite"])
        self.assertIn("repair_plan", mission_ir["deliverables"])
        self.assertIn("evidence", mission_ir["deliverables"])
        self.assertIn("code_location", mission_ir["evidenceRequirements"]["types"])

    def test_runtime_compile_mission_falls_back_when_llm_unavailable(self) -> None:
        result = self.run_cli(
            "runtime-compile-mission",
            "--project",
            "agent-os",
            "--request",
            "先帮我排查这个接口为什么返回500",
            "--provider",
            "custom",
            "--base-url",
            "http://127.0.0.1:9/v1",
            "--api-key",
            "test-key",
            "--model",
            "missing-model",
            "--timeout",
            "1",
        )
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["compiler_metadata"]["fallback"])
        self.assertEqual(result["mission_ir"]["mission"]["type"], "diagnose")
        self.assertFalse(result["mission_ir"]["constraints"]["allowWrite"])
        self.assertTrue(result["visible_intent"]["compiler"]["fallback"])
        self.assertIn("已回退", result["visible_intent"]["summary"])

    def test_runtime_plan_tasks_returns_visible_markdown_checklist(self) -> None:
        result = self.run_cli(
            "runtime-plan-tasks",
            "--project",
            "agent-os",
            "--goal-id",
            "goal-phone-login",
            "--request",
            "实现手机号登录",
            "--scale",
            "L3",
            "--capability-status",
            "broken-chain",
        )
        self.assertTrue(result["ok"], result)
        visible_plan = result["visible_plan"]
        self.assertEqual(visible_plan["format"], "markdown-checklist/v1")
        self.assertEqual(visible_plan["scale"], "L3")
        self.assertEqual(visible_plan["capability_status"], "broken-chain")
        self.assertIn("Agent OS：执行计划", visible_plan["markdown"])
        self.assertIn("- [ ] Confirm context, task layer, and scale", visible_plan["markdown"])
        self.assertIn("验证：", visible_plan["markdown"])
        self.assertEqual(len(visible_plan["items"]), len(result["tasks"]))

    def test_intent_runtime_blocks_read_only_mutation_and_records_loop_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            intent = self.run_cli(
                "runtime-detect-intent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--request",
                "用户反馈第一次检测原创度0 第二次检测就好了，你根据这个反馈好好排查一下",
                "--files",
                "apps/server/src/third_party/lj-api.service.ts",
                "--record",
            )
            self.assertTrue(intent["ok"], intent)
            self.assertEqual(intent["intent"]["intent_type"], "diagnosis")
            self.assertEqual(intent["intent"]["mutation_authorization"], "read-only")
            self.assertIn("patch", intent["intent"]["blocked_actions"])
            self.assertEqual(intent["mission_ir"]["mission"]["type"], "diagnose")
            self.assertFalse(intent["mission_ir"]["constraints"]["allowWrite"])

            conn = sqlite3.connect(db)
            try:
                row = conn.execute(
                    "SELECT mission_ir_json, compiler_metadata_json FROM intent_states WHERE id = ?",
                    ("intent-diagnosis",),
                ).fetchone()
            finally:
                conn.close()
            self.assertIsNotNone(row)
            self.assertIn('"specVersion": "mission-ir/v1"', row[0])
            self.assertIn("builtin-rules", row[1])

            registry = self.run_cli(
                "runtime-tool-registry",
                "--db",
                db,
                "--write-only",
            )
            registry_tools = {item["tool"] for item in registry["tools"]}
            self.assertIn("patch.apply", registry_tools)
            self.assertIn("memory.write", registry_tools)

            validation = self.run_cli(
                "runtime-validate-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--action-type",
                "patch",
                "--target-paths",
                "apps/server/src/third_party/lj-api.service.ts",
                "--validation-plan",
                "python -m unittest tests.test_agent_runtime",
                "--record",
            )
            self.assertFalse(validation["ok"], validation)
            self.assertEqual(validation["gate"]["decision"], "blocked")
            self.assertIn("blocked-actions:patch,write", validation["gate"]["missing_requirements"])

            proposal = self.run_cli(
                "runtime-propose-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--id",
                "action-readonly-patch",
                "--intent-id",
                "intent-diagnosis",
                "--action-type",
                "patch",
                "--target-paths",
                "apps/server/src/third_party/lj-api.service.ts",
                "--reason",
                "Patch attempt during diagnosis",
                "--validation-plan",
                "python -m unittest tests.test_agent_runtime",
            )
            self.assertFalse(proposal["ok"], proposal)
            self.assertEqual(proposal["gate"]["decision"], "blocked")

            blocked_tool = self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--tool-type",
                "shell",
                "--command",
                "python -m py_compile scripts\\agent-runtime.py",
                "--target-paths",
                "apps/server/src/third_party/lj-api.service.ts",
                "--validation-plan",
                "python -m unittest tests.test_agent_runtime",
            )
            self.assertFalse(blocked_tool["ok"], blocked_tool)
            self.assertEqual(blocked_tool["status"], "blocked")
            self.assertEqual(blocked_tool["gate"]["decision"], "blocked")

            side_effect = Path(tmp) / "blocked-side-effect.txt"
            blocked_write = self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--tool-type",
                "shell",
                "--command",
                f"Set-Content -LiteralPath '{side_effect}' -Value blocked",
                "--target-paths",
                "apps/server/src/third_party/lj-api.service.ts",
                "--validation-plan",
                "No source changes before user approval.",
            )
            self.assertFalse(blocked_write["ok"], blocked_write)
            self.assertEqual(blocked_write["status"], "blocked")
            self.assertFalse(side_effect.exists(), "Execution Gate must block shell side effects before execution")

            feedback = self.run_cli(
                "runtime-record-feedback",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--proposal-id",
                "action-readonly-patch",
                "--confidence-delta",
                "-0.1",
                "--evidence-delta",
                "new-evidence",
                "--summary",
                "A mutation was proposed while the user asked for diagnosis only.",
            )
            self.assertTrue(feedback["ok"], feedback)

            drift = self.run_cli(
                "runtime-detect-drift",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--proposal-id",
                "action-readonly-patch",
                "--record",
            )
            self.assertFalse(drift["ok"], drift)
            self.assertEqual(drift["drifts"][0]["drift_type"], "mutation")

            reanchor = self.run_cli(
                "runtime-reanchor",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
            )
            self.assertTrue(reanchor["ok"], reanchor)
            self.assertIn("Re-anchor", reanchor["prompt"])

            plan = self.run_cli(
                "runtime-revise-plan",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-diagnosis",
                "--steps",
                "1. Keep diagnosis read-only. 2. Collect upstream evidence. 3. Ask before fixing.",
                "--validation",
                "No source changes before user approval.",
                "--status",
                "active",
            )
            self.assertTrue(plan["ok"], plan)
            self.assertEqual(plan["version"], 1)

            listed_intents = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "intent",
            )
            self.assertEqual(listed_intents["results"][0]["id"], "intent-diagnosis")

            listed_drifts = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "drift",
                "--status",
                "open",
            )
            self.assertEqual(listed_drifts["results"][0]["drift_type"], "mutation")

            listed_plans = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "plan-version",
                "--status",
                "active",
            )
            self.assertEqual(listed_plans["results"][0]["version"], 1)

    def test_approval_upgrades_read_only_intent_for_confirmed_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-detect-intent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-approval",
                "--request",
                "先帮我排查这个接口为什么返回500",
                "--files",
                "server/api.ts",
                "--record",
            )
            self.run_cli(
                "runtime-propose-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--id",
                "action-confirmed-patch",
                "--intent-id",
                "intent-approval",
                "--action-type",
                "patch",
                "--target-paths",
                "server/api.ts",
                "--reason",
                "Apply confirmed fix after user approval",
                "--validation-plan",
                "python -m py_compile server/api.ts",
            )
            approval = self.run_cli(
                "runtime-approve-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-approval",
                "--proposal-id",
                "action-confirmed-patch",
                "--approved-text",
                "那你修一下",
                "--approved-scope",
                "server/api.ts",
            )
            self.assertTrue(approval["ok"], approval)

            gate = self.run_cli(
                "runtime-execution-gate",
                "--db",
                db,
                "--project",
                "agent-os",
                "--proposal-id",
                "action-confirmed-patch",
                "--user-approved",
                "--validation-plan",
                "python -m py_compile server/api.ts",
            )
            self.assertTrue(gate["ok"], gate)
            self.assertEqual(gate["gate"]["decision"], "allowed")

    def test_final_check_blocks_open_intent_loop_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "goal-intent-risk",
                "--objective",
                "Audit intent risk",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "policy",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-intent-risk",
                "--decision-type",
                "execution-mode",
                "--decision",
                "direct",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-intent-risk",
                "--scope",
                "intent risk",
                "--result",
                "passed",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "other-goal",
                "--objective",
                "Other unrelated audit",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "intent",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-intent-risk",
                "--id",
                "intent-risk",
                "--summary",
                "Read-only diagnosis",
                "--intent-type",
                "diagnosis",
                "--mutation-authorization",
                "read-only",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "action-proposal",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-intent-risk",
                "--id",
                "action-risk",
                "--intent-id",
                "intent-risk",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--reason",
                "Unauthorized mutation",
                "--status",
                "blocked",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "drift",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-risk",
                "--proposal-id",
                "action-risk",
                "--drift-type",
                "mutation",
                "--expected",
                "read-only",
                "--actual",
                "patch",
                "--status",
                "open",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "intent",
                "--project",
                "agent-os",
                "--goal-id",
                "other-goal",
                "--id",
                "intent-other",
                "--summary",
                "Other read-only diagnosis",
                "--intent-type",
                "diagnosis",
                "--mutation-authorization",
                "read-only",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "drift",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-other",
                "--drift-type",
                "mutation",
                "--expected",
                "other read-only",
                "--actual",
                "other patch",
                "--status",
                "open",
            )
            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-intent-risk",
            )
            self.assertFalse(final_check["ok"], final_check)
            self.assertIn("blocked action proposal", final_check["missing"])
            self.assertIn("open drift events", final_check["missing"])
            self.assertEqual(final_check["action_proposals"][0]["id"], "action-risk")
            self.assertEqual(final_check["open_drifts"][0]["drift_type"], "mutation")
            self.assertEqual(len(final_check["open_drifts"]), 1)

    def test_runtime_record_supports_intent_loop_record_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            intent = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "intent",
                "--project",
                "agent-os",
                "--id",
                "intent-record",
                "--summary",
                "Investigate without mutation.",
                "--intent-type",
                "diagnosis",
                "--mutation-authorization",
                "read-only",
                "--current-phase",
                "explaining",
                "--confidence",
                "0.8",
                "--explanation-required",
            )
            self.assertTrue(intent["ok"], intent)

            proposal = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "action-proposal",
                "--project",
                "agent-os",
                "--id",
                "proposal-record",
                "--intent-id",
                "intent-record",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--target-paths",
                "server/api.ts",
                "--reason",
                "Regression guard proposal",
                "--status",
                "blocked",
                "--gate-decision",
                "blocked",
                "--gate-reason",
                "read-only",
                "--requires-approval",
            )
            self.assertTrue(proposal["ok"], proposal)

            approval = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "approval",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-record",
                "--proposal-id",
                "proposal-record",
                "--approved-text",
                "那你修一下",
                "--approved-scope",
                "server/api.ts",
            )
            self.assertTrue(approval["ok"], approval)

            feedback = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "feedback",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-record",
                "--proposal-id",
                "proposal-record",
                "--confidence-delta",
                "-0.2",
                "--evidence-delta",
                "contradicts",
                "--summary",
                "User intent and proposed mutation conflict.",
            )
            self.assertTrue(feedback["ok"], feedback)

            drift = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "drift",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-record",
                "--proposal-id",
                "proposal-record",
                "--feedback-id",
                str(feedback["id"]),
                "--drift-type",
                "mutation",
                "--expected",
                "read-only diagnosis",
                "--actual",
                "patch proposal",
                "--status",
                "open",
            )
            self.assertTrue(drift["ok"], drift)

            plan = self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "plan-version",
                "--project",
                "agent-os",
                "--intent-id",
                "intent-record",
                "--steps",
                "1. Re-anchor. 2. Wait for confirmation. 3. Execute only after approval.",
                "--validation",
                "Execution gate must pass.",
                "--status",
                "active",
            )
            self.assertTrue(plan["ok"], plan)
            self.assertEqual(plan["version"], 1)

            listed_intents = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "intent",
                "--status",
                "explaining",
            )
            self.assertEqual(listed_intents["results"][0]["id"], "intent-record")
            self.assertEqual(listed_intents["results"][0]["mutation_authorization"], "read-only")

            listed_proposals = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "action-proposal",
                "--status",
                "blocked",
            )
            self.assertEqual(listed_proposals["results"][0]["id"], "proposal-record")

            listed_approvals = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "approval",
            )
            self.assertEqual(listed_approvals["results"][0]["proposal_id"], "proposal-record")

            listed_feedback = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "feedback",
            )
            self.assertEqual(listed_feedback["results"][0]["summary"], "User intent and proposed mutation conflict.")

            listed_drift = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "drift",
                "--status",
                "open",
            )
            self.assertEqual(listed_drift["results"][0]["drift_type"], "mutation")

            listed_plans = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "plan-version",
                "--status",
                "active",
            )
            self.assertEqual(listed_plans["results"][0]["version"], 1)

    def test_runtime_record_event_and_summary_expose_event_bus(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            event = self.run_cli(
                "runtime-record-event",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-event",
                "--goal-id",
                "goal-event",
                "--event-type",
                "UserRequest",
                "--source",
                "test",
                "--summary",
                "User asked for a kernel step.",
                "--payload-json",
                '{"request":"kernel"}',
            )
            self.assertTrue(event["ok"])
            self.assertEqual(event["event_type"], "UserRequest")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "event",
            )
            self.assertEqual(listed["results"][0]["event_type"], "UserRequest")
            self.assertEqual(listed["results"][0]["run_id"], "run-event")

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertEqual(summary["recent_events"][0]["event_type"], "UserRequest")

    def test_event_bus_scheduler_and_resource_manager_form_closed_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "goal-os-loop",
                "--objective",
                "Exercise OS loop services",
            )
            published = self.run_cli(
                "runtime-publish-event",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
                "--id",
                "event-msg-loop",
                "--topic",
                "scheduler.tick",
                "--subscriber",
                "scheduler",
                "--event-type",
                "KernelStep",
                "--summary",
                "Scheduler should inspect queue.",
                "--payload-json",
                '{"tick":1}',
                "--priority",
                "5",
            )
            self.assertTrue(published["ok"], published)

            polled = self.run_cli(
                "runtime-poll-events",
                "--db",
                db,
                "--project",
                "agent-os",
                "--subscriber",
                "scheduler",
                "--deliver",
            )
            self.assertEqual(polled["messages"][0]["id"], "event-msg-loop")
            self.assertEqual(polled["messages"][0]["status"], "delivered")

            final_with_message = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
            )
            self.assertIn("unacknowledged event messages", final_with_message["missing"])

            acked = self.run_cli(
                "runtime-ack-event",
                "--db",
                db,
                "--project",
                "agent-os",
                "--id",
                "event-msg-loop",
                "--ok",
            )
            self.assertTrue(acked["ok"], acked)

            lease = self.run_cli(
                "runtime-request-resource",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
                "--id",
                "lease-workspace",
                "--resource-type",
                "workspace",
                "--resource-key",
                "repo",
                "--reason",
                "Protect workspace mutation window.",
            )
            self.assertTrue(lease["ok"], lease)

            scheduled = self.run_cli(
                "runtime-schedule",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
                "--id",
                "schedule-review",
                "--action-type",
                "verify",
                "--assigned-role",
                "verifier",
                "--required-resources",
                "workspace:repo",
                "--priority",
                "10",
                "--reason",
                "Verify after workspace lease is free.",
            )
            self.assertTrue(scheduled["ok"], scheduled)

            blocked_next = self.run_cli(
                "runtime-scheduler-next",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
            )
            self.assertFalse(blocked_next["ok"], blocked_next)
            self.assertEqual(blocked_next["blockers"][0]["reason"], "resources-busy")

            final_with_work = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
            )
            self.assertIn("open schedule items", final_with_work["missing"])
            self.assertIn("resource lease not released", final_with_work["missing"])

            released = self.run_cli(
                "runtime-release-resource",
                "--db",
                db,
                "--project",
                "agent-os",
                "--id",
                "lease-workspace",
                "--reason",
                "Verification can proceed.",
            )
            self.assertTrue(released["ok"], released)

            runnable = self.run_cli(
                "runtime-scheduler-next",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-os-loop",
                "--advance",
            )
            self.assertTrue(runnable["ok"], runnable)
            self.assertEqual(runnable["selected"]["id"], "schedule-review")
            self.assertEqual(runnable["selected"]["status"], "running")

            completed = self.run_cli(
                "runtime-schedule-complete",
                "--db",
                db,
                "--project",
                "agent-os",
                "--id",
                "schedule-review",
                "--ok",
                "--evidence",
                "Scheduler queue item completed.",
            )
            self.assertTrue(completed["ok"], completed)

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertEqual(summary["recent_event_messages"][0]["status"], "acknowledged")
            self.assertEqual(summary["recent_schedule_items"][0]["status"], "completed")
            self.assertEqual(summary["recent_resource_leases"][0]["status"], "released")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "schedule-item",
                "--status",
                "completed",
            )
            self.assertEqual(listed["results"][0]["id"], "schedule-review")

    def test_kernel_step_records_goal_run_tasks_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "kernel-step",
                "--db",
                db,
                "--run-id",
                "kernel-run",
                "--goal-id",
                "kernel-goal",
                "--project",
                "agent-os",
                "--request",
                "Implement phone login",
                "--capability-status",
                "absent",
                "--files",
                "src/pages/Login.tsx",
                "server/auth.ts",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["run_id"], "kernel-run")
            self.assertEqual(result["goal_id"], "kernel-goal")
            self.assertEqual(result["next_action"], "present-plan")
            self.assertGreaterEqual(len(result["event_ids"]), 5)

            conn = sqlite3.connect(db)
            try:
                counts = {
                    table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "agent_events",
                        "runtime_contexts",
                        "runtime_runs",
                        "agent_goals",
                        "agent_tasks",
                        "policy_decisions",
                        "verification_runs",
                    )
                }
                event_types = {
                    row[0]
                    for row in conn.execute(
                        "SELECT event_type FROM agent_events WHERE run_id = ?",
                        ("kernel-run",),
                    ).fetchall()
                }
            finally:
                conn.close()

            for table, count in counts.items():
                self.assertGreater(count, 0, table)
            self.assertIn("KernelStep", event_types)
            self.assertIn("TaskPlanned", event_types)
            self.assertIn("VerificationPlanned", event_types)

    def test_runtime_transition_updates_state_and_emits_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "goal-transition",
                "--objective",
                "Transition goal",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "task",
                "--project",
                "agent-os",
                "--id",
                "task-transition",
                "--goal-id",
                "goal-transition",
                "--title",
                "Transition task",
            )
            transitioned = self.run_cli(
                "runtime-transition",
                "--db",
                db,
                "--project",
                "agent-os",
                "--entity-type",
                "task",
                "--id",
                "task-transition",
                "--goal-id",
                "goal-transition",
                "--status",
                "in_progress",
                "--summary",
                "Task moved to in progress",
            )
            self.assertTrue(transitioned["ok"])

            conn = sqlite3.connect(db)
            try:
                task_status = conn.execute(
                    "SELECT status FROM agent_tasks WHERE id = ?",
                    ("task-transition",),
                ).fetchone()[0]
                event_row = conn.execute(
                    "SELECT event_type, summary FROM agent_events WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                    ("task-transition",),
                ).fetchone()
            finally:
                conn.close()

            self.assertEqual(task_status, "in_progress")
            self.assertEqual(event_row[0], "TaskStateChanged")
            self.assertEqual(event_row[1], "Task moved to in progress")

    def test_runtime_workspace_snapshot_reports_workspace_state(self) -> None:
        result = self.run_cli(
            "runtime-workspace-snapshot",
            "--project",
            "agent-os",
        )
        self.assertTrue(result["ok"])
        self.assertIn("root", result)
        self.assertIn("git", result)
        self.assertIn("docs", result)
        self.assertIn("runtime", result)
        self.assertIn("files", result)

    def test_kernel_step_includes_workspace_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "kernel-step",
                "--db",
                db,
                "--run-id",
                "kernel-workspace",
                "--goal-id",
                "goal-workspace",
                "--project",
                "agent-os",
                "--request",
                "Inspect workspace",
                "--capability-status",
                "complete",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertIn("workspace", result)
            self.assertIn("git", result["workspace"])
            self.assertIn("docs", result["workspace"])
            self.assertIn("runtime", result["workspace"])

    def test_runtime_rank_context_orders_items_by_relevance(self) -> None:
        result = self.run_cli(
            "runtime-rank-context",
            "--project",
            "agent-os",
            "--request",
            "Implement phone login",
            "--files",
            "src/pages/Login.tsx",
            "server/auth.ts",
        )
        self.assertTrue(result["ok"])
        ranked = result["ranked"]
        self.assertGreaterEqual(len(ranked), 2)
        self.assertEqual(ranked[0]["kind"], "request")
        self.assertEqual(ranked[1]["kind"], "context")
        self.assertIn("context", {item["source"] for item in ranked})

    def test_runtime_run_records_full_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--project",
                "agent-os",
                "--request",
                "Implement phone login",
                "--capability",
                "phone-login",
                "--term",
                "phone",
                "login",
                "auth",
                "--files",
                "src/pages/Login.tsx",
                "server/auth.ts",
                "--signal",
                "auth",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["context"]["scale"], "L3")
            self.assertGreaterEqual(len(result["tasks"]), 5)
            self.assertTrue(result["verification_checks"])
            self.assertIsNotNone(result["recovery_strategy"])

            conn = sqlite3.connect(db)
            try:
                counts = {
                    table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "runtime_contexts",
                        "runtime_runs",
                        "agent_goals",
                        "agent_tasks",
                        "capability_nodes",
                        "policy_decisions",
                        "skill_recommendations",
                        "verification_runs",
                        "recovery_points",
                    )
                }
            finally:
                conn.close()
            for table, count in counts.items():
                self.assertGreater(count, 0, table)

    def test_runtime_run_final_check_can_be_scoped_by_run_after_completing_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-scope",
                "--goal-id",
                "goal-scope",
                "--project",
                "agent-os",
                "--request",
                "Implement phone login",
                "--capability",
                "phone-login",
                "--term",
                "phone",
                "login",
                "auth",
                "--files",
                "src/pages/Login.tsx",
                "server/auth.ts",
                "--record",
            )
            first_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-scope",
                "--require-recovery",
                "--require-skills",
            )
            self.assertFalse(first_check["ok"])
            self.assertGreater(first_check["open_tasks"], 0)
            self.assertIn("pipeline_stages", first_check)
            self.assertTrue(any(stage["name"] == "plan" for stage in first_check["pipeline_stages"]))

            for index in range(1, len(result["tasks"]) + 1):
                self.run_cli(
                    "runtime-complete-task",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--id",
                    f"run-scope-task-{index}",
                    "--evidence",
                    "completed in test",
                    "--complete-goal",
                )

            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-scope",
                "--require-recovery",
                "--require-skills",
            )
            self.assertTrue(final_check["ok"], final_check)
            self.assertEqual(final_check["goal_id"], "goal-scope")
            self.assertEqual(final_check["run_id"], "run-scope")
            self.assertIn("pipeline_stages", final_check)
            self.assertTrue(any(stage["name"] == "closeout" for stage in final_check["pipeline_stages"]))

            strict_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-scope",
                "--require-docs",
                "--require-memory",
            )
            self.assertFalse(strict_check["ok"])
            self.assertIn("documentation workspace", strict_check["missing"])
            self.assertIn("memory items", strict_check["missing"])

            pipeline = self.run_cli(
                "runtime-pipeline",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-scope",
            )
            self.assertTrue(pipeline["ok"])
            stage_names = {stage["name"] for stage in pipeline["stages"]}
            self.assertTrue({"plan", "act", "observe", "verify", "document", "learn", "recover", "closeout"}.issubset(stage_names))

    def test_skill_router_reads_skill_metadata(self) -> None:
        result = self.run_cli(
            "runtime-select-skills",
            "--project",
            "agent-os",
            "--task-layer",
            "API",
            "--stack",
            "Node",
        )
        api_skill = next(item for item in result["skills"] if item["skill_name"] == "api-change")
        self.assertIn("API Layer", api_skill["rationale"])
        self.assertEqual(api_skill["manifest_status"], "valid")
        self.assertEqual(api_skill["manifest_path"], "skills/api-change/SKILL.md")

    def test_skill_runtime_validates_manifests_and_records_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_dir = root / "skills"
            valid_dir = skills_dir / "valid-skill"
            invalid_dir = skills_dir / "invalid-skill"
            valid_dir.mkdir(parents=True)
            invalid_dir.mkdir(parents=True)
            (valid_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: valid-skill",
                        "version: 1.2.3",
                        "description: Validates a package skill.",
                        "dependencies: []",
                        "triggers:",
                        "- validation",
                        "---",
                        "",
                        "# When to Use",
                        "- Use when validation is needed.",
                        "",
                        "# Steps",
                        "1. Inspect.",
                    ]
                ),
                encoding="utf-8",
            )
            (invalid_dir / "SKILL.md").write_text("# Broken Skill\n\nNo frontmatter.\n", encoding="utf-8")
            db = str(root / "runtime.db")

            result = self.run_cli(
                "runtime-validate-skills",
                "--db",
                db,
                "--project",
                "agent-os",
                "--skills-dir",
                str(skills_dir),
                "--skill",
                "valid-skill",
                "invalid-skill",
                "missing-skill",
                "--record",
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["status_counts"]["valid"], 1)
            self.assertEqual(result["status_counts"]["invalid"], 1)
            self.assertEqual(result["status_counts"]["missing"], 1)
            valid = next(item for item in result["skills"] if item["skill_name"] == "valid-skill")
            self.assertEqual(valid["version"], "1.2.3")
            self.assertEqual(result["dependency_graph"]["valid-skill"]["dependencies"], [])
            self.assertTrue(any(item["skill_name"] == "valid-skill" for item in result["trigger_matches"]))
            invalid = next(item for item in result["skills"] if item["skill_name"] == "invalid-skill")
            self.assertIn("missing frontmatter", invalid["issues"])
            missing = next(item for item in result["skills"] if item["skill_name"] == "missing-skill")
            self.assertIn("missing SKILL.md", missing["issues"])

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "skill",
                "--status",
                "valid",
            )
            self.assertTrue(listed["ok"])
            self.assertEqual(len(listed["results"]), 1)
            self.assertEqual(listed["results"][0]["skill_name"], "valid-skill")

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertTrue(any(item["skill_name"] == "valid-skill" for item in summary["recent_skills"]))

    def test_skill_runtime_blocks_missing_dependencies_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_dir = root / "skills"
            alpha_dir = skills_dir / "alpha"
            beta_dir = skills_dir / "beta"
            alpha_dir.mkdir(parents=True)
            beta_dir.mkdir(parents=True)
            (alpha_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: alpha",
                        "version: 1.0.0",
                        "description: Alpha API capability.",
                        "dependencies:",
                        "- missing-base",
                        "conflicts:",
                        "- beta",
                        "triggers:",
                        "- api login",
                        "---",
                        "",
                        "# When to Use",
                        "- Use when api login work is requested.",
                        "",
                        "# Steps",
                        "1. Check contract.",
                    ]
                ),
                encoding="utf-8",
            )
            (beta_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: beta",
                        "version: 1.0.0",
                        "description: Beta API capability.",
                        "triggers:",
                        "- login",
                        "---",
                        "",
                        "# When to Use",
                        "- Use when login work is requested.",
                        "",
                        "# Steps",
                        "1. Check flow.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cli(
                "runtime-validate-skills",
                "--project",
                "agent-os",
                "--skills-dir",
                str(skills_dir),
                "--skill",
                "alpha",
                "beta",
                "--request",
                "implement api login",
                "--task-layer",
                "API",
                "--stack",
                "Node",
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["dependency_graph"]["alpha"]["missing_dependencies"], ["missing-base"])
            self.assertTrue(result["conflicts"])
            self.assertTrue(any("declares conflict" in item for item in result["blockers"]))
            alpha_match = next(item for item in result["trigger_matches"] if item["skill_name"] == "alpha")
            self.assertTrue(alpha_match["matched"])
            self.assertGreater(alpha_match["score"], 0)

    def test_skill_router_explains_trigger_selection_and_blocks_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skills_dir = root / "skills"
            api_dir = skills_dir / "api-change"
            beta_dir = skills_dir / "beta"
            api_dir.mkdir(parents=True)
            beta_dir.mkdir(parents=True)
            (api_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: api-change",
                        "version: 2.0.0",
                        "description: API changes.",
                        "conflicts:",
                        "- beta",
                        "triggers:",
                        "- phone login",
                        "---",
                        "",
                        "# When to Use",
                        "- Use for phone login API changes.",
                        "",
                        "# Steps",
                        "1. Check API.",
                    ]
                ),
                encoding="utf-8",
            )
            (beta_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: beta",
                        "version: 1.0.0",
                        "description: Login helper.",
                        "triggers:",
                        "- phone login",
                        "---",
                        "",
                        "# When to Use",
                        "- Use for phone login work.",
                        "",
                        "# Steps",
                        "1. Check helper.",
                    ]
                ),
                encoding="utf-8",
            )

            result = self.run_cli(
                "runtime-select-skills",
                "--project",
                "agent-os",
                "--skills-dir",
                str(skills_dir),
                "--request",
                "implement phone login",
                "--task-layer",
                "API",
                "--stack",
                "Node",
            )

            self.assertFalse(result["ok"])
            api_skill = next(item for item in result["skills"] if item["skill_name"] == "api-change")
            self.assertEqual(api_skill["version"], "2.0.0")
            self.assertTrue(api_skill["trigger_evidence"])
            self.assertIn("api-change", result["dependency_graph"])
            self.assertTrue(any("api-change declares conflict with beta" in item for item in result["blockers"]))

    def test_model_runtime_records_provider_adapter_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            recorded = self.run_cli(
                "runtime-run-model",
                "--db",
                db,
                "--project",
                "agent-os",
                "--provider",
                "openai",
                "--model",
                "gpt-5",
                "--operation",
                "planning",
                "--status",
                "passed",
                "--input-tokens",
                "120",
                "--output-tokens",
                "80",
                "--cost-estimate",
                "0.01",
                "--prompt-summary",
                "Plan runtime work.",
                "--response-summary",
                "Produced a plan.",
                "--record-only",
            )
            self.assertTrue(recorded["ok"])
            self.assertEqual(recorded["adapter"], "openai-model-adapter")

            providerless_env = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "GOOGLE_API_KEY",
                    "GEMINI_API_KEY",
                    "QWEN_API_KEY",
                    "DASHSCOPE_API_KEY",
                    "DEEPSEEK_API_KEY",
                }
            }
            blocked_completed = subprocess.run(
                [
                    sys.executable,
                    str(AGENT_RUNTIME),
                    "runtime-run-model",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--provider",
                    "anthropic",
                    "--model",
                    "claude-opus",
                    "--operation",
                    "review",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                env=providerless_env,
            )
            self.assertEqual(blocked_completed.returncode, 0, blocked_completed.stderr)
            blocked = json.loads(blocked_completed.stdout)
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["failure_detail"], "missing-provider-config:ANTHROPIC_API_KEY")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "model",
                "--status",
                "passed",
            )
            self.assertEqual(len(listed["results"]), 1)
            self.assertEqual(listed["results"][0]["provider"], "openai")
            self.assertEqual(listed["results"][0]["model_name"], "gpt-5")

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            providers = {item["provider"] for item in summary["recent_models"]}
            self.assertTrue({"openai", "anthropic"}.issubset(providers))

    def test_model_runtime_executes_mock_adapter_and_blocks_missing_provider_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            mock = self.run_cli(
                "runtime-run-model",
                "--db",
                db,
                "--project",
                "agent-os",
                "--provider",
                "mock",
                "--model",
                "mock-planner",
                "--operation",
                "planning",
                "--prompt",
                "Plan the runtime work.",
            )
            self.assertTrue(mock["ok"], mock)
            self.assertEqual(mock["status"], "passed")
            self.assertEqual(mock["diagnostics"]["status"], "ready")
            self.assertIn("prompt_sha256", mock["response_summary"])
            self.assertGreater(mock["input_tokens"], 0)

            blocked_env = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "GOOGLE_API_KEY",
                    "GEMINI_API_KEY",
                    "QWEN_API_KEY",
                    "DASHSCOPE_API_KEY",
                    "DEEPSEEK_API_KEY",
                }
            }
            blocked_completed = subprocess.run(
                [
                    sys.executable,
                    str(AGENT_RUNTIME),
                    "runtime-run-model",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--provider",
                    "openai",
                    "--model",
                    "gpt-5",
                    "--operation",
                    "inference",
                    "--prompt",
                    "Hello",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                env=blocked_env,
            )
            self.assertEqual(blocked_completed.returncode, 0, blocked_completed.stderr)
            blocked = json.loads(blocked_completed.stdout)
            self.assertFalse(blocked["ok"], blocked)
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["diagnostics"]["status"], "missing-secret")
            self.assertEqual(blocked["failure_detail"], "missing-provider-config:OPENAI_API_KEY")

    def test_model_runtime_redacts_secrets_from_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "runtime.db"
            fake_secret = "sk-" + "a" * 30
            completed = subprocess.run(
                [
                    sys.executable,
                    str(AGENT_RUNTIME),
                    "runtime-run-model",
                    "--db",
                    str(db_path),
                    "--project",
                    "agent-os",
                    "--provider",
                    "mock",
                    "--model",
                    "mock-safe",
                    "--prompt",
                    f"token={fake_secret}",
                    "--prompt-summary",
                    f"api_key={fake_secret}",
                    "--response-summary",
                    f"secret={fake_secret}",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
                env={**os.environ, "MODEL_API_KEY": fake_secret},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertTrue(result["ok"], result)
            self.assertNotIn(fake_secret, completed.stdout)

            conn = sqlite3.connect(db_path)
            try:
                rows = conn.execute(
                    "SELECT prompt_summary, response_summary, evidence FROM model_runs WHERE project = ?",
                    ("agent-os",),
                ).fetchall()
            finally:
                conn.close()
            joined = "\n".join(str(value) for row in rows for value in row)
            self.assertNotIn(fake_secret, joined)
            self.assertIn("[REDACTED]", joined)

    def test_subagent_runtime_records_role_boundaries_and_handoffs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            planned = self.run_cli(
                "runtime-run-subagent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--role",
                "planner",
                "--status",
                "planned",
                "--input-summary",
                "Break down Model Runtime work.",
                "--boundary",
                "Plan only; do not edit files.",
                "--handoff-to",
                "executor",
            )
            self.assertTrue(planned["ok"])
            self.assertEqual(planned["handoff_to"], "executor")

            completed = self.run_cli(
                "runtime-run-subagent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--role",
                "reviewer",
                "--status",
                "completed",
                "--input-summary",
                "Review runtime diff.",
                "--output-summary",
                "No blocking issue found.",
                "--boundary",
                "Review only; do not modify implementation.",
                "--evidence",
                "Checked schema and CLI paths.",
            )
            self.assertTrue(completed["ok"])

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "subagent",
                "--status",
                "planned",
            )
            self.assertEqual(len(listed["results"]), 1)
            self.assertEqual(listed["results"][0]["role"], "planner")
            self.assertEqual(listed["results"][0]["boundary"], "Plan only; do not edit files.")

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            roles = {item["role"] for item in summary["recent_subagents"]}
            self.assertTrue({"planner", "reviewer"}.issubset(roles))

    def test_subagent_runtime_plans_chain_and_runs_reviewer_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            planned = self.run_cli(
                "runtime-plan-subagents",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-subagents",
                "--run-id",
                "run-subagents",
                "--request",
                "Implement and verify runtime work.",
                "--role",
                "planner",
                "executor",
                "reviewer",
                "verifier",
                "--task-prefix",
                "chain",
            )
            self.assertTrue(planned["ok"])
            self.assertEqual([item["role"] for item in planned["subagents"]], ["planner", "executor", "reviewer", "verifier"])
            self.assertEqual(planned["subagents"][0]["handoff_to"], "executor")
            self.assertEqual(planned["subagents"][-1]["handoff_to"], None)

            reviewer = self.run_cli(
                "runtime-run-subagent-role",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-subagents",
                "--run-id",
                "run-subagents",
                "--task-id",
                "chain-3-reviewer",
                "--role",
                "reviewer",
                "--diff-text",
                "+TODO: finish this\n+console.log('debug')",
                "--boundary",
                "Review only.",
            )
            self.assertTrue(reviewer["ok"])
            findings = reviewer["evidence"]["findings"]
            self.assertEqual(len(findings), 2)
            self.assertTrue(any(item["category"] == "incomplete-work" for item in findings))

            verifier = self.run_cli(
                "runtime-run-subagent-role",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-subagents",
                "--run-id",
                "run-subagents",
                "--task-id",
                "chain-4-verifier",
                "--role",
                "verifier",
                "--command",
                "python -m py_compile scripts/agent-runtime.py",
                "--scope",
                "subagent verifier compile",
                "--boundary",
                "Verify only.",
            )
            self.assertTrue(verifier["ok"], verifier)
            self.assertIsNotNone(verifier["verification_id"])
            self.assertEqual(verifier["evidence"]["verification"]["result"], "passed")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "subagent",
                "--goal-id",
                "goal-subagents",
            )
            self.assertGreaterEqual(len(listed["results"]), 6)

            conn = sqlite3.connect(db)
            try:
                verification_count = conn.execute(
                    "SELECT COUNT(*) FROM verification_runs WHERE project = ? AND goal_id = ?",
                    ("agent-os", "goal-subagents"),
                ).fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(verification_count, 1)

    def test_subagent_runtime_supports_documentation_and_memory_recorders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            planned = self.run_cli(
                "runtime-plan-subagents",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-recorder-subagents",
                "--run-id",
                "run-recorder-subagents",
                "--request",
                "Update docs and memory without blocking the main agent.",
                "--role",
                "documentation-recorder",
                "memory-recorder",
                "--task-prefix",
                "recorder",
            )
            self.assertTrue(planned["ok"])
            self.assertEqual(
                [item["role"] for item in planned["subagents"]],
                ["documentation-recorder", "memory-recorder"],
            )
            self.assertEqual(planned["subagents"][0]["handoff_to"], "memory-recorder")
            self.assertIn("documentation", planned["subagents"][0]["boundary"])
            self.assertIn("memory", planned["subagents"][1]["boundary"])

    def test_adapter_layer_registers_host_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter_file = root / "adapter.py"
            adapter_file.write_text("print('adapter')\n", encoding="utf-8")
            db = str(root / "runtime.db")

            registered = self.run_cli(
                "runtime-register-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "vscode",
                "--adapter-name",
                "vscode-extension",
                "--entrypoint",
                str(adapter_file),
                "--capability",
                "install",
                "status-panel",
                "inject-agent-os",
                "--config-path",
                "package.json",
            )
            self.assertTrue(registered["ok"])
            self.assertEqual(registered["status"], "available")
            self.assertIn("dashboard", registered["capability_evaluation"]["unavailable_protocol_capabilities"])

            invalid = self.run_cli(
                "runtime-register-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "codex",
                "--adapter-name",
                "missing-entrypoint",
                "--entrypoint",
                str(root / "missing.py"),
            )
            self.assertFalse(invalid["ok"])
            self.assertEqual(invalid["status"], "invalid")
            self.assertIn("missing capability declaration", invalid["issues"])

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "adapter",
                "--status",
                "available",
            )
            self.assertEqual(len(listed["results"]), 1)
            self.assertEqual(listed["results"][0]["host_type"], "vscode")

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            hosts = {item["host_type"] for item in summary["recent_adapters"]}
            self.assertTrue({"vscode", "codex"}.issubset(hosts))

    def test_host_adapter_detects_supported_and_missing_capabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            registered = self.run_cli(
                "runtime-register-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "vscode",
                "--adapter-name",
                "vscode-panel",
                "--capability",
                "inject-agent-os",
                "dashboard",
                "report",
                "runtime-cli",
                "--require-capability",
                "dashboard",
                "report",
            )
            self.assertTrue(registered["ok"], registered)
            self.assertEqual(registered["capability_evaluation"]["missing_capabilities"], [])

            supported = self.run_cli(
                "runtime-detect-host-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "vscode",
                "--require-capability",
                "dashboard",
                "report",
            )
            self.assertTrue(supported["ok"], supported)
            self.assertEqual(supported["supported"], ["vscode-panel"])

            missing = self.run_cli(
                "runtime-detect-host-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "vscode",
                "--require-capability",
                "doctor",
                "status-panel",
            )
            self.assertFalse(missing["ok"], missing)
            unsupported = missing["unsupported"][0]
            self.assertEqual(unsupported["adapter_name"], "vscode-panel")
            self.assertEqual(unsupported["missing_capabilities"], ["doctor", "status-panel"])

    def test_compatibility_matrix_reports_models_hosts_and_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-register-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "claude",
                "--adapter-name",
                "claude-cli",
                "--capability",
                "shell",
                "git",
                "runtime-cli",
                "skills",
                "memory",
                "tool-runtime",
                "subagent-runtime",
            )
            matrix = self.run_cli(
                "runtime-compatibility-matrix",
                "--db",
                db,
                "--project",
                "agent-os",
                "--provider",
                "mock",
                "qwen",
                "--host-type",
                "claude",
                "qwen",
            )
            providers = {item["provider"]: item for item in matrix["providers"]}
            self.assertEqual(providers["mock"]["status"], "ready")
            self.assertEqual(providers["qwen"]["adapter"], "qwen-model-adapter")
            hosts = {item["host_type"]: item for item in matrix["hosts"]}
            self.assertEqual(hosts["claude"]["entrypoint"], "CLAUDE.md")
            self.assertEqual(hosts["claude"]["status"], "compatible")
            self.assertEqual(hosts["qwen"]["entrypoint"], "QWEN.md")

    def test_governance_proposal_records_human_review_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            proposal = self.run_cli(
                "runtime-governance-proposal",
                "--db",
                db,
                "--project",
                "agent-os",
                "--name",
                "intent-drift-policy",
                "--source-type",
                "rule",
                "--trigger",
                "Repeated diagnosis-to-mutation drift",
                "--evidence",
                "Two blocked action proposals and an open drift",
                "--validation",
                "runtime-final-check blocks open drift",
                "--scope",
                "Mutation Authorization Gate",
                "--boundary",
                "Do not auto-promote without human review",
                "--ready-for-review",
            )
            self.assertTrue(proposal["ok"], proposal)
            self.assertFalse(proposal["auto_promote"])
            self.assertEqual(proposal["review_result"], "requires-human-review")

            reviews = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "improvement",
                "--status",
                "reviewing",
            )
            self.assertEqual(reviews["results"][0]["candidate_name"], "intent-drift-policy")

    def test_observability_metrics_calculates_quality_signals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--tool-type",
                "shell",
                "--adapter",
                "shell-adapter",
                "--command",
                "python -m py_compile missing.py",
            )
            self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--tool-type",
                "shell",
                "--adapter",
                "shell-adapter",
                "--command",
                "python -m py_compile scripts/agent-runtime.py",
            )
            self.run_cli(
                "runtime-run-model",
                "--db",
                db,
                "--project",
                "agent-os",
                "--provider",
                "openai",
                "--model",
                "gpt-5",
                "--operation",
                "review",
                "--status",
                "failed",
                "--duration-ms",
                "20",
                "--failure-type",
                "unknown",
                "--record-only",
            )
            self.run_cli(
                "runtime-run-model",
                "--db",
                db,
                "--project",
                "agent-os",
                "--provider",
                "openai",
                "--model",
                "gpt-5",
                "--operation",
                "review",
                "--status",
                "passed",
                "--duration-ms",
                "40",
                "--record-only",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--scope",
                "unit",
                "--command",
                "python -m unittest",
                "--result",
                "failed",
                "--evidence",
                "first run failed",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--scope",
                "unit",
                "--command",
                "python -m unittest",
                "--result",
                "passed",
                "--evidence",
                "second run passed",
            )

            metrics = self.run_cli(
                "runtime-metrics",
                "--db",
                db,
                "--project",
                "agent-os",
                "--record",
            )
            self.assertTrue(metrics["ok"])
            self.assertEqual(metrics["metrics"]["tool_call_count"], 2)
            self.assertEqual(metrics["metrics"]["model_call_count"], 2)
            self.assertEqual(metrics["metrics"]["verification_count"], 2)
            self.assertEqual(metrics["metrics"]["retry_count"], 3)
            self.assertEqual(metrics["metrics"]["verification_pass_rate"], 0.5)
            self.assertGreater(metrics["metrics"]["failure_rate"], 0)

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "metrics",
            )
            self.assertEqual(len(listed["results"]), 1)
            self.assertEqual(listed["results"][0]["retry_count"], 3)

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertEqual(summary["recent_metrics"][0]["retry_count"], 3)

    def test_quality_trends_reports_failure_pass_and_docs_rates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--scope",
                "unit",
                "--command",
                "python -m unittest",
                "--result",
                "passed",
                "--evidence",
                "passed",
            )
            self.run_cli(
                "runtime-metrics",
                "--db",
                db,
                "--project",
                "agent-os",
                "--record",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--scope",
                "docs",
                "--command",
                "check docs",
                "--result",
                "failed",
                "--evidence",
                "docs missing",
            )
            self.run_cli(
                "runtime-metrics",
                "--db",
                db,
                "--project",
                "agent-os",
                "--request",
                "Update API documentation",
                "--files",
                "src/api/phone.ts",
                "--record",
            )

            trends = self.run_cli(
                "runtime-quality-trends",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertEqual(trends["trends"]["sample_count"], 2)
            self.assertIsNotNone(trends["trends"]["average_failure_rate"])
            self.assertIsNotNone(trends["trends"]["average_verification_pass_rate"])
            self.assertEqual(trends["trends"]["docs_missing_or_stale_count"], 1)
            self.assertEqual(trends["trends"]["docs_missing_rate"], 0.5)
            self.assertTrue(trends["trends"]["failure_rate_series"])
            self.assertTrue(trends["trends"]["verification_pass_rate_series"])
            self.assertTrue(any(cluster["type"] == "documentation-drift" for cluster in trends["trends"]["failure_clusters"]))

    def test_quality_score_and_self_audit_record_governance_risks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "goal-quality",
                "--objective",
                "Score runtime quality",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "verification",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
                "--scope",
                "unit",
                "--command",
                "python -m unittest",
                "--result",
                "failed",
                "--evidence",
                "failed before fix",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "action-proposal",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
                "--id",
                "action-quality",
                "--action-type",
                "patch",
                "--tool",
                "patch.apply",
                "--reason",
                "blocked action",
                "--status",
                "blocked",
            )
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "schedule-item",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
                "--id",
                "schedule-quality",
                "--action-type",
                "verify",
                "--status",
                "queued",
            )

            score = self.run_cli(
                "runtime-quality-score",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
                "--record",
                "--min-score",
                "90",
            )
            self.assertFalse(score["ok"], score)
            self.assertIn(score["grade"], {"D", "F"})
            self.assertLess(score["score"], 70)
            self.assertGreater(score["metrics"]["blocked_actions"], 0)

            audit = self.run_cli(
                "runtime-self-audit",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
                "--record",
            )
            self.assertFalse(audit["ok"], audit)
            finding_types = {finding["finding_type"] for finding in audit["findings"]}
            self.assertIn("blocked-action", finding_types)
            self.assertIn("open-scheduler-work", finding_types)

            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-quality",
            )
            self.assertIn("open self-audit findings", final_check["missing"])
            self.assertIn("quality score below threshold", final_check["missing"])

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertIn(summary["recent_quality_scores"][0]["grade"], {"D", "F"})
            self.assertEqual(summary["recent_self_audit_findings"][0]["status"], "open")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "quality-score",
            )
            self.assertIn(listed["results"][0]["grade"], {"D", "F"})

    def test_benchmark_records_thresholds_and_blocks_final_check_regressions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-record",
                "--db",
                db,
                "--kind",
                "goal",
                "--project",
                "agent-os",
                "--id",
                "goal-benchmark",
                "--objective",
                "Benchmark runtime",
            )
            failed = self.run_cli(
                "runtime-benchmark",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-benchmark",
                "--name",
                "dashboard-render",
                "--metric",
                "duration-ms",
                "--baseline-value",
                "100",
                "--current-value",
                "140",
                "--direction",
                "lower-is-better",
                "--unit",
                "ms",
                "--record",
            )
            self.assertFalse(failed["ok"], failed)
            self.assertEqual(failed["status"], "failed")

            quality = self.run_cli(
                "runtime-quality-score",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-benchmark",
                "--record",
            )
            self.assertGreater(quality["metrics"]["failed_benchmarks"], 0)

            audit = self.run_cli(
                "runtime-self-audit",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-benchmark",
                "--record",
            )
            self.assertIn("benchmark-regression", {item["finding_type"] for item in audit["findings"]})

            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-benchmark",
            )
            self.assertIn("benchmark regression", final_check["missing"])

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertEqual(summary["recent_benchmarks"][0]["status"], "failed")

    def test_policy_packs_validate_team_governance_pack(self) -> None:
        result = self.run_cli(
            "runtime-policy-packs",
            "--name",
            "core-governance",
        )
        self.assertTrue(result["ok"], result)
        pack = result["packs"][0]
        self.assertEqual(pack["status"], "valid")
        self.assertIn("rules/change-policy.md", pack["rules"])
        self.assertIn("workflows/agent-os-evolution.md", pack["workflows"])
        self.assertIn("Planning Gate", pack["gates"])

    def test_policy_packs_support_enable_disable_and_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packs_dir = root / "policy-packs"
            pack_dir = packs_dir / "team"
            pack_dir.mkdir(parents=True)
            (pack_dir / "policy-pack.json").write_text(
                json.dumps(
                    {
                        "name": "team",
                        "version": "1.0.0",
                        "description": "Team pack",
                        "rules": ["rules/change-policy.md"],
                        "workflows": ["workflows/feature-implementation.md"],
                        "gates": ["Planning Gate"],
                        "overrides": {"review": "required"},
                    }
                ),
                encoding="utf-8",
            )
            enabled = self.run_cli(
                "runtime-policy-packs",
                "--packs-dir",
                str(packs_dir),
                "--name",
                "team",
                "--action",
                "enable",
                "--override",
                "review=required",
            )
            self.assertTrue(enabled["ok"], enabled)
            self.assertIn("team", enabled["enabled"])
            self.assertEqual(enabled["packs"][0]["active_overrides"]["review"], "required")

            disabled = self.run_cli(
                "runtime-policy-packs",
                "--packs-dir",
                str(packs_dir),
                "--name",
                "team",
                "--action",
                "disable",
            )
            self.assertTrue(disabled["ok"], disabled)
            self.assertNotIn("team", disabled["enabled"])

    def test_policy_packs_detect_enabled_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packs_dir = root / "policy-packs"
            for name, conflicts in (("a", ["b"]), ("b", [])):
                pack_dir = packs_dir / name
                pack_dir.mkdir(parents=True)
                (pack_dir / "policy-pack.json").write_text(
                    json.dumps(
                        {
                            "name": name,
                            "version": "1.0.0",
                            "description": f"{name} pack",
                            "rules": ["rules/change-policy.md"],
                            "workflows": ["workflows/feature-implementation.md"],
                            "gates": ["Planning Gate"],
                            "conflicts": conflicts,
                        }
                    ),
                    encoding="utf-8",
                )
            self.run_cli("runtime-policy-packs", "--packs-dir", str(packs_dir), "--name", "a", "--action", "enable")
            result = self.run_cli("runtime-policy-packs", "--packs-dir", str(packs_dir), "--name", "b", "--action", "enable")
            self.assertFalse(result["ok"])
            self.assertTrue(any("conflicts" in issue for issue in result["conflicts"]))

    def test_policy_packs_report_invalid_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packs_dir = Path(tmp) / "policy-packs"
            broken_dir = packs_dir / "broken"
            broken_dir.mkdir(parents=True)
            (broken_dir / "policy-pack.json").write_text(
                json.dumps(
                    {
                        "name": "broken",
                        "version": "1.0.0",
                        "description": "Broken pack",
                        "rules": ["rules/missing.md"],
                        "workflows": ["workflows/missing.md"],
                        "gates": ["Planning Gate"],
                    }
                ),
                encoding="utf-8",
            )
            result = self.run_cli(
                "runtime-policy-packs",
                "--packs-dir",
                str(packs_dir),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["packs"][0]["status"], "invalid")
            self.assertTrue(any("missing reference" in issue for issue in result["packs"][0]["issues"]))

    def test_security_check_reports_permission_and_sandbox_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "safe.txt").write_text("no secrets here\n", encoding="utf-8")
            result = self.run_cli(
                "runtime-security-check",
                "--root",
                str(root),
            )
            self.assertTrue(result["ok"], result)
            self.assertIn("tool_allowlist", result["permission_policy"])
            self.assertTrue(result["permission_policy"]["allow_unsafe_requires_user_approval"])
            self.assertIn("recommend_worktree_for", result["sandbox_strategy"])
            self.assertEqual(result["dangerous_command"]["risk"], "none")

    def test_security_check_detects_secret_like_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_secret = "abcdefghi" + "jklmnopqrstuvwxyz123456"
            (root / "config.env").write_text(f"API_KEY={fake_secret}\n", encoding="utf-8")
            result = self.run_cli(
                "runtime-security-check",
                "--root",
                str(root),
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["secret_scan"]["findings"][0]["type"], "generic_secret")
            self.assertEqual(result["secret_scan"]["findings"][0]["line"], 1)

    def test_security_check_supports_ignore_entropy_and_dangerous_command_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agent-os-security-ignore").write_text("ignored.env\n", encoding="utf-8")
            ignored_secret = "abcdefghi" + "jklmnopqrstuvwxyz123456"
            (root / "ignored.env").write_text(f"API_KEY={ignored_secret}\n", encoding="utf-8")
            entropy_secret = "".join(["a8F3kL9qZ2", "xP7mN4vR6", "tY1cB5hJ0", "sD9wQ2eU7iO3p"])
            (root / "config.env").write_text(f"SESSION={entropy_secret}\n", encoding="utf-8")
            result = self.run_cli(
                "runtime-security-check",
                "--root",
                str(root),
                "--command",
                "git reset --hard HEAD",
            )
            self.assertFalse(result["ok"])
            self.assertIn("ignored.env", result["secret_scan"]["ignored_patterns"])
            self.assertTrue(any(finding["type"] == "high_entropy" for finding in result["secret_scan"]["findings"]))
            self.assertTrue(result["dangerous_command"]["blocked"])
            self.assertEqual(result["dangerous_command"]["matches"][0]["type"], "destructive-git-reset")

    def test_vscode_distribution_team_and_release_product_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            vscode = self.run_cli(
                "runtime-vscode-protocol",
                "--project",
                "agent-os",
            )
            self.assertTrue(vscode["ok"])
            self.assertIn("dashboard", vscode["protocol"]["commands"])
            self.assertIn("The panel is not a chat runtime.", vscode["protocol"]["boundaries"])

            distribution = self.run_cli("runtime-distribution", "--channel", "vscode-plugin")
            self.assertTrue(distribution["ok"])
            self.assertEqual(distribution["channels"][0]["name"], "vscode-plugin")

            team = self.run_cli("runtime-team-workspace")
            self.assertTrue(team["ok"], team)
            self.assertEqual(team["team_workspace"]["bootstrap"]["status"], "passed")
            self.assertTrue(team["team_workspace"]["policy_packs"])

            release = self.run_cli(
                "runtime-release-check",
                "--db",
                db,
            )
            self.assertTrue(release["ok"], release)
            self.assertEqual(release["version"], "2.0.0")
            self.assertIn("python -m unittest tests.test_agent_runtime", release["required_tests"])

    def test_trace_report_exports_complete_runtime_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-trace",
                "--goal-id",
                "goal-trace",
                "--project",
                "agent-os",
                "--request",
                "Implement trace report",
                "--record",
            )
            self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--tool-type",
                "shell",
                "--command",
                "python -m py_compile scripts/agent-runtime.py",
            )
            self.run_cli(
                "runtime-run-model",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--provider",
                "openai",
                "--model",
                "gpt-5",
                "--status",
                "passed",
                "--record-only",
            )
            self.run_cli(
                "runtime-run-subagent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--role",
                "verifier",
                "--status",
                "completed",
                "--input-summary",
                "Verify trace output.",
                "--output-summary",
                "Trace contains runtime chain.",
                "--boundary",
                "Verification only.",
            )
            self.run_cli(
                "runtime-register-adapter",
                "--db",
                db,
                "--project",
                "agent-os",
                "--host-type",
                "codex",
                "--adapter-name",
                "codex-cli",
                "--capability",
                "runtime-trace",
            )
            self.run_cli(
                "runtime-metrics",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--record",
            )
            self.run_cli(
                "runtime-detect-intent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--intent-id",
                "intent-trace",
                "--request",
                "Investigate trace report",
                "--record",
            )
            self.run_cli(
                "runtime-propose-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--id",
                "action-trace",
                "--intent-id",
                "intent-trace",
                "--action-type",
                "read",
                "--tool",
                "file.read",
                "--reason",
                "Trace read action",
                "--validation-plan",
                "trace has intent chain",
            )
            self.run_cli(
                "runtime-record-feedback",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--intent-id",
                "intent-trace",
                "--proposal-id",
                "action-trace",
                "--summary",
                "Trace feedback recorded.",
            )
            self.run_cli(
                "runtime-revise-plan",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-trace",
                "--run-id",
                "run-trace",
                "--intent-id",
                "intent-trace",
                "--steps",
                "1. Include intent loop in trace.",
                "--status",
                "active",
            )

            trace = self.run_cli(
                "runtime-trace",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-trace",
                "--record",
            )
            self.assertTrue(trace["ok"])
            runtime_trace = trace["trace"]
            self.assertEqual(runtime_trace["goal_id"], "goal-trace")
            self.assertEqual(runtime_trace["run_id"], "run-trace")
            self.assertTrue(runtime_trace["timeline"])
            self.assertIsNotNone(runtime_trace["duration_ms"])
            self.assertRegex(runtime_trace["input_hash"], r"^[a-f0-9]{64}$")
            self.assertRegex(runtime_trace["output_hash"], r"^[a-f0-9]{64}$")
            self.assertGreater(runtime_trace["event_count"], 0)
            self.assertTrue(runtime_trace["tasks"])
            self.assertTrue(runtime_trace["intents"])
            self.assertTrue(runtime_trace["action_proposals"])
            self.assertTrue(runtime_trace["feedback"])
            self.assertTrue(runtime_trace["plan_versions"])
            self.assertTrue(runtime_trace["policies"])
            self.assertTrue(runtime_trace["skill_recommendations"])
            self.assertTrue(runtime_trace["tool_runs"])
            self.assertTrue(runtime_trace["model_runs"])
            self.assertTrue(runtime_trace["subagent_runs"])
            self.assertTrue(runtime_trace["host_adapters"])
            self.assertIn("metrics", runtime_trace)
            event_types = {item["event_type"] for item in runtime_trace["events"]}
            self.assertIn("TraceExported", event_types)
            timeline_sources = {item["source"] for item in runtime_trace["timeline"]}
            self.assertTrue({"intent", "action", "feedback", "plan"}.issubset(timeline_sources))

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "trace",
            )
            self.assertEqual(len(listed["results"]), 1)

    def test_runtime_orchestrator_runs_full_chain_and_exports_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-orchestrate",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-orchestrate",
                "--run-id",
                "run-orchestrate",
                "--request",
                "Run the complete orchestrator chain.",
                "--verification-command",
                "python -m py_compile scripts/agent-runtime.py",
            )
            self.assertTrue(result["ok"], result)
            trace = result["trace"]
            self.assertEqual(trace["run"]["status"], "completed")
            self.assertTrue(trace["skill_manifests"])
            self.assertTrue(trace["model_runs"])
            self.assertTrue(trace["subagent_runs"])
            self.assertTrue(trace["verifications"])
            self.assertTrue(trace["timeline"])
            self.assertRegex(trace["input_hash"], r"^[a-f0-9]{64}$")
            self.assertRegex(trace["output_hash"], r"^[a-f0-9]{64}$")
            task_statuses = {item["status"] for item in trace["tasks"]}
            self.assertEqual(task_statuses, {"completed"})
            event_types = {item["event_type"] for item in trace["events"]}
            self.assertTrue({"UserRequest", "ContextReady", "SkillValidated", "ModelRunRecorded", "VerificationPassed", "TraceExported"}.issubset(event_types))

    def test_capability_scan_detects_broken_api_backend_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api_dir = root / "src" / "api"
            backend_dir = root / "server" / "routes"
            api_dir.mkdir(parents=True)
            backend_dir.mkdir(parents=True)
            (api_dir / "phone.ts").write_text("fetch('/api/sms-send')\n", encoding="utf-8")
            (backend_dir / "auth.ts").write_text("router.post('/api/password-only', handler)\n", encoding="utf-8")

            result = self.run_cli(
                "runtime-scan-capability",
                "--project",
                "agent-os",
                "--name",
                "phone-login",
                "--term",
                "api",
                "--roots",
                str(root),
            )
            self.assertEqual(result["status"], "broken-chain")
            self.assertEqual(result["linkage"]["api_backend_overlap"], [])

    def test_policy_engine_includes_workspace_risk_signals(self) -> None:
        result = self.run_cli(
            "runtime-evaluate-policy",
            "--project",
            "agent-os",
            "--scale",
            "L2",
            "--capability-status",
            "complete",
            "--task-layer",
            "Runtime",
            "--files",
            "package.json",
        )
        self.assertIn("dependency-upgrade", result["evidence"])

    def test_validation_profile_and_runtime_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-report",
                "--goal-id",
                "goal-report",
                "--project",
                "agent-os",
                "--request",
                "Improve Runtime",
                "--capability",
                "runtime",
                "--term",
                "runtime",
                "--files",
                "scripts/agent-runtime.py",
                "--record",
            )
            profile = self.run_cli(
                "runtime-detect-validation-profile",
                "--project",
                "agent-os",
                "--stack",
                "Python",
                "--task-layer",
                "Runtime",
                "--files",
                "scripts/agent-runtime.py",
            )
            self.assertTrue(any(check["scope"] == "python tests" for check in profile["checks"]))
            self.run_cli(
                "runtime-detect-intent",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-report",
                "--run-id",
                "run-report",
                "--intent-id",
                "intent-report",
                "--request",
                "Analyze runtime report",
                "--record",
            )
            self.run_cli(
                "runtime-propose-action",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-report",
                "--run-id",
                "run-report",
                "--id",
                "action-report",
                "--intent-id",
                "intent-report",
                "--action-type",
                "read",
                "--tool",
                "file.read",
                "--reason",
                "Report read action",
                "--validation-plan",
                "report contains intent loop",
            )
            self.run_cli(
                "runtime-record-feedback",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-report",
                "--proposal-id",
                "action-report",
                "--summary",
                "Report feedback recorded.",
            )
            self.run_cli(
                "runtime-revise-plan",
                "--db",
                db,
                "--project",
                "agent-os",
                "--intent-id",
                "intent-report",
                "--steps",
                "1. Include intent loop in report.",
                "--status",
                "active",
            )

            report = self.run_cli(
                "runtime-report",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-report",
            )
            self.assertTrue(report["ok"])
            self.assertEqual(report["run"]["id"], "run-report")
            self.assertTrue(report["tasks"])
            self.assertEqual(report["intents"][0]["id"], "intent-report")
            self.assertEqual(report["action_proposals"][0]["id"], "action-report")
            self.assertEqual(report["feedback"][0]["summary"], "Report feedback recorded.")
            self.assertEqual(report["plan_versions"][0]["version"], 1)

    def test_runtime_check_docs_reports_freshness(self) -> None:
        result = self.run_cli(
            "runtime-check-docs",
            "--project",
            "agent-os",
            "--request",
            "Update API contract and docs",
            "--files",
            "src/api/phone.ts",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["docs_freshness"]["must_update"])

    def test_runtime_check_knowledge_reports_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-reflect",
                "--db",
                db,
                "--project",
                "agent-os",
                "--source-type",
                "manual",
                "--summary",
                "Memory says a phone login flow exists.",
                "--evidence",
                "Manual reflection evidence.",
            )
            result = self.run_cli(
                "runtime-check-knowledge",
                "--db",
                db,
                "--project",
                "agent-os",
                "--request",
                "Implement phone login docs",
                "--capability",
                "phone-login",
                "--files",
                "src/api/phone.ts",
            )
            self.assertTrue(result["ok"])
            self.assertIn("knowledge_conflict", result)
            self.assertIn("docs_freshness", result)

    def test_runtime_final_check_reports_stale_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-docs",
                "--goal-id",
                "goal-docs",
                "--project",
                "agent-os",
                "--request",
                "Update API contract and docs",
                "--capability",
                "api-docs",
                "--term",
                "api",
                "docs",
                "--files",
                "src/api/phone.ts",
                "--record",
            )
            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-docs",
                "--require-docs",
            )
            self.assertIn("docs missing", final_check["missing"])
            self.assertIn("docs_freshness", final_check)

    def test_runtime_verification_pipeline_builds_stages(self) -> None:
        result = self.run_cli(
            "runtime-verification-pipeline",
            "--project",
            "agent-os",
            "--request",
            "Implement phone login",
            "--stack",
            "React",
            "--task-layer",
            "UI",
            "Integration",
            "--scale",
            "L3",
            "--files",
            "src/pages/Login.tsx",
            "server/auth.ts",
        )
        self.assertTrue(result["ok"])
        stages = {stage["stage"] for stage in result["stages"]}
        self.assertIn("compile", stages)
        self.assertIn("test", stages)
        self.assertIn("review", stages)
        self.assertIn("smoke", stages)

    def test_scan_use_memory_reports_markdown_import_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-scan-capability",
                "--db",
                db,
                "--project",
                "unknown-project",
                "--name",
                "definitely-missing-capability",
                "--term",
                "definitely-missing-capability",
                "--roots",
                "scripts",
                "--use-memory",
            )
            self.assertIn("import-markdown --project unknown-project", result["memory_import_hint"])

    def test_verification_runner_records_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run-verification",
                "--db",
                db,
                "--project",
                "agent-os",
                "--command",
                "python -m py_compile scripts\\agent-runtime.py scripts\\agent_store.py",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"], "passed")
            self.assertEqual(result["exit_code"], 0)

    def test_tool_runtime_records_shell_and_blocks_unsafe_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            passed = self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--tool-type",
                "shell",
                "--command",
                "python -m py_compile scripts\\agent-runtime.py",
            )
            self.assertTrue(passed["ok"])
            self.assertEqual(passed["status"], "passed")
            self.assertEqual(passed["tool_type"], "shell")

            blocked = self.run_cli(
                "runtime-run-tool",
                "--db",
                db,
                "--project",
                "agent-os",
                "--tool-type",
                "shell",
                "--command",
                "echo unsafe",
            )
            self.assertFalse(blocked["ok"])
            self.assertEqual(blocked["status"], "blocked")
            self.assertEqual(blocked["failure_detail"], "policy-blocked")

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "tool",
            )
            self.assertEqual(len(listed["results"]), 2)

    def test_tool_runtime_executes_git_api_and_browser_adapters(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = b"""<!doctype html>
<html>
  <body>
    <h1>agent-os adapter ok</h1>
    <input id="name" />
    <button id="go" onclick="document.body.setAttribute('data-clicked','yes');document.getElementById('result').textContent='clicked-ok'">Go</button>
    <div id="result"></div>
  </body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                payload = self.rfile.read(length)
                body = b"received:" + payload
                self.send_response(201)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            try:
                git_result = self.run_cli(
                    "runtime-run-tool",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--tool-type",
                    "git",
                    "--git-action",
                    "branch",
                )
                self.assertTrue(git_result["ok"])
                self.assertEqual(git_result["tool_type"], "git")
                self.assertEqual(git_result["status"], "passed")

                api_result = self.run_cli(
                    "runtime-run-tool",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--tool-type",
                    "api",
                    "--target",
                    base_url,
                    "--method",
                    "POST",
                    "--body",
                    "hello",
                    "--expect-text",
                    "received:hello",
                )
                self.assertTrue(api_result["ok"], api_result)
                self.assertEqual(api_result["tool_type"], "api")
                self.assertEqual(api_result["exit_code"], 201)

                browser_click = self.run_cli(
                    "runtime-run-tool",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--tool-type",
                    "browser",
                    "--target",
                    base_url,
                    "--browser-action",
                    "click",
                    "--selector",
                    "#go",
                    "--expect-text",
                    "clicked-ok",
                )
                self.assertTrue(browser_click["ok"], browser_click)
                self.assertEqual(browser_click["tool_type"], "browser")
                self.assertIn("clicked #go", browser_click["stdout_summary"])

                browser_type = self.run_cli(
                    "runtime-run-tool",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--tool-type",
                    "browser",
                    "--target",
                    base_url,
                    "--browser-action",
                    "type",
                    "--selector",
                    "#name",
                    "--text",
                    "Agent OS",
                )
                self.assertTrue(browser_type["ok"], browser_type)
                self.assertIn("typed into #name", browser_type["stdout_summary"])

                screenshot = Path(tmp) / "browser.png"
                browser_screenshot = self.run_cli(
                    "runtime-run-tool",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--tool-type",
                    "browser",
                    "--target",
                    base_url,
                    "--browser-action",
                    "screenshot",
                    "--screenshot-path",
                    str(screenshot),
                )
                self.assertTrue(browser_screenshot["ok"], browser_screenshot)
                self.assertTrue(screenshot.exists())
            finally:
                server.shutdown()
                server.server_close()

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "tool",
            )
            tool_types = {row["tool_type"] for row in listed["results"]}
            self.assertTrue({"git", "api", "browser"}.issubset(tool_types))

    def test_verification_runner_classifies_failure_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run-verification",
                "--db",
                db,
                "--project",
                "agent-os",
                "--command",
                "python -c \"import sys; sys.stderr.write('AssertionError: mismatch'); sys.exit(1)\"",
                "--allow-unsafe",
                "--record",
            )
            self.assertFalse(result["ok"])
            self.assertEqual(result["result"], "failed")
            self.assertEqual(result["failure_type"], "implementation")
            self.assertEqual(result["failure_detail"], "assertion")
            self.assertIsNotNone(result["reflection_id"])
            self.assertIsNotNone(result["learning"]["memory_item_id"])
            self.assertIsNotNone(result["learning"]["candidate_id"])

            listed = self.run_cli(
                "runtime-list",
                "--db",
                db,
                "--project",
                "agent-os",
                "--kind",
                "reflection",
            )
            self.assertEqual(listed["results"][0]["source_type"], "failure")

    def test_recovery_checkpoint_can_be_marked_obsolete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            created = self.run_cli(
                "runtime-create-checkpoint",
                "--db",
                db,
                "--project",
                "agent-os",
                "--files",
                "scripts/agent-runtime.py",
            )
            self.assertTrue(created["ok"])
            marked = self.run_cli(
                "runtime-mark-recovery",
                "--db",
                db,
                "--id",
                str(created["id"]),
                "--status",
                "obsolete",
                "--reason",
                "validated",
            )
            self.assertTrue(marked["ok"])
            self.assertEqual(marked["status"], "obsolete")

    def test_runtime_reflect_records_manual_reflection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-reflect",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-reflect",
                "--source-type",
                "manual",
                "--summary",
                "Manual reflection for a stable workflow.",
                "--evidence",
                "Used when task completed cleanly.",
                "--pattern",
                "Keep this workflow as a reusable path.",
                "--next-step",
                "Promote the pattern into learning later.",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["reflection"]["source_type"], "manual")
            self.assertIsNotNone(result["learning"]["memory_item_id"])

            summary = self.run_cli(
                "runtime-summary",
                "--db",
                db,
                "--project",
                "agent-os",
            )
            self.assertTrue(summary["recent_reflections"])

    def test_runtime_run_marks_recovery_preparation_for_high_risk_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--project",
                "agent-os",
                "--request",
                "Update auth and payment flow",
                "--capability",
                "checkout-auth",
                "--term",
                "auth",
                "payment",
                "--files",
                "server/auth.ts",
                "server/payment.ts",
                "--record",
            )
            self.assertEqual(result["next_action"], "prepare-recovery")
            self.assertIsNotNone(result["recovery_strategy"])

            conn = sqlite3.connect(db)
            try:
                recovery_events = conn.execute(
                    "SELECT event_type FROM agent_events WHERE project = ? AND event_type = 'RecoveryPlanned'",
                    ("agent-os",),
                ).fetchall()
                recovery_rows = conn.execute(
                    "SELECT status FROM recovery_points WHERE project = ?",
                    ("agent-os",),
                ).fetchall()
            finally:
                conn.close()
            self.assertGreaterEqual(len(recovery_events), 1)
            self.assertGreaterEqual(len(recovery_rows), 1)

    def test_runtime_final_check_accepts_available_recovery_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--id",
                "run-recovery",
                "--goal-id",
                "goal-recovery",
                "--project",
                "agent-os",
                "--request",
                "Update auth and payment flow",
                "--capability",
                "checkout-auth",
                "--term",
                "auth",
                "payment",
                "--files",
                "server/auth.ts",
                "server/payment.ts",
                "--record",
            )
            self.assertTrue(result["ok"])
            checkpoint = self.run_cli(
                "runtime-create-checkpoint",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-recovery",
                "--task-id",
                "run-recovery-task-1",
                "--files",
                "server/auth.ts",
                "server/payment.ts",
            )
            self.assertTrue(checkpoint["ok"])
            for index in range(1, len(result["tasks"]) + 1):
                self.run_cli(
                    "runtime-complete-task",
                    "--db",
                    db,
                    "--project",
                    "agent-os",
                    "--id",
                    f"run-recovery-task-{index}",
                    "--evidence",
                    "completed in test",
                    "--complete-goal",
                )
            final_check = self.run_cli(
                "runtime-final-check",
                "--db",
                db,
                "--project",
                "agent-os",
                "--run-id",
                "run-recovery",
                "--require-recovery",
            )
            self.assertTrue(final_check["ok"], final_check)
            self.assertTrue(any(stage["name"] == "recover" and stage["status"] == "done" for stage in final_check["pipeline_stages"]))

    def test_improvement_review_reads_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_memory_cli(
                "candidate-upsert",
                "--db",
                db,
                "--name",
                "runtime-loop",
                "--project",
                "*",
                "--trigger",
                "L2+ task needs full Agent Runtime loop.",
                "--evidence",
                "Repeated planning/runtime gap.",
                "--validation",
                "CLI test coverage.",
                "--scope",
                "Agent OS runtime work.",
                "--boundary",
                "Not for L1 text edits.",
                "--increment",
                "2",
            )
            result = self.run_cli(
                "runtime-review-improvements",
                "--db",
                db,
                "--project",
                "*",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["reviews"][0]["recommendation"], "ready-for-human-review")

    def test_improvement_review_can_be_scoped_by_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            self.run_memory_cli(
                "candidate-upsert",
                "--db",
                db,
                "--name",
                "global-runtime-pattern",
                "--project",
                "agent-os",
                "--trigger",
                "Reusable runtime lesson.",
                "--evidence",
                "Global evidence.",
                "--validation",
                "Validated globally.",
                "--scope",
                "All runtime tasks.",
                "--boundary",
                "Not project-specific.",
                "--increment",
                "2",
            )
            self.run_memory_cli(
                "candidate-upsert",
                "--db",
                db,
                "--name",
                "goal-runtime-pattern",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-1",
                "--run-id",
                "run-1",
                "--trigger",
                "Goal-scoped runtime lesson.",
                "--evidence",
                "Goal evidence.",
                "--validation",
                "Validated in goal.",
                "--scope",
                "This goal.",
                "--boundary",
                "Only this goal chain.",
                "--increment",
                "2",
            )
            self.run_memory_cli(
                "candidate-upsert",
                "--db",
                db,
                "--name",
                "other-goal-pattern",
                "--project",
                "agent-os",
                "--goal-id",
                "goal-2",
                "--trigger",
                "Other goal lesson.",
                "--evidence",
                "Other evidence.",
                "--validation",
                "Other validation.",
                "--scope",
                "Other goal.",
                "--boundary",
                "Not goal-1.",
                "--increment",
                "2",
            )
            result = self.run_cli(
                "runtime-review-improvements",
                "--db",
                db,
                "--project",
                "agent-os",
                "--goal-id",
                "goal-1",
                "--run-id",
                "run-1",
                "--record",
            )
            self.assertTrue(result["ok"])
            names = {item["name"] for item in result["reviews"]}
            self.assertIn("global-runtime-pattern", names)
            self.assertIn("goal-runtime-pattern", names)
            self.assertNotIn("other-goal-pattern", names)
            self.assertEqual(result["goal_id"], "goal-1")


if __name__ == "__main__":
    unittest.main()
