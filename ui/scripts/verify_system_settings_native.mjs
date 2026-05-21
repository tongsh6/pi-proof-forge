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
import { createServer } from "node:http";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const UI_DIR = resolve(new URL("..", import.meta.url).pathname);
const ROOT_DIR = resolve(UI_DIR, "..");
const ARTIFACT_DIR = join(UI_DIR, "test-results", "system-settings-native");
const VITE_ENV_LOCAL = join(UI_DIR, ".env.local");
const APP_EVENTS_PATH = join(ARTIFACT_DIR, "app-events.jsonl");
const POLICY_PATH = join(ARTIFACT_DIR, "policy.yaml");
const ROOT_POLICY_PATH = join(ROOT_DIR, "policy.yaml");
const SCENARIO = "system-settings";
const STUB_MODELS = ["ppf-acceptance-a", "ppf-acceptance-b"];

let activeChild = null;
let activeStubServer = null;
let activeRestoreViteEnv = null;
let shuttingDown = false;

function parseArgs(argv) {
  const args = {
    timeoutMs: Number(
      process.env.SYSTEM_SETTINGS_NATIVE_VERIFY_TIMEOUT_MS || "90000"
    ),
    keepArtifacts: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--") continue;
    if (arg === "--help" || arg === "-h") {
      console.log(
        "Usage: node ui/scripts/verify_system_settings_native.mjs [--timeout-ms <ms>] [--keep-artifacts]"
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

async function startLlmStubServer() {
  const requests = [];
  const server = createServer((request, response) => {
    requests.push({
      method: request.method,
      url: request.url,
      authorization: request.headers.authorization ?? "",
    });
    if (request.method === "GET" && request.url === "/v1/models") {
      response.writeHead(200, { "content-type": "application/json" });
      response.end(
        JSON.stringify({
          object: "list",
          data: STUB_MODELS.map((id) => ({ id, object: "model" })),
        })
      );
      return;
    }
    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "not found" }));
  });

  await new Promise((resolvePromise, rejectPromise) => {
    server.once("error", rejectPromise);
    server.listen(0, "127.0.0.1", () => {
      server.off("error", rejectPromise);
      resolvePromise();
    });
  });
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Failed to start LLM stub server");
  }
  return {
    server,
    baseUrl: `http://127.0.0.1:${address.port}/v1`,
    requests,
  };
}

async function stopLlmStubServer(server) {
  if (!server) return;
  await new Promise((resolvePromise) => {
    server.close(() => resolvePromise());
  });
}

function startTauriDev(stubBaseUrl) {
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  if (existsSync(APP_EVENTS_PATH)) unlinkSync(APP_EVENTS_PATH);
  const logPath = join(ARTIFACT_DIR, "tauri.log");
  const child = spawn("pnpm", ["tauri", "dev"], {
    cwd: UI_DIR,
    env: {
      ...process.env,
      QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
      VITE_QUICK_RUN_VERIFY_AUTORUN: SCENARIO,
      VITE_NATIVE_VERIFY: "1",
      VITE_SYSTEM_SETTINGS_DEEP_VERIFY: "1",
      VITE_SYSTEM_SETTINGS_LLM_STUB_BASE_URL: stubBaseUrl,
      PPF_POLICY_PATH: POLICY_PATH,
      LLM_PROVIDER: "openai",
      LLM_MODEL: "gpt-4",
      LLM_BASE_URL: "",
      LLM_API_KEY: "",
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
  if (event.event !== "system_settings.load.ready") return false;
  if (event.channel_count < 2) return false;
  if (!Array.isArray(event.channel_ids)) return false;
  if (!event.channel_ids.includes("liepin")) return false;
  if (!event.channel_ids.includes("email")) return false;
  if (typeof event.llm_provider !== "string" || !event.llm_provider) return false;
  return true;
}

function validateLlmFormReadyEvent(event) {
  if (event.event !== "system_settings.llm.form.ready") return false;
  if (event.has_provider !== true) return false;
  if (event.has_model !== true) return false;
  if (event.has_base_url_field !== true) return false;
  if (event.has_timeout !== true) return false;
  if (event.has_temperature !== true) return false;
  if (typeof event.api_key_configured !== "boolean") return false;
  if (event.supports_provider_defaults !== true) return false;
  if (event.supports_detected_model_select !== true) return false;
  return true;
}

function validateDeepVerifyEvent(event, stubBaseUrl) {
  if (event.event !== "system_settings.llm.deep_verify.result") return false;
  if (event.ok !== true) return false;
  if (event.provider_default_ok !== true) return false;
  if (event.connection_status !== "pass") return false;
  if (event.connection_code !== "OK") return false;
  if (event.detected_model_count !== STUB_MODELS.length) return false;
  if (!Array.isArray(event.detected_models)) return false;
  for (const model of STUB_MODELS) {
    if (!event.detected_models.includes(model)) return false;
  }
  if (event.selected_model !== STUB_MODELS[1]) return false;
  if (event.persisted_provider !== "lm_studio") return false;
  if (event.persisted_model !== STUB_MODELS[1]) return false;
  if (event.persisted_base_url !== stubBaseUrl) return false;
  if (event.api_key_configured !== true) return false;
  if (event.api_key_masked !== true) return false;
  if (event.plaintext_secret_exposed !== false) return false;
  if (event.blocked_status !== "blocked") return false;
  if (event.blocked_code !== "BLOCKED_LOCAL_PROVIDER") return false;
  if (event.blocked_model_count !== 0) return false;
  return true;
}

async function waitForReadyEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before System Settings loaded, exit code ${child.exitCode}`
      );
    }

    const ready = readEvents().find(validateReadyEvent);
    if (ready) return ready;
    await sleep(500);
  }
  throw new Error("Timed out waiting for System Settings native ready event");
}

async function waitForLlmFormReadyEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before System Settings LLM form loaded, exit code ${child.exitCode}`
      );
    }

    const ready = readEvents().find(validateLlmFormReadyEvent);
    if (ready) return ready;
    await sleep(500);
  }
  throw new Error("Timed out waiting for System Settings LLM form ready event");
}

async function waitForDeepVerifyEvent(args, child, stubBaseUrl) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(
        `Tauri dev exited before System Settings LLM deep verify completed, exit code ${child.exitCode}`
      );
    }

    const ready = readEvents().find((event) =>
      validateDeepVerifyEvent(event, stubBaseUrl)
    );
    if (ready) return ready;
    const error = readEvents().find(
      (event) => event.event === "system_settings.llm.deep_verify.error"
    );
    if (error) {
      throw new Error(`System Settings LLM deep verify failed: ${error.error}`);
    }
    await sleep(500);
  }
  throw new Error("Timed out waiting for System Settings LLM deep verify event");
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
  if (activeStubServer) await stopLlmStubServer(activeStubServer);
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
  const rootPolicyBefore = existsSync(ROOT_POLICY_PATH)
    ? readFileSync(ROOT_POLICY_PATH, "utf8")
    : null;
  if (!args.keepArtifacts && existsSync(ARTIFACT_DIR)) {
    rmSync(ARTIFACT_DIR, { recursive: true, force: true });
  }
  mkdirSync(ARTIFACT_DIR, { recursive: true });
  const llmStub = await startLlmStubServer();
  const restoreViteEnv = enableViteAutorunEnv();
  const { child, logPath, logs } = startTauriDev(llmStub.baseUrl);
  activeChild = child;
  activeStubServer = llmStub.server;
  activeRestoreViteEnv = restoreViteEnv;

  try {
    const event = await waitForReadyEvent(args, child);
    const llmFormEvent = await waitForLlmFormReadyEvent(args, child);
    const deepVerifyEvent = await waitForDeepVerifyEvent(
      args,
      child,
      llmStub.baseUrl
    );
    const modelsRequests = llmStub.requests.filter(
      (request) => request.method === "GET" && request.url === "/v1/models"
    );
    if (modelsRequests.length < 1) {
      throw new Error("LLM stub server did not receive a /v1/models request");
    }
    if (
      !modelsRequests.some(
        (request) => request.authorization === "Bearer lm-studio"
      )
    ) {
      throw new Error("LLM stub server did not receive the expected dummy key");
    }
    const rootPolicyAfter = existsSync(ROOT_POLICY_PATH)
      ? readFileSync(ROOT_POLICY_PATH, "utf8")
      : null;
    if (rootPolicyAfter !== rootPolicyBefore) {
      throw new Error("System Settings LLM deep verify modified root policy.yaml");
    }
    console.log(
      JSON.stringify({
        ok: true,
        driver: "tauri-native-autorun",
        scenario: SCENARIO,
        channel_count: event.channel_count,
        channel_ids: event.channel_ids,
        llm_provider: event.llm_provider,
        llm_form_ready: true,
        api_key_configured: llmFormEvent.api_key_configured,
        supports_provider_defaults: true,
        supports_detected_model_select: true,
        deep_verify: true,
        llm_stub_base_url: llmStub.baseUrl,
        detected_model_count: deepVerifyEvent.detected_model_count,
        selected_model: deepVerifyEvent.selected_model,
        persisted_model: deepVerifyEvent.persisted_model,
        blocked_code: deepVerifyEvent.blocked_code,
        model_requests: modelsRequests.length,
        policy: POLICY_PATH,
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
    await stopLlmStubServer(llmStub.server);
    restoreViteEnv();
    activeChild = null;
    activeStubServer = null;
    activeRestoreViteEnv = null;
  }
}

await main();
