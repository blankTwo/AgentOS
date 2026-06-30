"use strict";

const fs = require("fs");
const path = require("path");
const cp = require("child_process");
const https = require("https");
const http = require("http");

const RELEASE_TAG = "20260623";
const RELEASE_PREFIX = `https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}`;
const PYTHON_VERSION = "3.13.14";

function platformId() {
  if (process.platform === "win32") {
    return "windows";
  }
  if (process.platform === "darwin") {
    return "macos";
  }
  return "other";
}

function archId() {
  if (process.arch === "x64") {
    return "x86_64";
  }
  if (process.arch === "arm64") {
    return "aarch64";
  }
  return process.arch;
}

function assetName() {
  if (platformId() === "windows") {
    return `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-${archId()}-pc-windows-msvc-install_only_stripped.tar.gz`;
  }
  if (platformId() === "macos") {
    return `cpython-${PYTHON_VERSION}+${RELEASE_TAG}-${archId()}-apple-darwin-install_only_stripped.tar.gz`;
  }
  return null;
}

function runtimeRoot(extensionPath) {
  return path.join(extensionPath, ".runtime-cache");
}

function runtimeInstallDir(extensionPath) {
  return path.join(runtimeRoot(extensionPath), platformId(), archId(), RELEASE_TAG);
}

function runtimePythonPath(extensionPath) {
  const installDir = runtimeInstallDir(extensionPath);
  const discovered = discoverPythonExecutable(installDir);
  if (discovered) {
    return discovered;
  }
  if (platformId() === "windows") {
    return path.join(installDir, "python", "python.exe");
  }
  return path.join(installDir, "python", "bin", "python3");
}

function discoverPythonExecutable(rootDir) {
  const candidates = [];
  const maxDepth = 5;
  function walk(dir, depth) {
    if (depth > maxDepth || !fs.existsSync(dir)) {
      return;
    }
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full, depth + 1);
        continue;
      }
      const name = entry.name.toLowerCase();
      if (platformId() === "windows" && name === "python.exe") {
        candidates.push(full);
      }
      if (platformId() !== "windows" && (name === "python3" || name === "python")) {
        candidates.push(full);
      }
    }
  }
  walk(rootDir, 0);
  return candidates[0] || null;
}

function downloadFile(url, destination, redirectCount = 0) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https:") ? https : http;
    const request = client.get(url, { headers: { "User-Agent": "Codex" } }, (response) => {
      const status = response.statusCode || 0;
      if (status >= 300 && status < 400 && response.headers.location) {
        response.resume();
        if (redirectCount > 5) {
          reject(new Error("Too many redirects while downloading bundled Python runtime."));
          return;
        }
        const nextUrl = new URL(response.headers.location, url).toString();
        downloadFile(nextUrl, destination, redirectCount + 1).then(resolve, reject);
        return;
      }
      if (status !== 200) {
        response.resume();
        reject(new Error(`Download failed: ${status}`));
        return;
      }
      fs.mkdirSync(path.dirname(destination), { recursive: true });
      const file = fs.createWriteStream(destination);
      response.pipe(file);
      file.on("finish", () => file.close(resolve));
      file.on("error", reject);
    });
    request.on("error", reject);
  });
}

function commandExists(command) {
  try {
    const which = process.platform === "win32" ? "where" : "which";
    const result = cp.spawnSync(which, [command], { stdio: "ignore", shell: false });
    return result.status === 0;
  } catch {
    return false;
  }
}

function downloadWithCurl(url, destination) {
  const curl = process.platform === "win32" ? "curl.exe" : "curl";
  const result = cp.spawnSync(
    curl,
    [
      "-L",
      "--fail",
      "--silent",
      "--show-error",
      "--retry",
      "5",
      "--retry-all-errors",
      "--retry-delay",
      "2",
      "--connect-timeout",
      "30",
      "--max-time",
      "600",
      "-C",
      "-",
      "-o",
      destination,
      url,
    ],
    {
      stdio: "inherit",
      shell: false,
    },
  );
  if (result.status !== 0) {
    throw new Error("curl download failed");
  }
}

function extractArchive(archivePath, destinationDir) {
  fs.mkdirSync(destinationDir, { recursive: true });
  const result = cp.spawnSync("tar", ["-xzf", archivePath, "-C", destinationDir], { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("Failed to extract Python archive.");
  }
}

async function ensureRuntime(extensionPath) {
  const pythonPath = runtimePythonPath(extensionPath);
  if (fs.existsSync(pythonPath)) {
    return pythonPath;
  }
  const asset = assetName();
  if (!asset) {
    return null;
  }
  const installDir = runtimeInstallDir(extensionPath);
  const marker = path.join(installDir, ".ready");
  if (fs.existsSync(marker) && fs.existsSync(pythonPath)) {
    return pythonPath;
  }
  const archivePath = path.join(runtimeRoot(extensionPath), path.basename(asset));
  const url = `${RELEASE_PREFIX}/${asset}`;
  const downloaders = [];
  if (commandExists(process.platform === "win32" ? "curl.exe" : "curl")) {
    downloaders.push(() => downloadWithCurl(url, archivePath));
  }
  downloaders.push(() => downloadFile(url, archivePath));
  let lastError = null;
  for (const downloader of downloaders) {
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      try {
        await downloader();
        lastError = null;
        break;
      } catch (error) {
        lastError = error;
        if (attempt === 3) {
          break;
        }
      }
    }
    if (!lastError) {
      break;
    }
  }
  if (lastError) {
    throw new Error(`Bundled Python runtime download failed: ${lastError.message}`);
  }
  extractArchive(archivePath, installDir);
  const discoveredPython = discoverPythonExecutable(installDir) || runtimePythonPath(extensionPath);
  if (!fs.existsSync(discoveredPython)) {
    throw new Error("Bundled Python runtime was extracted, but no python executable was found.");
  }
  fs.writeFileSync(marker, JSON.stringify({ asset, downloadedAt: new Date().toISOString() }, null, 2), "utf-8");
  return discoveredPython;
}

async function runPython(extensionPath, args, cwd, envExtra = {}) {
  const pythonPath = await ensureRuntime(extensionPath);
  if (!pythonPath) {
    return { code: 127, stdout: "", stderr: "No bundled Python runtime available for this platform.", executable: null };
  }
  const child = cp.spawn(pythonPath, args, {
    cwd,
    shell: false,
    env: { ...process.env, ...envExtra },
  });
  let stdout = "";
  let stderr = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  return await new Promise((resolve) => {
    child.on("close", (code) => resolve({ code, stdout, stderr, executable: pythonPath }));
  });
}

module.exports = {
  ensureRuntime,
  runPython,
  runtimePythonPath,
};
