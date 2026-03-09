# PiProofForge GUI Architecture

## 1. Overview

This document defines the final GUI architecture for PiProofForge.

- Product form: desktop application
- Shell: Tauri
- Frontend: React 18 + TypeScript + Tailwind CSS + Zustand
- Backend runtime: Python sidecar reusing the existing `tools/` capabilities
- Source of truth: `ui/design/DESIGN.md` and `ui/design/piproofforge.pen`

The GUI is the final desktop interaction layer for the evidence-first workflow: evidence extraction, matching, resume generation, evaluation, job lead management, and submission tracking.

## 2. Architecture Principles

- Single product baseline: all GUI implementation and review follow `ui/design/DESIGN.md`
- Evidence-first: the Evidence page is the core asset hub, not an auxiliary screen
- Explicit separation: Quick Run and Agent Run are different products flows and must stay separate
- Desktop-native orchestration: the frontend communicates with the Python sidecar through a local desktop bridge, not through a remote-style web API
- Single-language runtime UI: bilingual labels are design annotations only; runtime text comes from i18n resources

## 3. Tech Stack

### Frontend

- React 18
- TypeScript
- Tailwind CSS
- Zustand
- i18n resource files under `ui/src/i18n/`

### Desktop Shell

- Tauri
- Rust shell for window lifecycle, native menus, file dialogs, and sidecar process control

### Backend Execution Layer

- Python sidecar
- Reuse existing domain and pipeline capabilities from `tools/`

## 4. Communication Model

The final communication model is `JSON-RPC over stdio` between the Tauri host and the Python sidecar.

### Why this is the final choice

- Fits desktop deployment without adding HTTP service lifecycle complexity
- Avoids introducing a second server runtime solely for GUI integration
- Supports request/response, streaming-style progress events, heartbeats, and structured error handling
- Keeps the bridge local to the desktop app process model

### Protocol requirements

- Version negotiation on sidecar startup
- Heartbeat messages for liveness detection
- Request timeout handling and retry policy where safe
- Structured error handling follows the error code baseline in `ui/design/contracts/sidecar-rpc.md`
- Suggested higher-level grouping for UI presentation:
  - connectivity: `SIDECAR_UNAVAILABLE`
  - timeout: `TIMEOUT`
  - business: `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`, `PERMISSION_DENIED`
  - system: `INTERNAL_ERROR`, `STORAGE_ERROR`, `UNSUPPORTED_VERSION`
- Correlation IDs for every request and event stream

## 5. Runtime Topology

1. Tauri starts the desktop shell.
2. The shell boots the web frontend.
3. The shell launches the Python sidecar.
4. The shell establishes a JSON-RPC stdio bridge.
5. The React app issues typed commands through the Tauri bridge.
6. The Python sidecar executes evidence, matching, generation, evaluation, discovery, and submission tasks.
7. Progress, logs, status transitions, and results stream back into the frontend state store.

## 6. Frontend Application Model

### Navigation model

The GUI follows the final nine-page information architecture defined in `ui/design/DESIGN.md`:

1. Overview
2. Resumes
3. Evidence
4. Jobs
5. Quick Run
6. Agent Run
7. Submissions
8. Policy
9. System Settings

### State model

Use Zustand stores to manage:

- sidecar connection state
- active language
- page-level loading, empty, and error states
- quick run execution state
- agent run state machine and gate state
- agent run review state（审批面板状态、pending candidates 列表、review decisions 映射）
- evidence selection and artifacts state

### Internationalization model

- All user-visible runtime text must come from translation keys
- Language switcher lives at the bottom of SideNav
- Bilingual labels such as `Overview / 概览` are design-only annotations and must not appear in runtime UI
- Technical tags, codes, and status keywords that are intentionally English remain untranslated where specified by `ui/design/DESIGN.md`

## 7. Domain-to-UI Mapping

### Evidence

- Evidence cards are first-class domain assets
- `artifacts` are visible and operable in the detail panel
- Import, preview, delete, and re-upload are part of the product requirement

### Quick Run

- Represents a single-pass pipeline visualization
- Covers extract, match, generate, evaluate
- No multi-round gate system

### Agent Run

- Represents the autonomous multi-round execution loop
- Shows the ten-state machine, gate progress, review flow, and event stream
- Must not collapse into the Quick Run model
- **REVIEW state** (only active when `delivery_mode=manual`):
  - Left panel switches to the candidate review panel
  - Displays TopN candidate details: JD summary, match score, generated resume version
  - Supports two review modes:
    - Per-round review (`batch_review=false`): pauses after each round, user reviews and continues
    - Batch review (`batch_review=true`): runs all rounds first, then presents all candidates at once
  - approve: candidate enters the automatic delivery queue (existing Playwright flow)
  - reject / skip: candidate is marked `skipped` with recorded reason
- In `delivery_mode=auto`, the REVIEW state is a pass-through with no UI interruption
### Jobs / Resumes / Submissions / Policy / System Settings

- Jobs manages job profiles and job leads
- Resumes acts as the personal asset hub for personal profile data, uploaded resumes, and generated resumes
- Submissions tracks delivery outcomes, screenshots, retries, and failure detail
- Policy owns gate policy and exclusions
- System Settings owns channels, model configuration, credential status, and connectivity checks

## 8. Shared UI Requirements

The following are mandatory implementation requirements for all pages:

- Loading state
- Empty state
- Error state
- Shared design tokens from the final design spec
- Reusable components for repeated patterns such as tables, form fields, modals, overlays, and status chips

## 9. Sidecar Lifecycle Requirements

- Launch sidecar during app bootstrap
- Surface startup failure in the UI immediately
- Monitor heartbeat continuously
- Mark the app offline when heartbeat or process health fails
- Support controlled shutdown from the desktop shell
- Avoid silent process restarts without UI visibility

## 10. Security and Configuration Requirements

- Secrets such as model API keys must not be stored as plain visible values in UI state snapshots
- System Settings UI must mask secrets by default
- Connection tests must report success and failure explicitly
- File import flows must validate type and size before sidecar submission

## 11. Implementation Baseline

The final implementation baseline is:

- Product spec: `ui/design/DESIGN.md`
- Design asset: `ui/design/piproofforge.pen`
- Architecture doc: `AIEF/context/tech/GUI_ARCHITECTURE.md`

Any future GUI implementation, review checklist, or delivery plan must align with these three artifacts.

## 12. Configuration Boundary (A10a)

GUI configuration ownership is fixed and must not regress to a single settings page.

- Policy page owns gate policy and exclusion list behavior:
  - `delivery_mode` (`auto` or `manual`)
  - `batch_review` (effective only when `delivery_mode=manual`)
  - `excluded_companies`
  - `excluded_legal_entities`
- System Settings page owns runtime/system capabilities:
  - channels and channel fallback configuration
  - LLM provider/model/base_url and credential status
  - connectivity and health checks

The sidecar bridge may keep a merged settings payload for compatibility, but frontend IA must remain split between Policy and System Settings.
