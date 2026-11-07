"""agent handler 门面：持有 Quick Run 路径/运行态，re-export 各域实现。

拆分结构（原单文件约 2225 行）：
- handlers/quick_run.py            Quick Run 启动/执行/取消/生命周期
- handlers/quick_run_progress.py   由 run_log 事件推导四阶段进度
- handlers/quick_run_results.py    材料/证据选择、路径解析、结果详情与 PDF 导出
- handlers/agent_run.py            Agent Run 10 状态机执行、dry-run、引导批次
- handlers/agent_delivery.py       投递前置：岗位线索、默认简历准备、回执复核
- handlers/agent_review.py         审批队列、待审查询、提交审批与投递同步
- handlers/_shared/agent_runtime.py 时间/ID 校验/路径解析等无状态工具

路径常量、Popen 与 Quick Run 运行态保留在本门面模块：它们会被测试 patch，
子模块通过各自的 ``_facade()`` 在运行时读取，保证拆分后 patch 语义不变。
server.py 与既有 import 保持不变。
"""

from __future__ import annotations

import threading
from pathlib import Path
from subprocess import Popen
from typing import Any

from tools.infra.export.pdf_exporter import markdown_to_pdf, pdf_page_count
from tools.sidecar.handlers._shared.agent_runtime import _find_project_root

_PROJECT_ROOT = _find_project_root(Path(__file__).resolve())
_AGENT_RUN_DIR = _PROJECT_ROOT / "outputs" / "agent_runs"
_QUICK_RUN_DIR = _PROJECT_ROOT / "outputs" / "quick_runs"
_REVIEW_QUEUE_DIR = _PROJECT_ROOT / "outputs" / "review_queue"

# Quick Run 的四个真实阶段与 pipeline 步骤名的映射（skip 提取时第一步即 evidence-selection）。
_QUICK_RUN_STAGES: tuple[str, ...] = ("extract", "match", "generate", "evaluate")
_QUICK_RUN_STEP_STAGES: dict[str, str] = {
    "evidence-selection": "extract",
    "evidence-extraction-llm": "extract",
    "evidence-extraction-rule": "extract",
    "matching-scoring": "match",
    "generation": "generate",
    "evaluation": "evaluate",
}
_QUICK_RUN_TERMINAL_STATUSES = frozenset(
    {"DONE", "SKIPPED", "FAILED", "TIMEOUT", "stopped"}
)
_QUICK_RUN_ENVELOPE_KEYS = frozenset({"run", "progress"})
# 后台线程轮询 run_log.json / 进程状态的间隔；测试可 monkeypatch 缩短。
_QUICK_RUN_POLL_INTERVAL_SECONDS = 0.5
# terminate 之后等待进程退出的宽限期，超时再 kill。
_QUICK_RUN_TERMINATE_GRACE_SECONDS = 2.0
# 读/写 outputs/quick_runs/<run_id>.json 与活跃运行状态都由这把锁保护（handler 主循环与后台线程并发）。
_QUICK_RUN_LOCK = threading.RLock()
_QUICK_RUN_ACTIVE: dict[str, Any] | None = None
_QUICK_RUN_LAST_THREAD: threading.Thread | None = None

from tools.sidecar.handlers._shared.agent_runtime import (
    _coerce_positive_int,
    _elapsed_seconds_between,
    _parse_iso_datetime,
    _utcnow_iso,
    _validate_run_resource_id,
)
from tools.sidecar.handlers.agent_delivery import (
    _domain_evidence_cards,
    _job_lead_candidates,
    _read_domain_job_profile,
    handle_prepare_liepin_default,
    handle_recheck_receipt,
)
from tools.sidecar.handlers.agent_review import (
    _delivery_confirmation,
    _delivery_summary,
    _ensure_queue_dir,
    _get_queue_file,
    _load_queue,
    _save_queue,
    _sync_review_run,
    handle_create_review_candidates,
    handle_get_pending_review,
    handle_submit_review,
)
from tools.sidecar.handlers.agent_run import (
    _build_agent_run_id,
    _ensure_agent_run_dir,
    _event_to_payload,
    _execute_guided_batch_run,
    _execute_local_dry_run,
    _get_agent_run_file,
    _load_agent_run,
    _save_agent_run,
    handle_agent_get,
    handle_agent_start,
    handle_agent_stop,
)
from tools.sidecar.handlers.quick_run import (
    _build_quick_run_id,
    _ensure_quick_run_dir,
    _execute_quick_run,
    _finalize_quick_run,
    _get_quick_run_file,
    _join_quick_run_thread,
    _load_quick_run,
    _read_temp_file_text,
    _run_quick_run_worker,
    _save_quick_run,
    _terminate_quick_run_process,
    _wait_for_process_exit,
    handle_quick_cancel,
    handle_quick_check_direction,
    handle_quick_get,
    handle_quick_start,
)
from tools.sidecar.handlers.quick_run_progress import (
    _pipeline_run_log_path,
    _quick_run_envelope,
    _read_pipeline_run_events,
    _refresh_quick_run_progress,
    _stage_progress_from_events,
)
from tools.sidecar.handlers.quick_run_results import (
    _direction_precheck_cache_dir,
    _evidence_card_dir,
    _export_resume_pdf,
    _is_saved_eligible_evidence,
    _load_eligible_evidence_card,
    _load_evidence_trace,
    _load_evidence_traces,
    _load_job_profile_context,
    _load_quick_run_summary,
    _parse_matching_evidence_ids,
    _parse_matching_lists,
    _parse_matching_scores,
    _persisted_llm_runtime_context,
    _quick_run_material_sources,
    _quick_run_paths,
    _quick_run_positioning,
    _quick_run_result_details,
    _resolve_project_path,
    _select_quick_run_material,
    _selected_evidence_cards,
    _stage_selected_evidence,
)
