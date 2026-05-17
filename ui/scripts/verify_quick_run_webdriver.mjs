#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const UI_DIR = resolve(new URL("..", import.meta.url).pathname);
const ROOT_DIR = resolve(UI_DIR, "..");
const DEFAULT_APP_BINARY =
  process.platform === "win32"
    ? join(UI_DIR, "src-tauri", "target", "release", "piproofforge.exe")
    : join(UI_DIR, "src-tauri", "target", "release", "piproofforge");
const WEBDRIVER_ELEMENT_ID = "element-6066-11e4-a52e-4f735466cecf";

function parseArgs(argv) {
  const args = {
    app: DEFAULT_APP_BINARY,
    driver: process.env.TAURI_DRIVER || "tauri-driver",
    port: Number(process.env.TAURI_DRIVER_PORT || "4444"),
    timeoutMs: Number(process.env.TAURI_WEBDRIVER_TIMEOUT_MS || "90000"),
    keepArtifacts: false,
    requireSupported: process.env.PPF_REQUIRE_TAURI_WEBDRIVER === "1",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      continue;
    }
    if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    }
    if (arg === "--app") {
      args.app = resolve(argv[++i]);
      continue;
    }
    if (arg === "--driver") {
      args.driver = argv[++i];
      continue;
    }
    if (arg === "--port") {
      args.port = Number(argv[++i]);
      continue;
    }
    if (arg === "--timeout-ms") {
      args.timeoutMs = Number(argv[++i]);
      continue;
    }
    if (arg === "--keep-artifacts") {
      args.keepArtifacts = true;
      continue;
    }
    if (arg === "--require-supported") {
      args.requireSupported = true;
      continue;
    }
    throw new Error(`Unknown argument: ${arg}`);
  }

  return args;
}

function printHelp() {
  console.log(`Usage: node ui/scripts/verify_quick_run_webdriver.mjs [options]

Runs a Tauri WebDriver E2E check for Quick Run.

Options:
  --app <path>          Tauri app binary path
  --driver <path>      tauri-driver binary path (default: tauri-driver)
  --port <port>        WebDriver port (default: 4444)
  --timeout-ms <ms>    Overall timeout (default: 90000)
  --keep-artifacts     Keep generated evidence/matching artifacts
  --require-supported  Fail instead of skip on unsupported platforms
`);
}

function ensureSupportedPlatform(requireSupported) {
  if (process.platform !== "darwin") return true;

  const message =
    "Tauri WebDriver desktop automation is unsupported on macOS because WKWebView has no native WebDriver driver. Use e2e:quick-run native verifier locally, or run WebDriver on Linux/Windows CI.";
  if (requireSupported) {
    throw new Error(message);
  }
  console.log(JSON.stringify({ ok: true, skipped: true, reason: message }));
  return false;
}

function ensureAppExists(appPath) {
  if (!existsSync(appPath)) {
    throw new Error(
      `Tauri app binary not found: ${appPath}. Build it first with: pnpm --dir ui tauri build`
    );
  }
}

function startDriver(command, port) {
  const child = spawn(command, ["--port", String(port)], {
    cwd: ROOT_DIR,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });
  child.on("exit", (code) => {
    if (code !== null && code !== 0) {
      console.error(`tauri-driver exited with code ${code}: ${stderr}`);
    }
  });
  return child;
}

async function webdriverRequest(port, method, path, body = undefined) {
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(`Invalid WebDriver JSON response for ${method} ${path}: ${text}`);
  }
  if (!response.ok || payload.value?.error) {
    throw new Error(
      `WebDriver ${method} ${path} failed: ${JSON.stringify(payload.value ?? payload)}`
    );
  }
  return payload.value;
}

async function waitForDriver(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      await webdriverRequest(port, "GET", "/status");
      return;
    } catch (error) {
      lastError = error;
      await sleep(250);
    }
  }
  throw new Error(`tauri-driver did not become ready: ${lastError}`);
}

async function createSession(port, appPath) {
  const value = await webdriverRequest(port, "POST", "/session", {
    capabilities: {
      alwaysMatch: {
        "tauri:options": {
          application: appPath,
        },
      },
    },
  });
  if (!value.sessionId) {
    throw new Error(`WebDriver session missing sessionId: ${JSON.stringify(value)}`);
  }
  return value.sessionId;
}

async function deleteSession(port, sessionId) {
  try {
    await webdriverRequest(port, "DELETE", `/session/${sessionId}`);
  } catch {
    // The app may already be closed; cleanup is best effort.
  }
}

async function execute(port, sessionId, script, args = []) {
  return webdriverRequest(port, "POST", `/session/${sessionId}/execute/sync`, {
    script,
    args,
  });
}

async function bodyText(port, sessionId) {
  return execute(port, sessionId, "return document.body.innerText;");
}

async function findElementByText(port, sessionId, text) {
  const xpath = `//*[self::button or self::a or @role='button'][contains(normalize-space(.), ${JSON.stringify(text)})]`;
  const value = await webdriverRequest(port, "POST", `/session/${sessionId}/element`, {
    using: "xpath",
    value: xpath,
  });
  return value[WEBDRIVER_ELEMENT_ID];
}

async function clickElement(port, sessionId, elementId) {
  await webdriverRequest(
    port,
    "POST",
    `/session/${sessionId}/element/${elementId}/click`,
    {}
  );
}

async function waitForText(port, sessionId, matcher, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let latest = "";
  while (Date.now() < deadline) {
    latest = String(await bodyText(port, sessionId));
    if (matcher(latest)) return latest;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for page text. Latest body:\n${latest}`);
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

async function runQuickRunE2E(args) {
  ensureAppExists(args.app);
  const driver = startDriver(args.driver, args.port);
  let sessionId = "";
  let runId = "";
  try {
    await waitForDriver(args.port, 15000);
    sessionId = await createSession(args.port, args.app);
    await waitForText(args.port, sessionId, (text) => text.includes("快速运行") || text.includes("Quick Run"), args.timeoutMs);

    const navId = await findElementByText(args.port, sessionId, "快速运行").catch(() =>
      findElementByText(args.port, sessionId, "Quick Run")
    );
    await clickElement(args.port, sessionId, navId);

    await waitForText(args.port, sessionId, (text) => text.includes("启动运行") || text.includes("Start Run"), args.timeoutMs);
    const startId = await findElementByText(args.port, sessionId, "启动运行").catch(() =>
      findElementByText(args.port, sessionId, "Start Run")
    );
    await clickElement(args.port, sessionId, startId);

    const finalText = await waitForText(
      args.port,
      sessionId,
      (text) => /qr_\d+/.test(text) && (text.includes("DONE") || text.includes("SKIPPED")),
      args.timeoutMs
    );
    runId = finalText.match(/qr_\d+/)?.[0] ?? "";
    const summaryPath = join(ROOT_DIR, "outputs", "agent_runs", runId, "summary.json");
    if (!runId || !existsSync(summaryPath)) {
      throw new Error(`Quick Run completed in UI but summary was not found: ${summaryPath}`);
    }

    if (!args.keepArtifacts) cleanupGeneratedArtifacts(runId);
    console.log(
      JSON.stringify({
        ok: true,
        run_id: runId,
        summary: summaryPath,
      })
    );
  } finally {
    if (sessionId) await deleteSession(args.port, sessionId);
    driver.kill();
  }
}

try {
  const args = parseArgs(process.argv.slice(2));
  if (ensureSupportedPlatform(args.requireSupported)) {
    await runQuickRunE2E(args);
  }
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
