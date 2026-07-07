"""执行门控 PEP(PreToolUse / pre-commit)与并发地基的测试。

覆盖:
- SQLite connect() 启用 WAL / busy_timeout(P0 并发地基)
- detect-intent --record 写出 active-intent.json 指针,且只读意图下 execution-gate 拦截写
- PreToolUse 钩子对只读意图的写操作返回 deny,对 shell 放行,无指针时放行
- git pre-commit 门控在只读意图下拒绝提交,off 模式放行
- agent-os install 幂等地写入 .claude/settings.json 与 git pre-commit 钩子
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME = ROOT / "scripts" / "agent-runtime.py"
AGENT_OS_CLI = ROOT / "scripts" / "agent-os.py"
PRE_TOOL_USE = ROOT / "hooks" / "pre_tool_use.py"
PRE_COMMIT_GATE = ROOT / "hooks" / "pre_commit_gate.py"

sys.path.insert(0, str(ROOT / "scripts"))
import agent_store  # noqa: E402


class ConcurrencyFoundationTests(unittest.TestCase):
    def test_connect_enables_wal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "index.db"
            conn = agent_store.connect(db)
            try:
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(str(mode).lower(), "wal")
            finally:
                conn.close()


class PointerAndGateTests(unittest.TestCase):
    def _record_diagnose_intent(self, tmp: Path) -> dict:
        db = tmp / "index.db"
        completed = subprocess.run(
            [
                sys.executable,
                str(AGENT_RUNTIME),
                "runtime-detect-intent",
                "--record",
                "--project",
                "demo",
                "--request",
                "排查一下为什么第一次检测原创度为0",
                "--db",
                str(db),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_detect_intent_writes_pointer_and_blocks_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            result = self._record_diagnose_intent(tmp_path)
            # 只读诊断意图
            self.assertEqual(result["intent"]["mutation_authorization"], "read-only")
            # 指针写到与 db 同目录
            pointer_path = tmp_path / "active-intent.json"
            self.assertTrue(pointer_path.exists())
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            self.assertEqual(pointer["project"], "demo")
            self.assertTrue(pointer["intent_id"])

            # execution-gate:只读意图下写文件应被 blocked
            gate = subprocess.run(
                [
                    sys.executable,
                    str(AGENT_RUNTIME),
                    "runtime-execution-gate",
                    "--project",
                    "demo",
                    "--intent-id",
                    pointer["intent_id"],
                    "--action-type",
                    "write",
                    "--target-paths",
                    "src/app.py",
                    "--db",
                    str(tmp_path / "index.db"),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(gate.returncode, 0, gate.stderr)
            self.assertEqual(json.loads(gate.stdout)["gate"]["decision"], "blocked")


class PreToolUseHookTests(unittest.TestCase):
    def _hook_env(self, tmp: Path, mode: str = "enforce") -> dict:
        env = dict(os.environ)
        env["AGENT_OS_RUNTIME"] = str(AGENT_RUNTIME)
        env["AGENT_OS_DB"] = str(tmp / "index.db")
        env["AGENT_OS_POINTER"] = str(tmp / "active-intent.json")
        env["AGENT_OS_HOOK_MODE"] = mode
        return env

    def _record_diagnose_intent(self, tmp: Path) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(AGENT_RUNTIME),
                "runtime-detect-intent",
                "--record",
                "--project",
                "demo",
                "--request",
                "分析一下这个 bug 的原因",
                "--db",
                str(tmp / "index.db"),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _run_hook(self, tmp: Path, payload: dict, mode: str = "enforce") -> str:
        completed = subprocess.run(
            [sys.executable, str(PRE_TOOL_USE)],
            input=json.dumps(payload),
            env=self._hook_env(tmp, mode),
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def test_write_denied_under_diagnose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            out = self._run_hook(tmp_path, {"tool_name": "Write", "tool_input": {"file_path": "src/app.py"}})
            self.assertTrue(out, "写操作应产生决策输出")
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            self.assertEqual(decision, "deny")

    def test_safe_shell_allowed_under_diagnose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            # rg 在安全验证白名单内 -> shell.safe -> 只读意图下放行;
            # 未在白名单的命令(如 ls)会被判为 unsafe/可变而拦截,属预期的保守治理
            out = self._run_hook(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "rg TODO src"}})
            self.assertEqual(out, "", "白名单内的只读 shell 命令应放行(无输出)")

    def test_unsafe_shell_blocked_under_diagnose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            # 非白名单 shell 命令按可变处理,只读意图下应被拦
            out = self._run_hook(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}})
            self.assertTrue(out)
            self.assertEqual(json.loads(out)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_allow_when_no_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 未记录意图,无指针 -> 放行
            out = self._run_hook(tmp_path, {"tool_name": "Write", "tool_input": {"file_path": "src/app.py"}})
            self.assertEqual(out, "")

    def test_non_gated_tool_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            out = self._run_hook(tmp_path, {"tool_name": "Read", "tool_input": {"file_path": "src/app.py"}})
            self.assertEqual(out, "")

    def test_monitor_mode_never_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            out = self._run_hook(
                tmp_path,
                {"tool_name": "Write", "tool_input": {"file_path": "src/app.py"}},
                mode="monitor",
            )
            self.assertEqual(out, "", "monitor 模式只在 stderr 提示,stdout 不产生 deny")


class PreCommitGateTests(unittest.TestCase):
    def _record_diagnose_intent(self, tmp: Path) -> None:
        subprocess.run(
            [
                sys.executable,
                str(AGENT_RUNTIME),
                "runtime-detect-intent",
                "--record",
                "--project",
                "demo",
                "--request",
                "看看为什么登录失败",
                "--db",
                str(tmp / "index.db"),
            ],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def _run_gate(self, tmp: Path, mode: str) -> int:
        env = dict(os.environ)
        env["AGENT_OS_RUNTIME"] = str(AGENT_RUNTIME)
        env["AGENT_OS_DB"] = str(tmp / "index.db")
        env["AGENT_OS_POINTER"] = str(tmp / "active-intent.json")
        env["AGENT_OS_HOOK_MODE"] = mode
        return subprocess.run(
            [sys.executable, str(PRE_COMMIT_GATE)],
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        ).returncode

    def test_commit_rejected_under_diagnose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            self.assertEqual(self._run_gate(tmp_path, "enforce"), 1)

    def test_off_mode_allows_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            self._record_diagnose_intent(tmp_path)
            self.assertEqual(self._run_gate(tmp_path, "off"), 0)


class InstallHookTests(unittest.TestCase):
    def _install(self, target: Path, *extra: str) -> None:
        completed = subprocess.run(
            [sys.executable, str(AGENT_OS_CLI), "install", "--target", str(target), "--force", *extra],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_default_codex_no_claude_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            subprocess.run(["git", "init", str(target)], check=True, capture_output=True, text=True)
            self._install(target)  # 默认 codex
            # 生成 AGENTS.md,不创建 .claude
            self.assertTrue((target / "AGENTS.md").exists())
            self.assertFalse((target / ".claude").exists(), "codex 宿主不应创建 .claude 配置")
            # host.json 记录 codex
            host_marker = json.loads((target / ".agent-os" / "host.json").read_text(encoding="utf-8"))
            self.assertEqual(host_marker["host"], "codex")
            # git pre-commit 兜底对所有宿主都装
            pre_commit = target / ".git" / "hooks" / "pre-commit"
            self.assertTrue(pre_commit.exists())
            self.assertIn("Agent OS managed pre-commit", pre_commit.read_text(encoding="utf-8"))

    def test_claude_writes_hook_and_entry_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "proj"
            target.mkdir()
            subprocess.run(["git", "init", str(target)], check=True, capture_output=True, text=True)
            for _ in range(2):  # 跑两次验证幂等
                self._install(target, "--host", "claude")

            # Claude 生成 CLAUDE.md,不生成 AGENTS.md
            self.assertTrue((target / "CLAUDE.md").exists())
            self.assertFalse((target / "AGENTS.md").exists())
            host_marker = json.loads((target / ".agent-os" / "host.json").read_text(encoding="utf-8"))
            self.assertEqual(host_marker["host"], "claude")

            settings = target / ".claude" / "settings.json"
            self.assertTrue(settings.exists())
            pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
            marker_entries = [
                e
                for e in pre
                if any("pre_tool_use.py" in str(h.get("command", "")) for h in e.get("hooks", []))
            ]
            self.assertEqual(len(marker_entries), 1, "PreToolUse 钩子应幂等,只保留一条")
            hook_command = marker_entries[0]["hooks"][0]["command"]
            self.assertIn(sys.executable, hook_command)

            pre_commit = target / ".git" / "hooks" / "pre-commit"
            self.assertTrue(pre_commit.exists())
            self.assertIn("Agent OS managed pre-commit", pre_commit.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
