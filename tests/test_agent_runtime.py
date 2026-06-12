import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME = ROOT / "scripts" / "agent-runtime.py"
MEMORY_TOOLS = ROOT / "scripts" / "memory-tools.py"


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

    def test_runtime_run_records_full_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            result = self.run_cli(
                "runtime-run",
                "--db",
                db,
                "--project",
                "codex-agent-os",
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
                "codex-agent-os",
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
                "codex-agent-os",
                "--run-id",
                "run-scope",
                "--require-recovery",
                "--require-skills",
            )
            self.assertFalse(first_check["ok"])
            self.assertGreater(first_check["open_tasks"], 0)

            for index in range(1, len(result["tasks"]) + 1):
                self.run_cli(
                    "runtime-complete-task",
                    "--db",
                    db,
                    "--project",
                    "codex-agent-os",
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
                "codex-agent-os",
                "--run-id",
                "run-scope",
                "--require-recovery",
                "--require-skills",
            )
            self.assertTrue(final_check["ok"], final_check)
            self.assertEqual(final_check["goal_id"], "goal-scope")
            self.assertEqual(final_check["run_id"], "run-scope")

    def test_skill_router_reads_skill_metadata(self) -> None:
        result = self.run_cli(
            "runtime-select-skills",
            "--project",
            "codex-agent-os",
            "--task-layer",
            "API",
            "--stack",
            "Node",
        )
        api_skill = next(item for item in result["skills"] if item["skill_name"] == "api-change")
        self.assertIn("API Layer", api_skill["rationale"])

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
                "codex-agent-os",
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
            "codex-agent-os",
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
                "codex-agent-os",
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
                "codex-agent-os",
                "--stack",
                "Python",
                "--task-layer",
                "Runtime",
                "--files",
                "scripts/agent-runtime.py",
            )
            self.assertTrue(any(check["scope"] == "python tests" for check in profile["checks"]))

            report = self.run_cli(
                "runtime-report",
                "--db",
                db,
                "--project",
                "codex-agent-os",
                "--run-id",
                "run-report",
            )
            self.assertTrue(report["ok"])
            self.assertEqual(report["run"]["id"], "run-report")
            self.assertTrue(report["tasks"])

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
                "codex-agent-os",
                "--command",
                "python -m py_compile scripts\\agent-runtime.py scripts\\codex_store.py",
                "--record",
            )
            self.assertTrue(result["ok"])
            self.assertEqual(result["result"], "passed")
            self.assertEqual(result["exit_code"], 0)

    def test_recovery_checkpoint_can_be_marked_obsolete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "runtime.db")
            created = self.run_cli(
                "runtime-create-checkpoint",
                "--db",
                db,
                "--project",
                "codex-agent-os",
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
                "codex-agent-os",
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
                "codex-agent-os",
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
                "codex-agent-os",
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
                "codex-agent-os",
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
