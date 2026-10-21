"""可复用的正文质量文本判定（评估器与生成器共用）。"""
from __future__ import annotations

import re

# 数字必须带业务单位才算可验证量化；技术版本、年份、纯序号不算。
QUANT_METRIC_RE = re.compile(
    r"\d[\d,.]*\+?\s*(?:%|ms\b|s\b|毫秒|秒|分钟|小时|万?条|次|个|人|项|QPS\b|TPS\b|GB\b|TB\b|倍)",
    re.I,
)


def compact(text: str) -> str:
    return re.sub(r"[\s*_`，,。；;：:·、|（）()\[\]【】“”\"']", "", str(text or ""))


def has_quant_metric(text: str) -> bool:
    return bool(QUANT_METRIC_RE.search(str(text or "")))
