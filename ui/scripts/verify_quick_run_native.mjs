#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

const UI_DIR = resolve(new URL("..", import.meta.url).pathname);
const ROOT_DIR = resolve(UI_DIR, "..");
const OUTPUTS_DIR = join(ROOT_DIR, "outputs");
const QUICK_RUNS_DIR = join(OUTPUTS_DIR, "quick_runs");
const MATERIALS_DIR = join(ROOT_DIR, "materials");
const ARTIFACT_DIR = join(UI_DIR, "test-results", "quick-run-native");
const VITE_ENV_LOCAL = join(UI_DIR, ".env.local");
const APP_EVENTS_PATH = join(ARTIFACT_DIR, "app-events.jsonl");
const TEMP_POLICY_PATH = join(ARTIFACT_DIR, "policy.yaml");
const EXPECTED_LLM = {
  provider: "quick_run_verify_provider",
  model: "quick-run-verify-model",
  baseUrl: "http://127.0.0.1:65535/v1",
};
const EXPECTED_MATERIAL = {
  materialId: "mat_quick_run_verify",
  resourceId: "res_quick_run_verify",
  label: "Quick Run verifier material",
};
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

function readEvents() {
  if (!existsSync(APP_EVENTS_PATH)) return [];
  return readFileSync(APP_EVENTS_PATH, "utf8")
    .split("\n")
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function validateReadyEvent(event) {
  if (event.event !== "quick_run.load.ready") return false;
  return (
    typeof event.evidence_count === "number" &&
    event.evidence_count >= 0 &&
    typeof event.material_source_count === "number" &&
    event.material_source_count >= 1 &&
    event.material_source_id === EXPECTED_MATERIAL.materialId &&
    typeof event.job_profile_count === "number" &&
    event.job_profile_count >= 0 &&
    event.llm_provider === EXPECTED_LLM.provider &&
    event.llm_model === EXPECTED_LLM.model &&
    event.llm_base_url === EXPECTED_LLM.baseUrl &&
    event.api_key_configured === true &&
    event.api_key_masked === true
  );
}

function validateStartResultEvent(event, runId) {
  return (
    event.event === "quick_run.start.result" &&
    event.run_id === runId &&
    event.material_source_id === EXPECTED_MATERIAL.materialId &&
    Array.isArray(event.trace_evidence_card_ids) &&
    event.trace_evidence_card_ids.includes(`ec-${runId}`) &&
    typeof event.trace_raw_source === "string" &&
    event.trace_raw_source.includes(EXPECTED_MATERIAL.materialId) &&
    event.trace_resume_traceable === true &&
    typeof event.trace_scorecard === "string" &&
    event.trace_scorecard.includes(`scorecard_mr-${runId}_A.md`) &&
    event.llm_provider === EXPECTED_LLM.provider &&
    event.llm_model === EXPECTED_LLM.model &&
    event.llm_base_url === EXPECTED_LLM.baseUrl &&
    event.api_key_configured === true &&
    event.api_key_masked === true
  );
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
    join(ROOT_DIR, "matching_reports", `mr-${runId}.yaml`),
    join(QUICK_RUNS_DIR, runId),
  ];
  for (const path of paths) {
    if (existsSync(path)) rmSync(path, { recursive: true, force: true });
  }
}

function seedMaterialSource() {
  mkdirSync(MATERIALS_DIR, { recursive: true });
  const materialPath = join(MATERIALS_DIR, `${EXPECTED_MATERIAL.materialId}.md`);
  const metaPath = join(MATERIALS_DIR, `${EXPECTED_MATERIAL.materialId}.meta.yaml`);
  writeFileSync(
    materialPath,
    [
      "# Quick Run verifier inventory platform",
      "时间：2025-06 ~ 2025-09",
      "",
      "背景：大促期间库存一致性要求 2 秒内，峰值 3k QPS。",
      "动作：",
      "- 重构 Java + Kafka 库存同步链路，削峰填谷",
      "- 引入 Redis 幂等键、补偿任务和 SLO 告警",
      "- 跨团队推进灰度、回滚和压测复盘",
      "",
      "结果：",
      "- 同步延迟 P95 从 6s 降至 1.8s，SLA 达到 99.95%",
      "- 大促库存异常工单下降 42%",
      "",
      "证据：",
      "- quick-run-verifier-design.md",
      "- quick-run-verifier-latency.png",
      "",
      "技术栈：Java, Redis, Kafka, MySQL, Prometheus",
      "",
    ].join("\n"),
    "utf8"
  );
  writeFileSync(
    metaPath,
    [
      `material_id: "${EXPECTED_MATERIAL.materialId}"`,
      `resource_id: "${EXPECTED_MATERIAL.resourceId}"`,
      `label: "${EXPECTED_MATERIAL.label}"`,
      `kind: "raw_work_material"`,
      `filename: "${EXPECTED_MATERIAL.materialId}.md"`,
      `extension: ".md"`,
      `uploaded_at: "2026-05-21T00:00:00Z"`,
      `preview: "Quick Run verifier inventory platform material"`,
      "",
    ].join("\n"),
    "utf8"
  );
}

function cleanupSeededMaterial() {
  const paths = [
    join(MATERIALS_DIR, `${EXPECTED_MATERIAL.materialId}.md`),
    join(MATERIALS_DIR, `${EXPECTED_MATERIAL.materialId}.meta.yaml`),
  ];
  for (const path of paths) {
    if (existsSync(path)) rmSync(path, { force: true });
  }
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
      QUICK_RUN_VERIFY_AUTORUN: "quick-run",
      VITE_QUICK_RUN_VERIFY_AUTORUN: "quick-run",
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

async function waitForReadyEvent(args, child) {
  const deadline = Date.now() + args.timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Tauri dev exited before Quick Run loaded, exit code ${child.exitCode}`);
    }

    const ready = readEvents().find(validateReadyEvent);
    if (ready) return ready;
    await sleep(500);
  }
  throw new Error("Timed out waiting for Quick Run native ready event");
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
  seedMaterialSource();
  const restoreViteEnv = enableViteAutorunEnv();
  const { child, logPath, logs } = startTauriDev();
  activeChild = child;
  activeRestoreViteEnv = restoreViteEnv;
  try {
    const readyEvent = await waitForReadyEvent(args, child);
    const result = await waitForRun(args, child, baseline);
    const summary = join(OUTPUTS_DIR, "agent_runs", result.runId, "summary.json");
    if (["DONE", "SKIPPED"].includes(result.status) && !existsSync(summary)) {
      throw new Error(`Quick Run finished but summary was not found: ${summary}`);
    }
    const runPayload = readQuickRun(result.record);
    const llmSummary = runPayload.run?.llm_config_summary ?? {};
    const materialSource = runPayload.run?.material_source ?? {};
    if (materialSource.material_id !== EXPECTED_MATERIAL.materialId) {
      throw new Error(
        `Quick Run record did not preserve selected material source: ${JSON.stringify(materialSource)}`
      );
    }
    if (
      llmSummary.provider !== EXPECTED_LLM.provider ||
      llmSummary.model !== EXPECTED_LLM.model ||
      llmSummary.base_url !== EXPECTED_LLM.baseUrl ||
      llmSummary.api_key?.configured !== true ||
    llmSummary.api_key?.masked !== true
  ) {
      throw new Error(
        `Quick Run record did not preserve persisted LLM summary: ${JSON.stringify(llmSummary)}`
      );
    }
    if (JSON.stringify(runPayload).includes("llm_api_key_placeholder")) {
      throw new Error("Quick Run record leaked policy secret storage fields");
    }
    const traceability = runPayload.traceability ?? {};
    if (
      !Array.isArray(traceability.evidence_card_ids) ||
      !traceability.evidence_card_ids.includes(`ec-${result.runId}`) ||
      traceability.evidence?.raw_source !== runPayload.run?.raw_path ||
      traceability.resume_traceable !== true
    ) {
      throw new Error(
        `Quick Run record did not preserve material/evidence/resume traceability: ${JSON.stringify(traceability)}`
      );
    }
    const startEvent = readEvents().find((event) =>
      validateStartResultEvent(event, result.runId)
    );
    if (!startEvent) {
      throw new Error("Quick Run verifier did not observe persisted LLM summary in start result event");
    }
    if (!args.keepArtifacts) cleanupGeneratedArtifacts(result.runId);
    console.log(
      JSON.stringify({
        ok: ["DONE", "SKIPPED"].includes(result.status),
        driver: "tauri-native-autorun",
        run_id: result.runId,
        status: result.status,
        evidence_count: readyEvent.evidence_count,
        material_source_count: readyEvent.material_source_count,
        material_source_id: EXPECTED_MATERIAL.materialId,
        job_profile_count: readyEvent.job_profile_count,
        quick_run_record: result.record,
        summary,
        policy: TEMP_POLICY_PATH,
        llm_provider: EXPECTED_LLM.provider,
        llm_model: EXPECTED_LLM.model,
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
    if (!args.keepArtifacts) cleanupSeededMaterial();
    activeChild = null;
    activeRestoreViteEnv = null;
  }
}

await main();
