"""批量证据提炼：把材料目录按项目聚类，产出可审核的证据卡草稿。

单文档提炼入口依赖人工逐篇选取，材料数量增长后容易留下覆盖缺口。
批量提炼复用相同来源约束，按项目组织待审核草稿。

本模块提供批量路线：
1. `collect_documents`：从材料文件切出文档边界（复用 material_documents）；
2. `cluster_by_project`：按目录首段把文档聚成项目簇；
3. `select_representative`：按"方案/需求/验收/复盘优先"选代表文档，受字符预算约束；
4. `build_scale_card`：规则模式产出"项目规模卡"（文档构成 + 规模事实，全部来自
   目录统计，不编造业务内容），用于让用户看到"有哪些项目待提炼"；
5. `build_extraction_prompt` / `parse_extraction_response`：LLM 模式的结构化契约。

事实边界：规则卡只写可复核的目录统计；LLM 卡必须逐字引用原文，
落盘前由 `evidence_sources.read_source_documents` 与 excerpt 校验兜底。
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tools.infra.material_documents import split_material_documents

# 代表文档优先级：先看方案/需求，再看验收/复盘，最后补发布记录。
_PRIORITY_TERMS: tuple[tuple[str, ...], ...] = (
    ("方案", "设计", "需求", "调研", "架构"),
    ("验收", "测试", "复盘", "问题", "缺陷", "故障", "原因分析", "解决方案"),
    ("发布", "上线", "部署", "清单", "说明", "总结", "周报"),
)
_DOC_TYPE_RE = re.compile(r"/([^/]+)$")
MAX_DOC_CHARS = 24000


@dataclass(frozen=True)
class CollectedDocument:
    document_id: str
    sha256: str
    label: str
    source_name: str
    text: str


@dataclass(frozen=True)
class ProjectCluster:
    key: str
    documents: tuple[CollectedDocument, ...]

    @property
    def document_count(self) -> int:
        return len(self.documents)


def collect_documents(material_path: Path) -> list[CollectedDocument]:
    """按材料文件的 `# Source:` 边界切文档；返回带稳定 document_id/sha256 的列表。"""
    text = material_path.read_text(encoding="utf-8")
    collected: list[CollectedDocument] = []
    for doc in split_material_documents(text, material_path.name):
        collected.append(
            CollectedDocument(
                document_id=doc["document_id"],
                sha256=doc["sha256"],
                label=doc["label"],
                source_name=str(doc.get("source_name") or doc["label"]),
                text=doc["text"],
            )
        )
    return collected


# 通用容器段：这些目录本身不表达项目，跳过它们再取语义段。
_GENERIC_SEGMENTS = frozenset({"项目目录", "项目", "文档", "工作汇总", "资料", "归档"})


def _project_key(label: str) -> str:
    parts = [part for part in label.replace("\\", "/").split("/") if part]
    if not parts:
        return "(root)"
    if len(parts) == 1:
        return parts[0].rsplit(".", 1)[0]
    if parts[0] in _GENERIC_SEGMENTS:
        rest = parts[1:-1]
        if len(rest) >= 2:
            return "/".join(rest[:2])
        return rest[0] if rest else parts[0]
    return parts[0]


def cluster_by_project(
    documents: Sequence[CollectedDocument],
    *,
    min_documents: int = 1,
) -> list[ProjectCluster]:
    """按目录首段聚类；文档数不足的簇不进入批量提炼（避免碎片卡）。"""
    buckets: dict[str, list[CollectedDocument]] = {}
    for doc in documents:
        buckets.setdefault(_project_key(doc.label), []).append(doc)
    clusters = [
        ProjectCluster(key=key, documents=tuple(docs))
        for key, docs in buckets.items()
        if len(docs) >= min_documents
    ]
    clusters.sort(key=lambda cluster: (-cluster.document_count, cluster.key))
    return clusters


_FIX_TERMS = ("修复", "bug", "fix", "hotfix", "临时", "hot 修复")


def exclude_clusters(
    clusters: Sequence[ProjectCluster], names: Sequence[str]
) -> list[ProjectCluster]:
    """按簇名排除噪音簇（如附件目录 assets），保留其余项目。"""
    blocked = {str(name).strip() for name in names if str(name).strip()}
    return [cluster for cluster in clusters if cluster.key not in blocked]


def _priority(label: str) -> int:
    """项目全景文档优先，具体缺陷修复方案降权（后者只能代表一个局部改动）。"""
    name = label.rsplit("/", 1)[-1].casefold()
    if any(term in name for term in _FIX_TERMS):
        return len(_PRIORITY_TERMS)
    if name.startswith(("00-", "01-", "02-", "03-")) and any(
        term in name for term in ("需求", "方案", "设计", "技术方案")
    ):
        return 0
    for rank, terms in enumerate(_PRIORITY_TERMS):
        if any(term in label for term in terms):
            return rank
    return len(_PRIORITY_TERMS)


_NOISE_SEGMENTS = ("bugs", "问题", "_archive", "releases", "_overview", "checklists", "templates")


def _depth(label: str) -> int:
    return label.replace("\\", "/").count("/")


def _noise(label: str) -> int:
    parts = label.casefold()
    return 1 if any(segment in parts for segment in _NOISE_SEGMENTS) else 0


def select_representative(
    cluster: ProjectCluster,
    *,
    max_chars: int = MAX_DOC_CHARS,
    max_docs: int = 5,
) -> list[CollectedDocument]:
    """选代表文档：文档类型优先级 → 非问题/归档目录 → 目录层级浅 → 信息密度。"""
    ordered = sorted(
        cluster.documents,
        key=lambda doc: (
            _priority(doc.label),
            _noise(doc.label),
            _depth(doc.label),
            -min(len(doc.text), 8000),
            doc.label,
        ),
    )
    selected: list[CollectedDocument] = []
    used = 0
    for doc in ordered:
        if len(selected) >= max_docs:
            break
        budget = min(len(doc.text), max_chars - used)
        if budget <= 0:
            break
        selected.append(doc)
        used += min(len(doc.text), max_chars - used)
    return selected


_DATE_PATTERNS = (
    re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})"),
    re.compile(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})"),
)
_FRONTMATTER_DATE_RE = re.compile(r"^(?:created|updated|date):\s*'?(20\d{2})-(\d{2})-(\d{2})", re.MULTILINE)


_MIN_YEAR = 2010


def _dates_in(text: str, *, max_year: int) -> list[tuple[int, int]]:
    """只接受职业期内、且不晚于当前的年月；避免金额/编号里的 8 位数字误判。"""
    found: list[tuple[int, int]] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span()
            if start > 0 and text[start - 1].isdigit():
                continue
            if end < len(text) and text[end].isdigit():
                continue
            year, month = int(match.group(1)), int(match.group(2))
            if _MIN_YEAR <= year <= max_year and 1 <= month <= 12:
                found.append((year, month))
    return found


def infer_period(documents: Sequence[CollectedDocument]) -> str:
    """从文档文件名与 frontmatter 的真实日期推断项目周期（年月精度）。

    只取文档里实际出现的日期，不推测项目起止；推断结果必须在卡上标注待确认。
    """
    import datetime as _datetime

    today = _datetime.date.today()
    max_year = today.year
    stamps: list[tuple[int, int]] = []
    for doc in documents:
        stamps.extend(_dates_in(doc.label, max_year=max_year))
        stamps.extend(_dates_in(doc.text[:2000], max_year=max_year))
        for match in _FRONTMATTER_DATE_RE.finditer(doc.text[:4000]):
            year, month = int(match.group(1)), int(match.group(2))
            if _MIN_YEAR <= year <= max_year and 1 <= month <= 12:
                stamps.append((year, month))
    stamps = [item for item in stamps if item <= (today.year, today.month)]
    if not stamps:
        return ""
    stamps.sort()
    first, last = stamps[0], stamps[-1]
    if first == last:
        return f"{first[0]:04d}-{first[1]:02d}"
    return f"{first[0]:04d}-{first[1]:02d} ~ {last[0]:04d}-{last[1]:02d}"


def _doc_type_counts(documents: Sequence[CollectedDocument]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for doc in documents:
        match = _DOC_TYPE_RE.search(doc.label)
        name = match.group(1) if match else doc.label
        stem = name.rsplit(".", 1)[0]
        key = stem.rsplit("/", 1)[-1] or stem
        general = "文档"
        for candidate in ("需求", "方案", "设计", "验收", "发布", "问题", "复盘", "索引", "清单", "规范", "说明", "总结"):
            if candidate in key:
                general = candidate if candidate != "设计" else "方案"
                break
        counts[general] = counts.get(general, 0) + 1
    return counts


def _detect_stack(documents: Sequence[CollectedDocument]) -> list[str]:
    terms = (
        "Java", "Spring Boot", "MyBatis", "MySQL", "Redis", "MongoDB", "RabbitMQ",
        "Kafka", "微信小程序", "微信支付", "收钱吧", "顺丰", "CRM", "Nacos",
        "Docker", "XXL-JOB", "Angular", "Vue", "PowerPoint", "Nginx",
    )
    blob = "\n".join(doc.text for doc in documents).casefold()
    return [term for term in terms if term.casefold() in blob]


def build_scale_card(
    cluster: ProjectCluster,
    selected: Sequence[CollectedDocument],
    *,
    material_id: str,
    card_id: str,
    raw_source: str,
    now: str,
) -> dict:
    """规则模式卡：只写目录统计与文档构成，不推测业务内容。

    这类卡的作用是"让用户看到有哪些项目可以提炼"，而不是直接作为简历素材；
    因此 `candidate_pool_eligible` 为 false、`missing_items` 明确列出待补项。
    """
    counts = _doc_type_counts(cluster.documents)
    total = cluster.document_count
    inferred_period = infer_period(cluster.documents)
    parts = "、".join(f"{name} {count} 篇" for name, count in sorted(counts.items(), key=lambda item: -item[1]))
    actions = [
        f"项目目录共 {total} 篇文档，其中 {parts}",
        "代表文档：" + "；".join(doc.label for doc in selected),
    ]
    results = [f"{total} 篇业务文档沉淀（方案/需求/验收/发布记录可追溯）"]
    context = f"{cluster.key} 项目档案，所属材料 {material_id}，共 {total} 篇文档。"
    references = [
        {
            "document_id": doc.document_id,
            "sha256": doc.sha256,
            "label": doc.label,
            "material_id": material_id,
        }
        for doc in selected
    ]
    return {
        "id": card_id,
        "title": f"{cluster.key}（工程档案规模）",
        "time_range": inferred_period,
        "context": context,
        "role_scope": "",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "actions": actions,
        "results": results,
        "stack": _detect_stack(selected),
        "artifacts": [material_id],
        "tags": ["批量规模卡", "待提炼", cluster.key],
        "raw_source": raw_source,
        "source_material_ids": [material_id],
        "source_documents_json": json.dumps(references, ensure_ascii=False),
        "review_decision": "pending",
        "candidate_pool_eligible": "false",
        "missing_items": (
            "本人职责、任职时间、业务成果与量化指标待补；规模卡不能直接作为简历素材。"
            + ("项目周期由文档日期推断，需用户确认。" if inferred_period else "")
        ),
        "batch_scale_card": "true",
    }


_PERIOD_MONTH_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})")
_PLANNED_RE = re.compile(r"预计|计划中|计划为|^计划|将会|预期|目标为|拟定|有望")


def normalize_period(value: str) -> str:
    """把任意精度的时间表达统一到年月；无法识别时返回空串（不猜）。"""
    text = str(value or "").strip()
    if not text:
        return ""
    parts = [part for part in re.split(r"\s*[~至到]\s*", text) if part.strip()]
    stamps: list[str] = []
    for part in parts:
        match = _PERIOD_MONTH_RE.search(part)
        if not match:
            return ""
        month = int(match.group(2))
        if not 1 <= month <= 12:
            return ""
        stamps.append(f"{int(match.group(1)):04d}-{month:02d}")
    if not stamps:
        return ""
    if len(stamps) == 1:
        return stamps[0]
    return f"{stamps[0]} ~ {stamps[-1]}"


def split_planned_results(results: Sequence[str]) -> tuple[list[str], list[str]]:
    """把"预计/计划"类结果单列：它们还没被验证，不能当成果写进简历。"""
    verified: list[str] = []
    planned: list[str] = []
    for value in results:
        text = str(value or "").strip()
        if not text:
            continue
        (planned if _PLANNED_RE.search(text) else verified).append(text)
    return verified, planned


_ACTIVITY_RE = re.compile(r"培训|面试|分享|入职|学习|考试|题库|招聘|述职|例会|周会|团建")
_OPERATION_RE = re.compile(r"运维|排查|故障|问题处理|值班|交接")
_PROJECT_STRONG_RE = re.compile(r"架构|设计|改造|建设|重构|集成|开发")


def pool_approval_reason(card: dict, *, source_verifiable: bool = True) -> str:
    """入池硬门槛的唯一判定：返回拒绝原因，空串表示通过。

    依据宪法第 1 条：results 或 artifacts 缺失的卡不进入候选池；
    另需 title 与可校验的来源绑定。
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


def classify_card_category(title: str, actions: Sequence[str] = ()) -> str:
    """把卡分成项目/运维/活动三类：活动类不得作为简历项目经历。"""
    blob = " ".join([str(title or ""), *[str(value) for value in actions]])
    if _ACTIVITY_RE.search(str(title) or ""):
        return "activity"
    if _OPERATION_RE.search(str(title) or "") and not _PROJECT_STRONG_RE.search(
        str(title) or ""
    ):
        return "operation"
    return "project"


def project_outline(cluster: ProjectCluster, *, limit: int = 30) -> str:
    """项目目录结构摘要：让模型看到项目全貌，而不是只看到 5 篇代表文档。"""
    containers = {"features", "experiences", "bugs", "checklists", "_archive", "releases"}
    counts: dict[str, int] = {}
    for doc in cluster.documents:
        parts = [part for part in doc.label.split("/") if part]
        if (
            len(parts) >= 3
            and parts[1].casefold() in containers
            and "." not in parts[2]
        ):
            key = f"{parts[1]}/{parts[2]}"
        elif len(parts) >= 2:
            key = parts[1]
        else:
            key = doc.label
        counts[key] = counts.get(key, 0) + 1
    rows = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return "\n".join(f"- {key}（{count} 篇）" for key, count in rows)


def build_extraction_prompt(cluster: ProjectCluster, selected: Sequence[CollectedDocument]) -> str:
    """LLM 模式：要求输出可校验的 JSON 数组，事实必须逐字引用原文。"""
    documents = "\n\n".join(
        f"### 文档：{doc.label}\n{doc.text[: max(0, MAX_DOC_CHARS // max(1, len(selected)))]}"
        for doc in selected
    )
    outline = project_outline(cluster)
    return (
        "你是证据提炼器。下面给出一个工作项目的目录结构与若干代表文档，请提炼 1-2 张证据卡。\n"
        "硬性要求：\n"
        "1. actions 与 results 必须逐字引用原文句子（可以截取片段），不得改写、不得补充原文没有的信息；\n"
        "2. 没有原文依据的数字、指标、职责一律不写；\n"
        "3. role_scope 必须从原文的第一人称职责表述中提取（如「我负责」「本人主导」\n"
        "   「由我设计」「负责…的是我」），原文没有这类表述时留空，不得用技术相似度推断；\n"
        "4. 先概括该项目整体做了什么（项目级），再把代表文档里的关键方案作为支撑细节；\n"
        "   不要把整张卡写成某一个具体功能/缺陷的修复记录；\n"
        "5. role_scope 与 actions 的责任强度必须一致：原文写「参与」就不能写成「主导」；\n"
        "6. 只输出 JSON 数组，不要额外解释。\n"
        "输出结构：[{\"title\": str, \"context\": str, \"role_scope\": str, "
        "\"actions\": [str], \"results\": [str], \"stack\": [str], \"time_range\": str}]\n\n"
        f"项目：{cluster.key}（共 {cluster.document_count} 篇文档）\n"
        f"项目目录结构：\n{outline}\n\n"
        f"代表文档：\n{documents}"
    )


def parse_extraction_response(raw: str) -> list[dict]:
    """解析并做结构校验；非法结构直接拒绝，不猜。"""
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("batch_extraction_invalid_json") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise ValueError("batch_extraction_empty")
    cards: list[dict] = []
    for item in data:
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            raise ValueError("batch_extraction_missing_title")
        actions = [str(value).strip() for value in item.get("actions") or [] if str(value).strip()]
        results = [str(value).strip() for value in item.get("results") or [] if str(value).strip()]
        if not actions and not results:
            raise ValueError("batch_extraction_missing_facts")
        cards.append(
            {
                "title": str(item["title"]).strip(),
                "context": str(item.get("context") or "").strip(),
                "role_scope": str(item.get("role_scope") or "").strip(),
                "actions": actions,
                "results": results,
                "stack": [str(value).strip() for value in item.get("stack") or [] if str(value).strip()],
                "time_range": str(item.get("time_range") or "").strip(),
            }
        )
    return cards


def verify_card_against_sources(card: dict, source_text: str) -> list[str]:
    """逐条核对事实是否能在源文本中定位；返回不能定位的条目。"""
    missing: list[str] = []
    for value in [*card.get("actions", []), *card.get("results", [])]:
        if str(value) not in source_text:
            missing.append(str(value))
    return missing
