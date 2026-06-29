"use strict";

const fs = require("fs");
const path = require("path");
const cp = require("child_process");
const vscode = require("vscode");

let outputChannel;
let statusProvider;

function workspaceRoot() {
  const folder = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders[0];
  return folder ? folder.uri.fsPath : null;
}

function repoRoot(context) {
  return path.resolve(context.extensionPath, "..");
}

function coreScript(context) {
  const candidates = [
    path.join(context.extensionPath, "agent-os", "scripts", "agent-os.py"),
    path.join(repoRoot(context), "scripts", "agent-os.py"),
    path.join(context.extensionPath, "scripts", "agent-os.py"),
  ];
  const found = candidates.find(fileExists);
  return found || candidates[0];
}

function agentOsScript(root) {
  return path.join(root, ".agent-os", "scripts", "agent-os.py");
}

function runtimeScript(root) {
  return path.join(root, ".agent-os", "scripts", "agent-runtime.py");
}

function installMetaPath(root) {
  return path.join(root, ".agent-os", ".install-meta.json");
}

function fileExists(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function spawnPython(executable, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = cp.spawn(executable, args, {
      cwd,
      shell: false,
      env: process.env,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => resolve({ code, stdout, stderr, executable }));
  });
}

async function runPython(args, cwd) {
  const executables = ["python3", "python"];
  let lastError = null;
  for (const executable of executables) {
    try {
      const result = await spawnPython(executable, args, cwd);
      if (result.code === 0 || result.stderr || result.stdout) {
        return result;
      }
      return result;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Unable to locate a Python interpreter.");
}

async function readJson(args, cwd) {
  const result = await runPython(args, cwd);
  if (result.code !== 0) {
    throw new Error(result.stderr || `python exited with code ${result.code}`);
  }
  return JSON.parse(result.stdout);
}

async function installWorkspace(context) {
  const root = workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("Open a workspace before injecting Agent OS.");
    return;
  }
  const rootAgents = path.join(root, "AGENTS.md");
  const hadRootAgents = fileExists(rootAgents);
  const installer = coreScript(context);
  const result = await runPython([installer, "install", "--target", root, "--force"], repoRoot(context));
  if (result.code !== 0) {
    vscode.window.showErrorMessage("Agent OS injection failed. Check the Output panel.");
    const channel = getOutputChannel(context);
    channel.appendLine(result.stderr || result.stdout || "Agent OS injection failed.");
    channel.show(true);
    return;
  }
  const meta = {
    installedBy: "agent-os-vscode-plugin",
    rootAgentsCreated: !hadRootAgents,
    installedAt: new Date().toISOString(),
  };
  fs.writeFileSync(installMetaPath(root), JSON.stringify(meta, null, 2), "utf-8");
  vscode.window.showInformationMessage("Agent OS workspace injected.");
  if (statusProvider) {
    await statusProvider.refresh();
  }
}

function rootAgentsLooksGenerated(root) {
  const rootAgents = path.join(root, "AGENTS.md");
  if (!fileExists(rootAgents)) {
    return false;
  }
  const content = fs.readFileSync(rootAgents, "utf-8");
  const requiredMarkers = [
    "# Project Agent Entry",
    "This project uses Agent OS from `.agent-os/`.",
    "Project-specific rules can be added below this line.",
  ];
  return requiredMarkers.every((marker) => content.includes(marker));
}

function readInstallMeta(root) {
  const metaPath = installMetaPath(root);
  if (!fileExists(metaPath)) {
    return {};
  }
  try {
    return JSON.parse(fs.readFileSync(metaPath, "utf-8"));
  } catch {
    return {};
  }
}

async function uninstallWorkspace(context) {
  const root = workspaceRoot();
  if (!root) {
    vscode.window.showWarningMessage("请先打开一个工作区。");
    return;
  }
  const agentOsDir = path.join(root, ".agent-os");
  if (!fileExists(agentOsDir)) {
    vscode.window.showInformationMessage("当前工作区尚未安装 Agent OS。");
    return;
  }
  const meta = readInstallMeta(root);
  const shouldRemoveRootAgents = meta.rootAgentsCreated === true && rootAgentsLooksGenerated(root);
  const rootAgentsNote = shouldRemoveRootAgents
    ? "会同时删除本插件创建的根目录 AGENTS.md。"
    : "根目录 AGENTS.md 会保留。";
  const confirmed = await vscode.window.showWarningMessage(
    `确认卸载当前工作区的 .agent-os/？${rootAgentsNote}`,
    { modal: true },
    "确认卸载",
  );
  if (confirmed !== "确认卸载") {
    return;
  }
  const installer = coreScript(context);
  const args = ["uninstall", "--target", root];
  if (shouldRemoveRootAgents) {
    args.push("--remove-root-agents");
  }
  const result = await runPython([installer, ...args], repoRoot(context));
  if (result.code !== 0) {
    vscode.window.showErrorMessage("Agent OS 卸载失败。请查看 Output 面板。");
    const channel = getOutputChannel(context);
    channel.appendLine(result.stderr || result.stdout || "Agent OS uninstall failed.");
    channel.show(true);
    return;
  }
  vscode.window.showInformationMessage("Agent OS 已从当前工作区卸载。");
  if (statusProvider) {
    await statusProvider.refresh();
  }
}

function getOutputChannel(context) {
  if (!outputChannel) {
    outputChannel = vscode.window.createOutputChannel("Agent OS");
    context.subscriptions.push(outputChannel);
  }
  return outputChannel;
}

async function loadStatus(context) {
  const root = workspaceRoot();
  if (!root) {
    return {
      installed: false,
      root: null,
      reason: "No workspace folder is open.",
    };
  }
  const installed = fileExists(agentOsScript(root));
  const status = {
    installed,
    root,
    agentOsScript: agentOsScript(root),
    project: path.basename(root),
    doctor: null,
    dashboard: null,
    protocol: null,
  };
  if (!installed) {
    return status;
  }
  const doctor = await safeReadJson([agentOsScript(root), "doctor", "--root", path.join(root, ".agent-os")], root);
  const summary = await safeReadJson([runtimeScript(root), "runtime-summary", "--project", status.project, "--limit", "5"], root);
  const protocol = await safeReadJson(
    [agentOsScript(root), "vscode-protocol", "--project", status.project],
    root,
  );
  return { ...status, doctor, summary, protocol };
}

async function safeReadJson(args, cwd) {
  try {
    return await readJson(args, cwd);
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      args,
    };
  }
}

function updateButtonBusyState(button, busy) {
  button.disabled = busy;
  button.textContent = busy ? (button.dataset.busy || "处理中...") : button.dataset.original;
}

function renderStatusHtml(status) {
  const checks = status.doctor ? status.doctor.checks || [] : [];
  const passed = checks.filter((check) => check.status === "passed").length;
  const failed = checks.length - passed;
  const topChecks = checks.slice(0, 8).map(
    (check) => `<li><strong>${escapeHtml(localizeCheckName(check.name))}</strong> <span>${escapeHtml(localizeStatus(check.status))}</span></li>`,
  ).join("");
  const protocolCommands = status.protocol ? Object.keys(status.protocol.commands || {}).map(
    (key) => `<li><code>${escapeHtml(key)}</code>: ${escapeHtml(status.protocol.commands[key])}</li>`,
  ).join("") : "";
  const doctorStatus = status.doctor && status.doctor.ok === false
    ? `<div class="status-bad">${escapeHtml(status.doctor.error || "健康检查不可用")}</div>`
    : "";
  return `<!doctype html>
  <html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font-family: var(--vscode-font-family); margin: 0; padding: 16px; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
      h1 { font-size: 18px; margin: 0 0 12px; }
      .grid { display: grid; gap: 8px; grid-template-columns: 1fr; }
      .card { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 12px; background: var(--vscode-sideBar-background); }
      .muted { color: var(--vscode-descriptionForeground); font-size: 12px; }
      .value { margin-top: 4px; overflow-wrap: anywhere; }
      .status-ok { color: var(--vscode-testing-iconPassed); }
      .status-bad { color: var(--vscode-testing-iconFailed); }
      ul { padding-left: 18px; margin: 8px 0 0; }
      code { background: var(--vscode-textCodeBlock-background); padding: 2px 5px; border-radius: 6px; }
      .button-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
      button { appearance: none; border: 1px solid var(--vscode-button-border, transparent); border-radius: 6px; padding: 6px 10px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); cursor: pointer; }
      button.secondary { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
      button.danger { background: var(--vscode-inputValidation-errorBackground); color: var(--vscode-inputValidation-errorForeground); border-color: var(--vscode-inputValidation-errorBorder); }
      button:disabled { opacity: 0.65; cursor: wait; }
      .notice { margin-top: 10px; color: var(--vscode-descriptionForeground); min-height: 18px; }
    </style>
  </head>
  <body>
    <h1>Agent OS 状态</h1>
    <div class="grid">
      <div class="card">
        <div class="muted">工作区</div>
        <div class="value">${escapeHtml(status.root || "未打开工作区")}</div>
        <div class="${status.installed ? "status-ok" : "status-bad"}">${status.installed ? "已安装" : "未安装"}</div>
      </div>
      <div class="card">
        <div class="muted">健康检查</div>
        <div class="value">${status.doctor ? `${passed}/${checks.length} 项通过` : "不可用"}</div>
        <div class="${failed ? "status-bad" : "status-ok"}">${failed ? `${failed} 个问题` : "健康"}</div>
        ${doctorStatus}
      </div>
    </div>
    <div class="card" style="margin-top:12px;">
      <div class="muted">检查项</div>
      <ul>${topChecks || "<li>暂无检查结果。</li>"}</ul>
    </div>
    <div class="card" style="margin-top:12px;">
      <div class="muted">协议命令</div>
      <ul>${protocolCommands || "<li>暂无协议命令。</li>"}</ul>
    </div>
    <div class="card" style="margin-top:12px;">
      <div class="muted">操作</div>
      <p>可以使用命令面板，也可以直接点击下面的操作。</p>
      <div class="button-row">
        ${status.installed
          ? '<button class="danger" data-command="agentOs.uninstallWorkspace" data-busy="正在卸载...">卸载工作区</button>'
          : '<button data-command="agentOs.injectWorkspace" data-busy="正在注入...">注入工作区</button>'
        }
        <button class="secondary" data-command="agentOs.refreshStatus" data-busy="正在刷新...">刷新状态</button>
        <button class="secondary" data-command="agentOs.openOverview" data-busy="正在打开..." ${status.installed ? "" : "disabled"}>打开总览</button>
      </div>
      <div id="notice" class="notice"></div>
    </div>
    <script>
      const vscode = acquireVsCodeApi();
      const notice = document.getElementById("notice");
      function updateButtonBusyState(button, busy) {
        button.disabled = busy;
        button.textContent = busy ? (button.dataset.busy || "处理中...") : button.dataset.original;
      }
      document.querySelectorAll("button[data-command]").forEach((button) => {
        button.dataset.original = button.textContent;
        button.addEventListener("click", () => {
          updateButtonBusyState(button, true);
          notice.textContent = button.textContent;
          vscode.postMessage({ command: button.dataset.command });
        });
      });
    </script>
  </body>
  </html>`;
}

function localizeStatus(value) {
  return {
    passed: "通过",
    failed: "失败",
    warning: "警告",
    skipped: "跳过",
  }[value] || value;
}

function localizeCheckName(value) {
  return {
    directories: "目录结构",
    agents: "入口文件",
    rules: "规则",
    skills: "技能",
    bootstrap: "项目入口",
    "policy-packs": "策略包",
    security: "安全检查",
    memory: "记忆",
    runtime: "运行时",
    version: "版本",
    "db-writable": "数据库可写",
  }[value] || value;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function registerStatusView(context, provider) {
  context.subscriptions.push(vscode.window.registerWebviewViewProvider("agentOsStatus", provider));
}

function createStatusProvider(context) {
  let currentView;
  let lastStatusMessage = "";
  async function render() {
    if (!currentView) {
      return;
    }
    try {
      const status = await loadStatus(context);
      currentView.webview.html = renderStatusHtml(status).replace('<div id="notice" class="notice"></div>', `<div id="notice" class="notice">${escapeHtml(lastStatusMessage)}</div>`);
    } catch (error) {
      currentView.webview.html = `<pre>${escapeHtml(error.stack || error.message)}</pre>`;
    }
  }
  return {
    refresh: render,
    resolveWebviewView(webviewView) {
      currentView = webviewView;
      webviewView.webview.options = { enableScripts: true, enableCommandUris: true };
      webviewView.webview.onDidReceiveMessage(async (message) => {
        if (!message || !message.command) {
          return;
        }
        lastStatusMessage = "处理中...";
        try {
          await vscode.commands.executeCommand(message.command);
          lastStatusMessage = "操作完成。";
        } catch (error) {
          lastStatusMessage = `操作失败：${error.message}`;
          vscode.window.showErrorMessage(lastStatusMessage);
        } finally {
          await render();
        }
      });
      render();
    },
  };
}

function registerCommands(context) {
  context.subscriptions.push(
    vscode.commands.registerCommand("agentOs.injectWorkspace", () => installWorkspace(context)),
    vscode.commands.registerCommand("agentOs.uninstallWorkspace", () => uninstallWorkspace(context)),
    vscode.commands.registerCommand("agentOs.refreshStatus", async () => {
      const status = await loadStatus(context);
      const channel = getOutputChannel(context);
      channel.appendLine(JSON.stringify(status, null, 2));
      channel.show(true);
      if (statusProvider) {
        await statusProvider.refresh();
      }
      vscode.window.showInformationMessage("Agent OS 状态已刷新。");
      return status;
    }),
    vscode.commands.registerCommand("agentOs.openDashboard", async () => {
      const root = workspaceRoot();
      if (!root) {
        return;
      }
      const dashboard = path.join(root, "docs", "agent-os", "dashboard.html");
      if (!fileExists(agentOsScript(root))) {
        vscode.window.showWarningMessage("当前工作区尚未安装 Agent OS。");
        return;
      }
      if (!fileExists(dashboard)) {
        await readJson(
          [
            agentOsScript(root),
            "dashboard",
            "--project",
            path.basename(root),
            "--output",
            dashboard,
            "--data-output",
            path.join(root, "docs", "agent-os", "dashboard.json"),
          ],
          root,
        );
      }
      if (fileExists(dashboard)) {
        await vscode.env.openExternal(vscode.Uri.file(dashboard));
        return;
      }
      vscode.window.showWarningMessage("仪表盘暂不可用。");
    }),
    vscode.commands.registerCommand("agentOs.openReport", async () => {
      const root = workspaceRoot();
      if (!root) {
        return;
      }
      if (!fileExists(agentOsScript(root))) {
        vscode.window.showWarningMessage("当前工作区尚未安装 Agent OS。");
        return;
      }
      const dashboard = path.join(root, "docs", "agent-os", "dashboard.html");
      if (!fileExists(dashboard)) {
        await readJson(
          [
            agentOsScript(root),
            "dashboard",
            "--project",
            path.basename(root),
            "--output",
            dashboard,
            "--data-output",
            path.join(root, "docs", "agent-os", "dashboard.json"),
          ],
          root,
        );
      }
      if (fileExists(dashboard)) {
        await vscode.env.openExternal(vscode.Uri.file(dashboard));
        return;
      }
      vscode.window.showWarningMessage("运行总览暂不可用。");
    }),
    vscode.commands.registerCommand("agentOs.openOverview", async () => {
      await vscode.commands.executeCommand("agentOs.openDashboard");
    }),
  );
}

function activate(context) {
  registerCommands(context);
  statusProvider = createStatusProvider(context);
  registerStatusView(context, statusProvider);
}

function deactivate() {}

module.exports = { activate, deactivate };
