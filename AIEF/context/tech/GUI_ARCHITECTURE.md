# PiProofForge GUI Architecture & Integration Plan

## 1. Overview
This document outlines the architecture and integration plan to connect the existing HTML/JS GUI prototype (`ui/prototype/index.html`) with the Python backend pipeline (`tools/run_pipeline.py`). The goal is to provide a seamless, real-time experience for users to configure job profiles, upload raw materials, and visualize the "reasoning trace" and final generated resumes.

## 2. Tech Stack
- **Frontend**: Vanilla HTML/JS/CSS (Existing prototype).
- **Backend**: **FastAPI** (Python). Chosen for its lightweight nature, native async support, and ease of implementing Server-Sent Events (SSE) for log streaming.
- **Communication**: REST API for standard requests, **Server-Sent Events (SSE)** for streaming reasoning traces and pipeline logs.

## 3. Data Flow
1. **Configuration & Upload**: User selects raw files and configures the job profile in the GUI.
2. **Submission**: Frontend sends a `POST` request to `/api/run_pipeline` with files (multipart/form-data) and configuration parameters.
3. **Initialization**: FastAPI backend receives the request, saves uploaded files to a temporary workspace, and generates a `job_profile.yaml`.
4. **Execution & Streaming**: Backend spawns `tools/run_pipeline.py` as an async subprocess. It reads the subprocess `stdout`/`stderr` line by line and yields them as SSE messages to the frontend.
5. **Real-time UI Update**: Frontend receives SSE messages, parses them, and appends them to the "Reasoning Trace" panel.
6. **Result Retrieval**: Once the subprocess completes, the backend reads the generated output files (Match Report, Resumes, Scorecard) and sends them as the final SSE event (or frontend makes a separate fetch). Frontend renders the results in the preview tabs.

## 4. API Schema

### 4.1 `POST /api/run_pipeline`
**Purpose**: Start the pipeline execution and stream logs/results.
**Content-Type**: `multipart/form-data` (to handle file uploads and JSON config).

**Request Payload**:
- `files`: List of uploaded files (raw materials).
- `profile`: JSON string containing the job profile (target_role, must_have, keywords, business_domain, tone).
- `config`: JSON string containing run configuration (`run_id`, `use_llm`, `require_llm`, `strict_gate`).

**Response**: `text/event-stream` (Server-Sent Events)
**Event Types**:
- `event: log`: Standard pipeline log or reasoning trace.
  - `data: {"timestamp": "...", "level": "info|action|thought|success|error", "message": "..."}`
- `event: step`: Pipeline step transition.
  - `data: {"step": "extract|match|gen|eval", "status": "running|done"}`
- `event: result`: Final execution results.
  - `data: {"match_report": "...", "resume_a": "...", "resume_b": "...", "scorecard": "..."}`
- `event: done`: Stream completion signal.

### 4.2 `GET /api/profiles`
**Purpose**: Fetch available job profile presets.
**Response**: `application/json`
```json
{
  "presets": [
    {
      "id": "jp-2026-001",
      "name": "Backend Tech Lead",
      "target_role": "Backend Tech Lead",
      "must_have": ["高并发系统设计", "稳定性治理", "跨团队协作"],
      "keywords": ["Java", "Redis", "Kafka", "SLA", "SLO"],
      "business_domain": "电商",
      "tone": "A"
    }
  ]
}
```

## 5. Integration Steps (Action Plan)
1. **Setup FastAPI Project**: Create `api/main.py` and configure CORS for the frontend.
2. **Implement `/api/profiles`**: Read existing YAML profiles from `job_profiles/` and return them as JSON.
3. **Implement `/api/run_pipeline`**:
   - Handle `multipart/form-data` parsing.
   - Create a temporary directory for the run (`/tmp/piproof_run_<id>`).
   - Save uploaded files to the temp directory.
   - Generate `job_profile.yaml` from the request payload.
   - Use `asyncio.create_subprocess_exec` to run `python3 tools/run_pipeline.py`.
4. **Implement SSE Streaming**:
   - Read `stdout` and `stderr` from the subprocess asynchronously.
   - Parse log lines to categorize them (system, action, thought, success, error) based on keywords or prefixes.
   - Yield formatted SSE strings.
5. **Frontend Adaptation**:
   - Replace the mock `runPipeline` function in `index.html` with a `fetch` call to `/api/run_pipeline`.
   - Use a custom SSE reader (handling multipart fetch streams) or `EventSource` (if GET, but we need POST for files, so use `fetch` with `ReadableStream` reader) to process incoming logs and update the UI dynamically.
   - Fetch presets from `/api/profiles` on page load.
