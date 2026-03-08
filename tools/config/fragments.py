"""配置切片定义，与 design 一致；禁止上帝对象 Config。"""

from __future__ import annotations

from dataclasses import dataclass


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
