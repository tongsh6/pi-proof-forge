"""事实可用性闸门：判断一条事实能否作为候选人正文呈现。

背景：证据卡的 `actions`/`results` 是从技术文档抽取的，其中混有代码标识符、
接口文档碎片、表格残片与内部自指描述。它们事实为真，但不适合写进简历。
本模块只做"是否适合呈现"的判定，不否定事实本身的真实性；被拒绝的事实
仍留在证据卡与 trace 中，只是不进入正文。

判定必须可解释：每个拒绝都返回稳定原因，便于统计与回溯。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 内部自指：证据卡/文档整理痕迹，不属于候选人经历叙述。
_STRONG_META_RE = re.compile(
    r"此卡|本卡|该卡|证据卡|卡片|本次盘点|文档整理|工作台已按|待用户确认|用户确认后"
)
_WEAK_META_RE = re.compile(r"下述|如上|见下文|如下|本文")
# 代码标识符：连续大写下划线（表名/存储过程/常量）或驼峰方法名。
_CODE_IDENT_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+){2,}")
_METHOD_IDENT_RE = re.compile(r"\b[a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]*\(\)")
# 表格/管道残片。
_TABLE_RE = re.compile(r"\s\|\s")
# 接口路径/URL：候选人正文不展示实现地址（多段路径才判定，避免误伤 HTTP/JSON）。
_URL_PATH_RE = re.compile(r"https?://|/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_{}.-]+")
# 以数字开头的规则片段（"3-500人"、"40-49 占人数30%以下"）。
_NUMERIC_LEAD_RE = re.compile(r"^\s*\d[\d\s.,%~\-–]*")
# 否定/省略片段（"无需改造"、"不需要改造"）。
_NEGATIVE_RE = re.compile(r"无需改造|不需要改造|无需|不需要|不涉及|保留原")
# 工作日志痕迹：番茄钟/工时/日报/周报/初步完成——不是简历成果。
_WORKLOG_RE = re.compile(r"番茄钟|工时|打卡|日报|周报|初步完成|待验证|进行中|尚未")
# SQL / 存储实现细节：属于技术方案内部，不是简历成果。
# 业务规则（"不能超过/不得超过/必须满足"）是约束条件，不是成果。
_RULE_FRAGMENT_RE = re.compile(r"不能超过|不得超过|不允许|必须满足|需满足|须满足|校验规则[:：]")
# 参数级改动（增加某字段/参数/接口）是提交说明，不是项目成果或职责。
_PARAM_CHANGE_RE = re.compile(
    "(?:增加|新增|去掉|移除|修改)[\u201c\u201d\"'][^\u201c\u201d\"'\n]{1,24}"
    "[\u201c\u201d\"'][^\n]{0,6}(?:字段|参数|列|接口)|"
    "(?:字段|参数|配置项)[:：]\\s*\\S"
)
_SQL_DETAIL_RE = re.compile(
    r"JSON_CONTAINS|COLLSCAN|TEXT 列|[A-Z]{3,}_[A-Z]{2,}|SELECT\s|JOIN\s|EXPLAIN"
)
_VERB_RE = re.compile(
    r"负责|设计|实现|主导|参与|推动|搭建|改造|优化|治理|交付|上线|建设|重构|迁移|引入|建立|完成|支撑|维护|"
    r"降低|减少|提升|缩短|覆盖|支撑了"
)
_RESULT_RE = re.compile(r"降至|提升至|从.+到|→|缩短|减少|增长|下降|覆盖|不超过|低于|高于|达到")


@dataclass(frozen=True)
class QualityVerdict:
    presentable: bool
    reason: str = ""


def _count_identifiers(text: str) -> int:
    return len(_CODE_IDENT_RE.findall(text)) + len(_METHOD_IDENT_RE.findall(text))


def judge_fact_text(text: str, *, field: str = "actions", strict: bool = True) -> QualityVerdict:
    """按字段语义判定可否呈现。

    `strict=False` 用于已确认职业档案事实：用户确认过的职责即使很短也应保留，
    只拦截内部自指与代码标识符；证据卡（模型/文档抽取）走严格模式。
    """
    value = " ".join(str(text or "").split())
    if not value:
        return QualityVerdict(False, "empty")
    structural = field in {"title", "stack", "time_range", "role_scope", "tags"}
    if structural:
        return QualityVerdict(True)

    if strict and len(value) < 10:
        return QualityVerdict(False, "too_short")

    if _STRONG_META_RE.search(value):
        return QualityVerdict(False, "internal_meta")
    if _WEAK_META_RE.search(value) and len(value) < 40:
        return QualityVerdict(False, "internal_meta")

    identifiers = _count_identifiers(value)
    if identifiers >= 1 and (len(value) < 60 or identifiers >= 2):
        return QualityVerdict(False, "code_identifier")

    if _TABLE_RE.search(value):
        return QualityVerdict(False, "table_fragment")

    if _URL_PATH_RE.search(value):
        return QualityVerdict(False, "url_path")

    if strict and (
        _NUMERIC_LEAD_RE.match(value)
        and not _VERB_RE.search(value)
        and not _RESULT_RE.search(value)
    ):
        return QualityVerdict(False, "numeric_fragment")

    if strict and _NEGATIVE_RE.search(value):
        return QualityVerdict(False, "negative_fragment")

    if strict and _WORKLOG_RE.search(value):
        return QualityVerdict(False, "worklog_trace")

    if strict and _SQL_DETAIL_RE.search(value):
        return QualityVerdict(False, "sql_detail")

    if strict and _RULE_FRAGMENT_RE.search(value):
        return QualityVerdict(False, "business_rule_fragment")

    if strict and _PARAM_CHANGE_RE.search(value):
        return QualityVerdict(False, "param_change")

    if not re.search(r"[\u4e00-\u9fff]", value) and not re.search(r"[A-Za-z]{4,}", value):
        return QualityVerdict(False, "no_readable_text")

    return QualityVerdict(True)


def presentable(text: str, *, field: str = "actions") -> bool:
    return judge_fact_text(text, field=field).presentable
