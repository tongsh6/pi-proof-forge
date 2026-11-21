"""四层简历质量评估：合格（Eligible）→ 对位（Fit）→ 优质（Strong）→ 突出（Distinct）。

实现按层拆分在 ``tools/engines/evaluation/tiers/``：
- common：配置、正文解析、bullet/条目/追溯检查等公共工具
- eligible / fit / strong / distinct：四层规则判项
- report：四层报告组装、投递建议、auto_pass 重算与 PDF 校验回填

本模块保留原公开与内部符号的 re-export，既有 import 与测试无需修改。
"""
from __future__ import annotations

from .tiers.common import (
    DEFAULT_THRESHOLDS,
    FALLBACK_FILLER_TERMS,
    PHASE_A_LLM_PENDING,
    ROOT,
    QualityConfig,
    _CONTACT_RE,
    _DEGREE_RANK,
    _ENTRY_SECTIONS,
    _FLAT_KEYS,
    _INTERNAL_TRACE_RE,
    _STRONG_ROLE_RE,
)
from .tiers.common import (
    split_first_screen,
    extract_bullets,
    _split_first_screen,
    _normalize,
    _compact,
    _ym,
    _now_ym,
    _period_bounds,
    _title_period,
    _bullet_rows,
    _entries,
    inspect_bullet_trace,
    _failure,
    _short,
    _report_metrics,
    _unique,
    _pdf_check_pending,
    _advice_recomputable,
    load_quality_config)
from .tiers.distinct import _candidate_highlights, evaluate_distinct
from .tiers.eligible import (
    _hard_condition_failures,
    _provenance,
    _provenance_level,
    _structure_failures,
    evaluate_eligible,
)
from .tiers.fit import (
    _fit_gap_kind,
    _fit_gap_reason,
    _fit_matrix,
    _judge_candidates,
    _pending_rules,
    evaluate_fit,
)
from .tiers.report import (
    _delivery_advice,
    _tier_gap_tasks,
    apply_pdf_check,
    build_quality_report,
    recompute_auto_pass,
)
from .tiers.report import (
    _FACT_RULES,
    _GAP_KIND_LABELS,
    _RECOMMENDATION_LABELS,
    _RECOMMENDATION_SUMMARIES,
)
from .tiers.strong import _has_verifiable_quant, evaluate_strong
