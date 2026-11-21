"""把模型摘录的原文片段定位回事实编号。

## 为什么需要它（流程理顺，而不是容错）

语义评审原来要求模型输出 `fact_id`（如 `ec_0f6287d2:actions:1`）。这个字符串
对模型是纯噪音：它懂语义，但要逐字符复制一个带冒号的标识，实测 iq3_s 整批
输出不存在的事实编号，导致整批评审降级。

职责本应这样分配：

- **模型**：理解语义、判断相关性、摘录支撑结论的原文片段（它擅长的自然语言）；
- **程序**：把摘录片段精确映射回事实编号（它擅长的精确匹配）。

`locate_fact_by_quote` 就是"程序的这一半"。定位失败不是异常，只是一个可解释的
事实：该摘录在当前事实集合中不存在，调用方据此把该条结论判为不可核实，而不是
让整批评审失败。

## 匹配策略（由严到宽，每一步都可解释）

1. 精确子串：摘录是原文的一部分（模型照抄或截断）；
2. 归一化子串：去掉空白与常见标点后再匹配（模型改了空格/标点）；
3. 前缀/后缀包含：摘录被截断（模型输出被 max_tokens 截断）；
4. 全部不命中：返回 `None`，调用方降级该条。

只做这三步，不做模糊相似度——相似度阈值会把"看起来像"变成"就算证据"，
违反事实保真。
"""
from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[，。；：、！？,.;:!?\"'“”‘’（）()\[\]【】《》<>…·\-—–_]")
MIN_QUOTE_LENGTH = 4


def _normalize(text: str) -> str:
    value = _WHITESPACE_RE.sub("", str(text or ""))
    return _PUNCTUATION_RE.sub("", value)


def locate_fact_by_quote(quote: str, facts: dict[str, dict]) -> str | None:
    """把摘录片段定位到事实编号；无法定位时返回 None。

    只返回真正包含该片段的第一个事实编号，不做相似度近似。
    """
    raw = str(quote or "").strip()
    if len(raw) < MIN_QUOTE_LENGTH:
        return None
    normalized_quote = _normalize(raw)
    if not normalized_quote:
        return None
    # 1) 精确子串
    for fact_id, fact in facts.items():
        if raw in str(fact.get("text") or ""):
            return fact_id
    # 2) 归一化子串
    for fact_id, fact in facts.items():
        if normalized_quote in _normalize(str(fact.get("text") or "")):
            return fact_id
    # 3) 截断情形：摘录是原文的前缀或后缀
    for fact_id, fact in facts.items():
        text = _normalize(str(fact.get("text") or ""))
        if text and (text.startswith(normalized_quote) or text.endswith(normalized_quote)):
            return fact_id
    return None
