#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const UI_DIR = resolve(new URL("..", import.meta.url).pathname);
const ROOT_DIR = resolve(UI_DIR, "..");
const OUTPUTS_DIR = join(ROOT_DIR, "outputs");
const QUICK_RUNS_DIR = join(OUTPUTS_DIR, "quick_runs");
const ARTIFACT_DIR = join(UI_DIR, "test-results", "quick-run-native");
const VITE_ENV_LOCAL = join(UI_DIR, ".env.local");
const APP_EVENTS_PATH = join(ARTIFACT_DIR, "app-events.jsonl");
let activeChild = null;
let activeRestoreViteEnv = null;
let shuttingDown = false;

function parseArgs(argv) {
  const args = {
    timeoutMs: Number(process.env.QUICK_RUN_NATIVE_VERIFY_TIMEOUT_MS || "180000"),
    keepArtifacts: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") {
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      console.log(`Usage: node ui/scripts/verify_quick_run_native.mjs [--timeout-ms <ms>] [--keep-artifacts]`);
      process.exit(0);
    }
    if (arg === "--timeout-ms") {
      args.timeoutMs = Number(argv[++index]);
      continue;
    }
    if (arg === "--keep-artifacts") {
      args.keepArtifacts = true;
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }

  return args;
}

function quickRunFiles() {
  if (!existsSync(QUICK_RUNS_DIR)) return new Set();
  return new Set(
    readdirSync(QUICK_RUNS_DIR)
      .filter((name) => name.startsWith("qr_") && name.endsWith(".json"))
      .map((name) => join(QUICK_RUNS_DIR, name))
  );
}

function readQuickRun(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function findFinishedRun(baseline) {
  const candidates = [...quickRunFiles()]
    .filter((path) => !baseline.has(path))
    .map((path) => ({ path, payload: readQuickRun(path) }))
    .sort((a, b) => String(b.payload.run?.started_at ?? "").localeCompare(String(a.payload.run?.started_at ?? "")));

  for (const candidate of candidates) {
    const run = candidate.payload.run ?? {};
    const status = String(run.status ?? "");
    if (["DONE", "SKIPPED", "FAILED", "TIMEOUT"].includes(status)) {
      return {
        runId: String(run.run_id ?? candidate.path.match(/qr_[^.]+/)?.[0] ?? ""),
        status,
        record: candidate.path,
      };
    }
  }

  return null;
}

function cleanupGeneratedArtifacts(runId) {
  const paths = [
    join(ROOT_DIR, "evidence_cards", `ec-${runId}.yaml`),
    join(ROOT_DIR, "matching_reports", `mr-${runId}.yaml`),
  ];
  for (const path of paths) {
    if (existsSync(path)) rmSync(path);
  }
}

function startTauriDev() {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  if (existsSync(APP_EVENTS_PATH)) unlinkSync(APP_EVENTS_PATH);
  const logPath = join(ARTIFACT_DIR, "tauri.log");
  const child = spawn("pnpm", ["tauri", "dev"], {
    cwd: UI_DIR,
    env: {
      ...process.env,
      QUICK_RUN_VERIFY_AUTORUN: "quick-run",
      VITE_QUICK_RUN_VERIFY_AUTORUN: "quick-run",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });

  let logs = "";
  const appendLog = (chunk) => {
    const text = chunk.toString();
    logs += text;
    writeFileSync(logPath, logs);
  };
  child.stdout.on("data", appendLog);
  child.stderr.on("data", appendLog);

  return { child, logPath, logs: () => logs };
}

function enableViteAutorunEnv() {
  const previous = existsSync(VITE_ENV_LOCAL)
    ? readFileSync(VITE_ENV_LOCAL, "utf8")
    : null;
  const next = `${previous ?? ""}${previous?.endsWith("\n") || !previous ? "" : "\n"}VITE_QUICK_RUN_VERIFY_AUTORUN=quick-run\n`;
  writeFileSync(VITE_ENV_LOCAL, next);
  return () => {
    if (previous === null) {
      if (existsSync(VITE_ENV_LOCAL)) unlinkSync(VITE_ENV_LOCAL);
      return;
    }
    writeFileSync(VITE_ENV_LOCAL, previous);
  };
}

async function waitForRun(args, child, baseline) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Tauri dev exited before Quick Run completed, exit code ${child.exitCode}`);
    }

    const result = findFinishedRun(baseline);
    if (result) return result;
    await sleep(500);
  }
  throw new Error("Timed out waiting for Quick Run output");
}

async function stopProcess(child) {
  if (child.exitCode !== null) return;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
      stdio: "ignore",
    });
    return;
  }

  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    child.kill("SIGTERM");
  }
  for (let i = 0; i < 20; i += 1) {
    if (child.exitCode !== null) return;
    await sleep(100);
  }
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
}

function tailFile(path, lines) {
  if (!existsSync(path)) return "";
  return readFileSync(path, "utf8").split("\n").slice(-lines).join("\n");
}

async function shutdownFromSignal(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (activeChild) await stopProcess(activeChild);
  if (activeRestoreViteEnv) activeRestoreViteEnv();
  process.exit(signal === "SIGINT" ? 130 : 143);
}

process.once("SIGINT", () => {
  void shutdownFromSignal("SIGINT");
});
process.once("SIGTERM", () => {
  void shutdownFromSignal("SIGTERM");
});

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const baseline = quickRunFiles();
  const restoreViteEnv = enableViteAutorunEnv();
  const { child, logPath, logs } = startTauriDev();
  activeChild = child;
  activeRestoreViteEnv = restoreViteEnv;
  try {
    const result = await waitForRun(args, child, baseline);
    const summary = join(OUTPUTS_DIR, "agent_runs", result.runId, "summary.json");
    if (["DONE", "SKIPPED"].includes(result.status) && !existsSync(summary)) {
      throw new Error(`Quick Run finished but summary was not found: ${summary}`);
    }
    if (!args.keepArtifacts) cleanupGeneratedArtifacts(result.runId);
    console.log(
      JSON.stringify({
        ok: ["DONE", "SKIPPED"].includes(result.status),
        driver: "tauri-native-autorun",
        run_id: result.runId,
        status: result.status,
        quick_run_record: result.record,
        summary,
        log: logPath,
        app_events: APP_EVENTS_PATH,
      })
    );
    process.exitCode = ["DONE", "SKIPPED"].includes(result.status) ? 0 : 1;
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    const appEvents = tailFile(APP_EVENTS_PATH, 80);
    if (appEvents) {
      console.error("Recent app verifier events:");
      console.error(appEvents);
    }
    console.error(logs().split("\n").slice(-80).join("\n"));
    process.exitCode = 1;
  } finally {
    await stopProcess(child);
    restoreViteEnv();
    activeChild = null;
    activeRestoreViteEnv = null;
  }
}

await main();
