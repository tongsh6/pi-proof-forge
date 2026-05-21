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
const ROOT_DIR = resolve(UI_DIR, "..");
const ARTIFACT_DIR = join(UI_DIR, "test-results", "agent-run-native");
const VITE_ENV_LOCAL = join(UI_DIR, ".env.local");
const APP_EVENTS_PATH = join(ARTIFACT_DIR, "app-events.jsonl");
const TEMP_POLICY_PATH = join(ARTIFACT_DIR, "policy.yaml");
const SCENARIO = "agent-run";
const EXPECTED_LLM = {
  provider: "agent_run_verify_provider",
  model: "agent-run-verify-model",
  baseUrl: "http://127.0.0.1:65534/v1",
};

let activeChild = null;
let activeRestoreViteEnv = null;
let shuttingDown = false;

function parseArgs(argv) {
  const args = {
    timeoutMs: Number(process.env.AGENT_RUN_NATIVE_VERIFY_TIMEOUT_MS || "90000"),
    keepArtifacts: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") continue;
    if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: node ui/scripts/verify_agent_run_native.mjs [--timeout-ms <ms>] [--keep-artifacts]"
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
  writeFileSync(
    TEMP_POLICY_PATH,
    [
      `llm_provider: "${EXPECTED_LLM.provider}"`,
      `llm_model: "${EXPECTED_LLM.model}"`,
      `llm_base_url: "${EXPECTED_LLM.baseUrl}"`,
      `llm_api_key_configured: "true"`,
      `llm_api_key_updated_at: "2026-05-21T00:00:00Z"`,
      `llm_api_key_placeholder: "configured"`,
      `llm_timeout: "30"`,
      `llm_temperature: "0.2"`,
      "",
    ].join("\n"),
    "utf8"
  );
  const logPath = join(ARTIFACT_DIR, "tauri.log");
  const child = spawn("pnpm", ["tauri", "dev"], {
    cwd: UI_DIR,
    env: {
      ...process.env,
      PPF_POLICY_PATH: TEMP_POLICY_PATH,
      QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
      VITE_QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
      VITE_NATIVE_VERIFY: "1",
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
  return () => undefined;
}

function readEvents() {
  if (!existsSync(APP_EVENTS_PATH)) return [];
  return readFileSync(APP_EVENTS_PATH, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function validateReadyEvent(event) {
  if (event.event !== "agent_run.load.ready") return false;
  if (typeof event.profile_count !== "number" || event.profile_count < 0) {
    return false;
  }
  if (typeof event.selected_profile_id !== "string") return false;
  return (
    event.llm_provider === EXPECTED_LLM.provider &&
    event.llm_model === EXPECTED_LLM.model &&
    event.llm_base_url === EXPECTED_LLM.baseUrl &&
    event.api_key_configured === true &&
    event.api_key_masked === true
  );
}

function validateStartResultEvent(event) {
  return (
    event.event === "agent_run.start.result" &&
    typeof event.run_id === "string" &&
    event.run_id.startsWith("ar_") &&
    event.llm_provider === EXPECTED_LLM.provider &&
    event.llm_model === EXPECTED_LLM.model &&
    event.llm_base_url === EXPECTED_LLM.baseUrl &&
    event.api_key_configured === true &&
    event.api_key_masked === true
  );
}

async function waitForReadyEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before Agent Run loaded, exit code ${child.exitCode}`
      );
    }

    const ready = readEvents().find(validateReadyEvent);
    if (ready) return ready;
    await sleep(500);
  }
  throw new Error("Timed out waiting for Agent Run native ready event");
}

async function waitForStartResultEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before Agent Run started, exit code ${child.exitCode}`
      );
    }

    const event = readEvents().find(validateStartResultEvent);
    if (event) return event;
    await sleep(500);
  }
  throw new Error("Timed out waiting for Agent Run start result event");
}

function readAgentRun(runId) {
  const path = join(ROOT_DIR, "outputs", "agent_runs", `${runId}.json`);
  return {
    path,
    payload: JSON.parse(readFileSync(path, "utf8")),
  };
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
    const readyEvent = await waitForReadyEvent(args, child);
    const startEvent = await waitForStartResultEvent(args, child);
    const runRecord = readAgentRun(startEvent.run_id);
    const llmSummary = runRecord.payload.run?.llm_config_summary ?? {};
    if (
      llmSummary.provider !== EXPECTED_LLM.provider ||
      llmSummary.model !== EXPECTED_LLM.model ||
      llmSummary.base_url !== EXPECTED_LLM.baseUrl ||
      llmSummary.api_key?.configured !== true ||
      llmSummary.api_key?.masked !== true
    ) {
      throw new Error(
        `Agent Run record did not preserve persisted LLM summary: ${JSON.stringify(llmSummary)}`
      );
    }
    if (JSON.stringify(runRecord.payload).includes("llm_api_key_placeholder")) {
      throw new Error("Agent Run record leaked policy secret storage fields");
    }
    console.log(
      JSON.stringify({
        ok: true,
        driver: "tauri-native-autorun",
        scenario: SCENARIO,
        run_id: startEvent.run_id,
        status: startEvent.status,
        profile_count: readyEvent.profile_count,
        selected_profile_id: readyEvent.selected_profile_id,
        agent_run_record: runRecord.path,
        policy: TEMP_POLICY_PATH,
        llm_provider: EXPECTED_LLM.provider,
        llm_model: EXPECTED_LLM.model,
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
