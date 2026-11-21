"""证据卡入池口径的唯一实现。

生成与匹配都必须使用同一套"可进入候选池"判定，否则会出现"生成只认已审核卡、
匹配却把样例卡也算进去"的双口径漂移。

判定规则（与 App 内入池语义一致，对旧格式保持可读）：
- 显式 `sample: true` 的卡一律排除（演示/无来源卡）；
- 有 `status` 字段时必须是 `saved_eligible`；
- 有 `candidate_pool_eligible` 字段时必须是 `true`；
- 两者都没有的历史卡/CLI 夹具保持可读，由来源校验兜底。
"""
from __future__ import annotations

from collections.abc import Mapping

# 本地演示/一次性运行产物与旧手写卡：即使没有管理字段也不得进入候选池。
# 与 .gitignore 中 `ec-demo_*`、`ec-qr_*` 的本地产物约定一致。
_DEMO_ID_PREFIXES = ("ec-demo", "ec-qr", "ec-2026-0")


def is_demo_card_id(card_id: str) -> bool:
    return str(card_id or "").startswith(_DEMO_ID_PREFIXES)


def pool_eligible_scalars(scalars: Mapping[str, object], *, card_id: str = "") -> bool:
    if is_demo_card_id(card_id):
        return False
    if str(scalars.get("sample") or "").lower() == "true":
        return False
    status = str(scalars.get("status") or "")
    if status and status != "saved_eligible":
        return False
    eligible = str(scalars.get("candidate_pool_eligible") or "")
    if eligible and eligible.lower() != "true":
        return False
    return True


def pool_approval_reason(card: dict, *, source_verifiable: bool = True) -> str:
    """只读完整性预检查，返回缺失或来源未核验原因。

    空原因不授予复审批准或实测资格；调用者仍须核对明确状态、
    现行来源及逐事实范围。
    """
    if not str(card.get("title") or "").strip():
        return "title_missing"
    if not card.get("results"):
        return "results_missing"
    if not card.get("artifacts"):
        return "artifacts_missing"
    if not source_verifiable:
        return "source_unverifiable"
    return ""
