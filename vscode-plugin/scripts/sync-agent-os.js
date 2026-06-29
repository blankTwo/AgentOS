"use strict";

const fs = require("fs");
const path = require("path");

const pluginRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(pluginRoot, "..");
const targetRoot = path.join(pluginRoot, "agent-os");
const dryRun = process.argv.includes("--dry-run");

const excludedNames = new Set([
  ".git",
  ".idea",
  ".vscode",
  ".tmp",
  "__pycache__",
  ".pytest_cache",
  "vscode-plugin",
  "docs",
  "tests",
  "sessions",
  "logs",
  "temp",
]);

const excludedFiles = new Set([
  ".install-meta.json",
  "memory/index.db",
  "memory/index.db-shm",
  "memory/index.db-wal",
]);

function relativeFromRepo(filePath) {
  return path.relative(repoRoot, filePath).replace(/\\/g, "/");
}

function shouldSkip(filePath) {
  const relative = relativeFromRepo(filePath);
  if (!relative || relative.startsWith("..")) {
    return true;
  }
  if (excludedFiles.has(relative)) {
    return true;
  }
  if (relative.endsWith(".pyc") || relative.endsWith(".lock")) {
    return true;
  }
  return relative.split("/").some((part) => excludedNames.has(part));
}

function copyTree(sourceRoot, destinationRoot) {
  const actions = [];
  for (const entry of fs.readdirSync(sourceRoot, { withFileTypes: true })) {
    const source = path.join(sourceRoot, entry.name);
    if (shouldSkip(source)) {
      continue;
    }
    const destination = path.join(destinationRoot, path.relative(repoRoot, source));
    if (entry.isDirectory()) {
      if (!dryRun) {
        fs.mkdirSync(destination, { recursive: true });
      }
      actions.push(...copyTree(source, destinationRoot));
      continue;
    }
    actions.push(`copy ${relativeFromRepo(source)}`);
    if (!dryRun) {
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      fs.copyFileSync(source, destination);
    }
  }
  return actions;
}

if (!dryRun && fs.existsSync(targetRoot)) {
  fs.rmSync(targetRoot, { recursive: true, force: true });
}

const actions = copyTree(repoRoot, targetRoot);
console.log(JSON.stringify({
  ok: true,
  dryRun,
  source: repoRoot,
  target: targetRoot,
  files: actions.length,
}, null, 2));
