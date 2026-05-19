#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const UI_DIR = resolve(new URL("..", import.meta.url).pathname);
const ARTIFACT_DIR = join(UI_DIR, "test-results", "jobs-native");
const VITE_ENV_LOCAL = join(UI_DIR, ".env.local");
const APP_EVENTS_PATH = join(ARTIFACT_DIR, "app-events.jsonl");
const SCENARIO = "jobs";

let activeChild = null;
let activeRestoreViteEnv = null;
let shuttingDown = false;

function parseArgs(argv) {
  const args = {
    timeoutMs: Number(process.env.JOBS_NATIVE_VERIFY_TIMEOUT_MS || "90000"),
    keepArtifacts: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") continue;
    if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: node ui/scripts/verify_jobs_native.mjs [--timeout-ms <ms>] [--keep-artifacts]"
      );
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

function startTauriDev() {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  if (existsSync(APP_EVENTS_PATH)) unlinkSync(APP_EVENTS_PATH);
  const logPath = join(ARTIFACT_DIR, "tauri.log");
  const child = spawn("pnpm", ["tauri", "dev"], {
    cwd: UI_DIR,
    env: {
      ...process.env,
      QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
      VITE_QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
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
  const next = `${previous ?? ""}${
    previous?.endsWith("\n") || !previous ? "" : "\n"
  }VITE_QUICK_RUN_VERIFY_AUTORUN=${SCENARIO}\n`;
  writeFileSync(VITE_ENV_LOCAL, next);
  return () => {
    if (previous === null) {
      if (existsSync(VITE_ENV_LOCAL)) unlinkSync(VITE_ENV_LOCAL);
      return;
    }
    writeFileSync(VITE_ENV_LOCAL, previous);
  };
}

function readEvents() {
  if (!existsSync(APP_EVENTS_PATH)) return [];
  return readFileSync(APP_EVENTS_PATH, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function validateReadyEvent(event) {
  if (event.event !== "jobs.load.ready") return false;
  for (const key of ["profile_count", "lead_count", "active_profile_count"]) {
    if (typeof event[key] !== "number") return false;
    if (event[key] < 0) return false;
  }
  return true;
}

async function waitForReadyEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before Jobs loaded, exit code ${child.exitCode}`
      );
    }

    const ready = readEvents().find(validateReadyEvent);
    if (ready) return ready;
    await sleep(500);
  }
  throw new Error("Timed out waiting for Jobs native ready event");
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
  if (!args.keepArtifacts && existsSync(ARTIFACT_DIR)) {
    rmSync(ARTIFACT_DIR, { recursive: true, force: true });
  }
  const restoreViteEnv = enableViteAutorunEnv();
  const { child, logPath, logs } = startTauriDev();
  activeChild = child;
  activeRestoreViteEnv = restoreViteEnv;

  try {
    const event = await waitForReadyEvent(args, child);
    console.log(
      JSON.stringify({
        ok: true,
        driver: "tauri-native-autorun",
        scenario: SCENARIO,
        profile_count: event.profile_count,
        lead_count: event.lead_count,
        active_profile_count: event.active_profile_count,
        log: logPath,
        app_events: APP_EVENTS_PATH,
      })
    );
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
