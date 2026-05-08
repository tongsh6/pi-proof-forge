"""配置切片定义，与 design 一致；禁止上帝对象 Config。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration — design section 9.8."""
    model: str
    base_url: str
    api_key: str
    timeout: int = 120


@dataclass(frozen=True)
class PathConfig:
    """Filesystem path configuration — design section ISP."""
    evidence_dir: str = "evidence_cards"
    output_dir: str = "outputs"
    profile_dir: str = "job_profiles"
    session_dir: str = "outputs/sessions"


@dataclass(frozen=True)
class EngineSelection:
    """Engine strategy selection — design section 9.9."""
    evidence_mode: str = "rule"
    matching_mode: str = "rule"
    generation_mode: str = "template"
    evaluation_mode: str = "rule"


@dataclass(frozen=True)
class PolicyConfig:
    """策略配置：门禁、投递模式、企业例外清单。"""

    n_pass_required: int
    matching_threshold: float
    evaluation_threshold: float
    max_rounds: int
    gate_mode: str
    delivery_mode: str  # "auto" | "manual"
    batch_review: bool  # 仅 delivery_mode=manual 时生效
    excluded_companies: tuple[str, ...]
    excluded_legal_entities: tuple[str, ...]
    max_deliveries: int = 0
