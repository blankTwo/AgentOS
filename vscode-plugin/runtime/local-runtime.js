"use strict";

const fs = require("fs");
const path = require("path");

const GIT_EXCLUDE_START = "# Agent OS managed excludes";
const GIT_EXCLUDE_END = "# End Agent OS managed excludes";
const GIT_EXCLUDE_ENTRIES = ["AGENTS.md", ".agent-os/"];

const PROJECT_AGENTS_TEMPLATE = `# Project Agent Entry

This project uses Agent OS from \`.agent-os/\`.

This root \`AGENTS.md\` is the project bootstrap entry. Load it first, then delegate to \`.agent-os/AGENTS.md\`.

## Agent Display

Agent display name: Agent OS

Use this display name at the start of the first user-visible status paragraph and for major status/conclusion paragraphs so the user can see Agent OS is active.

Before starting any task:
1. Read \`.agent-os/AGENTS.md\`.
2. Follow \`.agent-os/context/\`, \`.agent-os/workflows/\`, \`.agent-os/rules/\`, \`.agent-os/skills/\`, \`.agent-os/tools/\`, and \`.agent-os/memory/\`.
3. Prefer project-local \`.agent-os/skills/<skill>/SKILL.md\` over global user-level skills when both exist.
4. Treat this repository root as the user project.
5. Keep project-specific decisions in \`.agent-os/memory/projects/{project}.md\`.
6. Save durable implementation plans, task breakdowns, decisions, reviews, and verification records under \`docs/agent-os/\`.
7. Before final response, decide whether project README/docs, \`docs/agent-os/\`, project memory, or Agent OS docs need updates; if not, state why.
8. Do not modify \`.agent-os/AGENTS.md\` unless the user explicitly asks to upgrade Agent OS itself.

Project-specific rules can be added below this line.
`;

function fileExists(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function rootFromContext(context) {
  return context.workspaceRoot || process.cwd();
}

function repoRoot(context) {
  return path.resolve(context.extensionPath, "..");
}

function bundledAgentOsRoot(context) {
  return path.join(context.extensionPath, "agent-os");
}

function managedIgnoreTarget(root) {
  const gitDir = path.join(root, ".git");
  if (fileExists(gitDir)) {
    return path.join(gitDir, "info", "exclude");
  }
  return path.join(root, ".gitignore");
}

function updateManagedIgnoreFile(root, entries) {
  const ignorePath = managedIgnoreTarget(root);
  const existing = fileExists(ignorePath) ? fs.readFileSync(ignorePath, "utf-8") : "";
  const block = [GIT_EXCLUDE_START, ...entries, GIT_EXCLUDE_END].join("\n") + "\n";
  const pattern = new RegExp(`^\\s*${escapeRegExp(GIT_EXCLUDE_START)}\\n[\\s\\S]*?^\\s*${escapeRegExp(GIT_EXCLUDE_END)}\\n?`, "m");
  let updated = existing;
  if (pattern.test(existing)) {
    updated = existing.replace(pattern, block);
  } else {
    if (updated && !updated.endsWith("\n")) {
      updated += "\n";
    }
    if (updated && !updated.endsWith("\n\n")) {
      updated += "\n";
    }
    updated += block;
  }
  if (updated !== existing) {
    fs.mkdirSync(path.dirname(ignorePath), { recursive: true });
    fs.writeFileSync(ignorePath, updated, "utf-8");
  }
  return ignorePath;
}

function removeManagedIgnoreFile(root) {
  const ignorePath = managedIgnoreTarget(root);
  if (!fileExists(ignorePath)) {
    return ignorePath;
  }
  const existing = fs.readFileSync(ignorePath, "utf-8");
  const pattern = new RegExp(`^\\s*${escapeRegExp(GIT_EXCLUDE_START)}\\n[\\s\\S]*?^\\s*${escapeRegExp(GIT_EXCLUDE_END)}\\n?`, "m");
  const updated = existing.replace(pattern, "");
  if (updated !== existing) {
    fs.writeFileSync(ignorePath, updated, "utf-8");
  }
  return ignorePath;
}

function copyAgentOs(sourceRoot, targetRoot) {
  const actions = [];
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    const source = path.join(sourceRoot, entry.name);
    const relative = path.relative(sourceRoot, source).replace(/\\/g, "/");
    if (relative === "vscode-plugin" || relative === "docs" || relative === "tests") {
      continue;
    }
    const destination = path.join(targetRoot, relative);
    if (entry.isDirectory()) {
      fs.mkdirSync(destination, { recursive: true });
      actions.push(...copyAgentOs(source, destination));
      continue;
    }
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(source, destination);
    actions.push(`copy ${relative}`);
  }
  return actions;
}

function install(context, options = {}) {
  const root = rootFromContext(context);
  const force = options.force === true;
  const agentOsDir = path.join(root, ".agent-os");
  const rootAgents = path.join(root, "AGENTS.md");
  const actions = [];
  if (fileExists(agentOsDir) && !force) {
    throw new Error(`Agent OS install target already exists: ${agentOsDir}`);
  }
  if (fileExists(agentOsDir)) {
    fs.rmSync(agentOsDir, { recursive: true, force: true });
  }
  fs.mkdirSync(agentOsDir, { recursive: true });
  actions.push(...copyAgentOs(bundledAgentOsRoot(context), agentOsDir));
  if (fileExists(rootAgents) && !force) {
    throw new Error(`Root AGENTS.md already exists: ${rootAgents}`);
  }
  fs.writeFileSync(rootAgents, PROJECT_AGENTS_TEMPLATE, "utf-8");
  fs.mkdirSync(path.join(agentOsDir, "memory"), { recursive: true });
  updateManagedIgnoreFile(root, GIT_EXCLUDE_ENTRIES);
  return { ok: true, actions, root, mode: "local-js" };
}

function uninstall(context, options = {}) {
  const root = rootFromContext(context);
  const removeRootAgents = options.removeRootAgents === true;
  const agentOsDir = path.join(root, ".agent-os");
  const rootAgents = path.join(root, "AGENTS.md");
  const actions = [];
  removeManagedIgnoreFile(root);
  if (removeRootAgents && fileExists(rootAgents)) {
    fs.unlinkSync(rootAgents);
    actions.push(`remove root AGENTS.md -> ${rootAgents}`);
  }
  if (fileExists(agentOsDir)) {
    fs.rmSync(agentOsDir, { recursive: true, force: true });
    actions.push(`remove Agent OS directory -> ${agentOsDir}`);
  }
  return { ok: true, actions, root, mode: "local-js" };
}

function detect(context) {
  const root = rootFromContext(context);
  const agentOsDir = path.join(root, ".agent-os");
  return {
    ok: true,
    root,
    agentOsDir,
    installed: fileExists(agentOsDir),
    mode: "local-js",
  };
}

module.exports = {
  install,
  uninstall,
  detect,
};
