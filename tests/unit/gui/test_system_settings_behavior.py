"""Settings UI behavior through the real React page and synthetic Tauri IPC.

Uses the installed browser and UI dependencies; no native sidecar or model is called.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROVIDERS = ("lm_studio", "strata", "openai", "openai_compatible", "deepseek")


def _config(provider="deepseek", enabled=None, effort="high"):
    return {
        "provider": provider,
        "model": "synthetic-model",
        "base_url": (
            "http://127.0.0.1:47831/v1"
            if provider == "strata"
            else "https://synthetic.invalid/v1"
        ),
        "api_key": {"configured": False, "masked": False, "updated_at": ""},
        "timeout": 30,
        "temperature": 0.1,
        "thinking_enabled": enabled,
        "thinking_effort": effort,
    }


CASES = {
    **{
        f"save_{provider}_{mode}": {
            "config": _config(provider, enabled, "low"),
            "operations": [{"save": True}],
        }
        for provider in PROVIDERS
        for mode, enabled in (("default", None), ("off", False), ("on", True))
    },
    **{
        f"choose_{provider}": {
            "config": _config(provider),
            "operations": [
                {"mode": "On"}, {"effort": "Low"}, {"save": True},
                {"mode": "Off"}, {"save": True},
                {"mode": "Provider default"}, {"save": True},
            ],
        }
        for provider in PROVIDERS
    },
    "provider_change": {
        "config": _config("deepseek", True, "max"),
        "operations": [
            {"provider": "openai_compatible"},
            {"base_url": "https://second.invalid/v1"}, {"save": True},
        ],
    },
    "endpoint_change": {
        "config": _config("deepseek", True, "low"),
        "operations": [{"base_url": "https://second.invalid/v1"}, {"save": True}],
    },
    "same_endpoint": {
        "config": _config("deepseek", True, "max"),
        "operations": [{"base_url": " https://synthetic.invalid/v1/ "}, {"save": True}],
    },
    "model_only": {
        "config": _config("deepseek", True, "max"),
        "operations": [{"model": "another-model"}, {"save": True}],
    },
    "same_provider": {
        "config": _config("deepseek", False, "low"),
        "operations": [{"provider": "deepseek"}, {"save": True}],
    },
    "explicit_after_change": {
        "config": _config("deepseek", True, "max"),
        "operations": [
            {"provider": "openai_compatible"},
            {"base_url": "https://second.invalid/v1"}, {"mode": "On"},
            {"effort": "Low"}, {"save": True},
        ],
    },
    "empty_endpoint": {
        "config": _config("deepseek", True, "low"),
        "operations": [{"base_url": "  "}, {"save_error": True}],
    },
    "strata_max": {
        "config": _config("strata", True, "max"),
        "operations": [{"save": True}],
    },
}


SETTINGS_ENTRY = r"""
import React from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { mockIPC } from "@tauri-apps/api/mocks";
import i18n from "/src/i18n/index.ts";
import { SystemSettingsPage } from "/src/pages/system-settings/index.tsx";
await i18n.changeLanguage("en");
let root;
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const waitFor = async (predicate) => {
  for (let i = 0; i < 200; i++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error("Component did not reach the expected state");
};
window.runSettingsCase = async ({config, operations}) => {
  if (root) root.unmount();
  document.getElementById("root").replaceChildren();
  const settings = {
    meta: {correlation_id: "synthetic-ui"},
    gate_policy: {gate_mode: "manual", delivery_mode: "manual", batch_review: false},
    exclusion_list: [], excluded_legal_entities: [], material_source_roots: [],
    channels: [], liepin_api: {configured: false, state: "unconfigured"},
    llm_config: structuredClone(config),
  };
  const saves = [];
  let reads = 0;
  mockIPC((command, args) => {
    if (command !== "sidecar_request") throw new Error("Unexpected native call: " + command);
    const request = JSON.parse(args.request);
    let result;
    if (request.method === "settings.get") {
      reads++;
      result = settings;
    } else if (request.method === "settings.update" && request.params.section === "llm_config") {
      const payload = structuredClone(request.params.payload);
      saves.push(payload);
      if (Object.hasOwn(payload, "base_url") && !payload.base_url.trim()) {
        return JSON.stringify({jsonrpc: "2.0", id: request.id, error: {
          code: "VALIDATION_ERROR", message: "base_url must be a non-empty string",
          details: {retryable: false},
        }});
      }
      const {api_key, ...publicFields} = payload;
      settings.llm_config = {...settings.llm_config, ...publicFields};
      result = {meta: {correlation_id: "synthetic-ui"}, section: "llm_config", saved: true};
    } else {
      throw new Error("Unexpected RPC: " + request.method);
    }
    return JSON.stringify({jsonrpc: "2.0", id: request.id, result});
  });
  root = createRoot(document.getElementById("root"));
  root.render(React.createElement(
    MemoryRouter, {initialEntries: ["/settings?section=llm"]},
    React.createElement(SystemSettingsPage),
  ));
  await waitFor(() => document.querySelector('[data-testid="settings-llm-model"]'));
  const view = () => ({
    effortVisible: !!document.querySelector('[role="group"][aria-label="Thinking effort"]'),
    efforts: Array.from(document.querySelectorAll('[role="group"][aria-label="Thinking effort"] button'))
      .map(button => ({name: button.textContent.trim(), selected: button.getAttribute("aria-pressed") === "true"})),
  });
  const states = [];
  const click = (element, label) => {
    if (!element || element.disabled) throw new Error("Missing operable control: " + label);
    element.click();
  };
  const edit = (element, value) => {
    if (!element || element.readOnly) throw new Error("Missing editable field");
    const prototype = element instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, "value").set.call(element, value);
    element.dispatchEvent(new Event(element instanceof HTMLSelectElement ? "change" : "input", {bubbles: true}));
  };
  let error = null;
  try {
    for (const operation of operations) {
      if (operation.provider) {
        click(document.querySelector('[data-testid="settings-llm-provider-' + operation.provider + '"]'), operation.provider);
      } else if (Object.hasOwn(operation, "base_url")) {
        edit(document.querySelector('[data-testid="settings-llm-base-url"]'), operation.base_url);
      } else if (operation.model) {
        edit(document.querySelector('[data-testid="settings-llm-model"]'), operation.model);
      } else if (operation.mode) {
        const select = document.querySelector('select[aria-label="Thinking mode"]');
        if (select) {
          const option = Array.from(select.options).find(item => item.textContent.trim() === operation.mode);
          if (!option) throw new Error("Missing thinking choice: " + operation.mode);
          edit(select, option.value);
        } else {
          const choice = Array.from(document.querySelectorAll('button,[role="radio"],input[type="radio"]'))
            .find(item => (item.getAttribute("aria-label") || item.textContent.trim()) === operation.mode);
          click(choice, operation.mode);
        }
      } else if (operation.effort) {
        const choice = Array.from(document.querySelectorAll('[role="group"][aria-label="Thinking effort"] button'))
          .find(item => item.textContent.trim() === operation.effort);
        click(choice, operation.effort);
      } else if (operation.save || operation.save_error) {
        states.push(view());
        const count = saves.length;
        const readCount = reads;
        click(document.querySelector('[data-testid="settings-save"]'), "Save");
        await waitFor(() => saves.length === count + 1 && (operation.save_error || reads > readCount));
        await waitFor(() => !document.querySelector('[data-testid="settings-save"]').disabled);
      }
      await tick();
    }
  } catch (reason) {
    error = String(reason.message || reason);
  }
  return {saves, states, error,
    validationErrorVisible: document.body.innerText.includes("base_url must be a non-empty string"),
    savedNoticeVisible: document.body.innerText.includes("Model configuration saved"),
  };
};
"""


# The two real component consumers share only browser setup, not their business fixtures.
NODE_DRIVER = r"""
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "vite";
import react from "@vitejs/plugin-react";

const cases = __CASES__;
const chrome = __CHROME__;
const entry = __ENTRY__;
const runFunction = __RUN_FUNCTION__;
const temporary = await mkdtemp(path.join(tmpdir(), "ppf-component-ui-"));
const pause = (ms) => new Promise(resolve => setTimeout(resolve, ms));
let server;
let browser;
let socket;
let stderr = "";
try {
  server = await createServer({
    root: process.cwd(), configFile: false, logLevel: "silent",
    cacheDir: path.join(temporary, "vite-cache"),
    resolve: {alias: {"@": path.join(process.cwd(), "src")}},
    plugins: [
      react(),
      {
        name: "component-test",
        resolveId(id) { if (id === "/__component_test__.js") return "\0component-test"; },
        load(id) { if (id === "\0component-test") return entry; },
        configureServer(vite) {
          vite.middlewares.use(async (request, response, next) => {
            if (request.url !== "/__component_test__") return next();
            response.setHeader("Content-Type", "text/html");
            response.end(await vite.transformIndexHtml(request.url,
              '<html><body><div id="root"></div><script type="module" src="/__component_test__.js"></script></body></html>'));
          });
        },
      },
    ],
    optimizeDeps: {noDiscovery: true, include: [
      "react", "react/jsx-runtime", "react-dom/client", "react-router-dom",
      "react-i18next", "i18next", "lucide-react", "zustand",
      "@tauri-apps/api/core", "@tauri-apps/api/mocks",
    ]},
    server: {host: "127.0.0.1", port: 0, hmr: false},
  });
  await server.listen();
  const port = server.httpServer.address().port;
  browser = spawn(chrome, [
    "--headless=new", "--remote-debugging-port=0",
    "--user-data-dir=" + temporary, "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-component-update",
    "--disable-extensions", "--disable-sync", "--no-proxy-server",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
    "about:blank",
  ], {stdio: ["ignore", "ignore", "pipe"]});
  browser.stderr.on("data", chunk => { stderr = (stderr + chunk).slice(-5000); });
  let devtoolsPort;
  for (let i = 0; i < 200; i++) {
    try { devtoolsPort = (await readFile(path.join(temporary, "DevToolsActivePort"), "utf8")).split("\n")[0]; break; }
    catch { await pause(25); }
  }
  if (!devtoolsPort) throw new Error("Chrome did not start: " + stderr);
  const tabs = await (await fetch("http://127.0.0.1:" + devtoolsPort + "/json/list")).json();
  socket = new WebSocket(tabs.find(tab => tab.type === "page").webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  let sequence = 0;
  const pending = new Map();
  const forbidden = [];
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("CDP timeout: " + method)); }, 20000);
    pending.set(id, {resolve, reject, timer});
    socket.send(JSON.stringify({id, method, params}));
  });
  socket.onmessage = ({data}) => {
    const message = JSON.parse(data);
    if (message.id) {
      const item = pending.get(message.id);
      if (!item) return;
      clearTimeout(item.timer); pending.delete(message.id);
      if (message.error) item.reject(new Error(JSON.stringify(message.error)));
      else item.resolve(message.result);
    } else if (message.method === "Fetch.requestPaused") {
      const {requestId, request} = message.params;
      const url = new URL(request.url);
      const allowed = url.protocol === "data:" || (url.hostname === "127.0.0.1" && Number(url.port) === port);
      if (!allowed) forbidden.push(request.url);
      void call(allowed ? "Fetch.continueRequest" : "Fetch.failRequest",
        allowed ? {requestId} : {requestId, errorReason: "BlockedByClient"})
        .catch(reason => { if (!/navigated|closed|Invalid InterceptionId/.test(String(reason))) forbidden.push(String(reason)); });
    }
  };
  const evaluate = async (expression) => {
    const result = await call("Runtime.evaluate", {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await call("Fetch.enable", {patterns: [{urlPattern: "*"}]});
  await call("Page.navigate", {url: "http://127.0.0.1:" + port + "/__component_test__"});
  let ready = false;
  for (let i = 0; i < 300; i++) {
    try {
      if (await evaluate("typeof window[" + JSON.stringify(runFunction) + "] === 'function'")) { ready = true; break; }
    } catch (reason) {
      if (!/context|navigated|closed/.test(String(reason))) throw reason;
    }
    await pause(25);
  }
  if (!ready) throw new Error("Component entry did not load: " + await evaluate("document.body.innerText"));
  const observations = {};
  for (const [name, fixture] of Object.entries(cases)) {
    observations[name] = await evaluate("window[" + JSON.stringify(runFunction) + "](" + JSON.stringify(fixture) + ")");
  }
  if (forbidden.length) throw new Error("Non-test network blocked: " + forbidden.join(", "));
  console.log("COMPONENT_BEHAVIOR=" + JSON.stringify(observations));
} finally {
  socket?.close();
  if (browser && browser.exitCode === null) {
    browser.kill("SIGTERM");
    await Promise.race([new Promise(resolve => browser.once("exit", resolve)), pause(2000)]);
    if (browser.exitCode === null) browser.kill("SIGKILL");
  }
  await server?.close();
  await rm(temporary, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
}
"""


def run_component_cases(entry, cases, run_function):
    node = shutil.which("node")
    chrome = shutil.which("google-chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not node or not Path(chrome).is_file():
        pytest.skip("Component behavior requires the installed Node and Chrome runtimes")
    driver = (NODE_DRIVER.replace("__CASES__", json.dumps(cases))
              .replace("__CHROME__", json.dumps(chrome))
              .replace("__ENTRY__", json.dumps(entry))
              .replace("__RUN_FUNCTION__", json.dumps(run_function)))
    result = subprocess.run(
        [node, "--input-type=module"],
        input=driver, cwd=ROOT / "ui", text=True, capture_output=True, timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    prefix = "COMPONENT_BEHAVIOR="
    output = next(line[len(prefix):] for line in result.stdout.splitlines() if line.startswith(prefix))
    return json.loads(output)


@pytest.fixture(scope="module")
def settings_behavior():
    return run_component_cases(SETTINGS_ENTRY, CASES, "runSettingsCase")


def _case(observations, name):
    actual = observations[name]
    assert actual["error"] is None, actual
    return actual


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize(("mode", "expected"), (("default", None), ("off", False), ("on", True)))
def test_settings_preserves_three_state_configuration_at_rpc_boundary(settings_behavior, provider, mode, expected):
    actual = _case(settings_behavior, f"save_{provider}_{mode}")
    payload = actual["saves"][0]
    assert "thinking_enabled" in payload, payload
    assert payload["thinking_enabled"] is expected, payload
    assert payload["thinking_effort"] == "low", payload
    assert actual["states"][0]["effortVisible"] is (expected is True)


@pytest.mark.parametrize("provider", PROVIDERS)
def test_settings_user_can_select_all_three_modes_and_only_on_shows_effort(settings_behavior, provider):
    actual = _case(settings_behavior, f"choose_{provider}")
    assert [payload["thinking_enabled"] for payload in actual["saves"]] == [True, False, None]
    assert [state["effortVisible"] for state in actual["states"]] == [True, False, False]
    assert actual["saves"][0]["thinking_effort"] == "low"


@pytest.mark.parametrize("name", ("provider_change", "endpoint_change"))
def test_settings_deployment_change_resets_unconfirmed_thinking_controls(settings_behavior, name):
    actual = _case(settings_behavior, name)
    assert actual["saves"][0]["thinking_enabled"] is None, actual
    assert actual["saves"][0]["thinking_effort"] == "high", actual
    assert actual["states"][0]["effortVisible"] is False


@pytest.mark.parametrize(("name", "enabled", "effort"), (
    ("same_endpoint", True, "max"), ("model_only", True, "max"), ("same_provider", False, "low"),
))
def test_settings_same_deployment_or_model_only_preserves_controls(settings_behavior, name, enabled, effort):
    actual = _case(settings_behavior, name)
    assert actual["saves"][0]["thinking_enabled"] is enabled
    assert actual["saves"][0]["thinking_effort"] == effort


def test_settings_explicit_selection_after_deployment_change_is_saved(settings_behavior):
    actual = _case(settings_behavior, "explicit_after_change")
    assert actual["saves"][0]["thinking_enabled"] is True
    assert actual["saves"][0]["thinking_effort"] == "low"


def test_settings_empty_endpoint_is_submitted_and_validation_failure_is_visible(settings_behavior):
    actual = _case(settings_behavior, "empty_endpoint")
    assert "base_url" in actual["saves"][0], actual
    assert actual["saves"][0]["base_url"] == "", actual
    assert actual["validationErrorVisible"] is True, actual
    assert actual["savedNoticeVisible"] is False, actual


def test_settings_strata_existing_max_is_displayed_and_saved_as_high(settings_behavior):
    actual = _case(settings_behavior, "strata_max")
    assert actual["saves"][0]["thinking_enabled"] is True
    assert actual["saves"][0]["thinking_effort"] == "high"
    assert actual["states"][0]["efforts"] == [
        {"name": "Low", "selected": False}, {"name": "High", "selected": True},
    ]
