"""规则式证据提炼引擎（确定性、零外部依赖）。

从原始文本中抽取 Evidence Card 字段。产品主链路的规则提炼唯一实现；
CLI 与 Agent 引擎均通过本模块调用，禁止在入口层重复实现同一套抽取规则。
"""

from __future__ import annotations

import re
from typing import TypedDict

from tools.domain.models import EvidenceCard

TECH_TOKENS = [
    "Java",
    "Go",
    "Python",
    "Redis",
    "Kafka",
    "MySQL",
    "PostgreSQL",
    "Kubernetes",
    "Prometheus",
    "Grafana",
    "Elasticsearch",
    "ClickHouse",
    "RocketMQ",
]

TAG_TOKENS = [
    "稳定性",
    "性能",
    "成本",
    "治理",
    "一致性",
    "交付",
    "架构",
]


class SectionData(TypedDict):
    context: str
    actions: list[str]
    results: list[str]
    artifacts: list[str]
    stack: list[str]


class EvidenceCardDraft(TypedDict):
    id: str
    title: str
    raw_source: str
    time_range: str
    context: str
    role_scope: str
    actions: list[str]
    results: list[str]
    stack: list[str]
    artifacts: list[str]
    tags: list[str]
    interview_hooks: list[str]


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_time_range(text: str) -> str:
    pattern = re.compile(r"(20\d{2})[-/.](0[1-9]|1[0-2])")
    matches = pattern.findall(text)
    if len(matches) >= 2:
        start = f"{matches[0][0]}-{matches[0][1]}"
        end = f"{matches[1][0]}-{matches[1][1]}"
        return f"{start} ~ {end}"
    if len(matches) == 1:
        return f"{matches[0][0]}-{matches[0][1]}"
    return ""


def extract_role_scope(text: str) -> str:
    if re.search(r"Owner|负责人|Owner 意识", text, re.IGNORECASE):
        return "Owner"
    if re.search(r"Tech Lead|技术负责人|TL", text, re.IGNORECASE):
        return "Tech Lead"
    return "执行"


def split_stack(text: str) -> list[str]:
    tokens = re.split(r"[,，/\s]+", text.strip())
    return [token for token in tokens if token]


def unique_list(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


def parse_sections(lines: list[str]) -> SectionData:
    section = None
    data: SectionData = {
        "context": "",
        "actions": [],
        "results": [],
        "artifacts": [],
        "stack": [],
    }
    for line in lines:
        if re.match(r"^(背景|场景)[:：]", line):
            data["context"] = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            section = "context"
            continue
        if re.match(r"^(动作|措施|行动)[:：]", line):
            section = "actions"
            continue
        if re.match(r"^(结果|成效)[:：]", line):
            section = "results"
            continue
        if re.match(r"^(证据|附件)[:：]", line):
            section = "artifacts"
            continue
        if re.match(r"^(技术栈)[:：]", line):
            section = "stack"
            tail = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            if tail:
                data["stack"].extend(split_stack(tail))
            continue

        if section == "context" and not data["context"] and len(line) >= 10:
            data["context"] = line

        if section in {"actions", "results", "artifacts"}:
            if re.match(r"^[-*]\s+", line) or re.match(r"^\d+\.", line):
                content = re.sub(r"^[-*]\s+", "", line)
                content = re.sub(r"^\d+\.\s*", "", content)
                if content:
                    if section == "actions":
                        data["actions"].append(content)
                    elif section == "results":
                        data["results"].append(content)
                    else:
                        data["artifacts"].append(content)
            elif section == "results" and re.search(r"\d", line):
                data["results"].append(line)
        if section == "stack" and line:
            data["stack"].extend(split_stack(line))

    data["actions"] = data["actions"][:5]
    data["results"] = data["results"][:3]
    return data


def extract_actions(lines: list[str]) -> list[str]:
    data = parse_sections(lines)
    if data["actions"]:
        return data["actions"]
    fallback: list[str] = []
    for line in lines:
        if (re.match(r"^[-*]\s+", line) or re.match(r"^\d+\.", line)) and not re.search(
            r"\d", line
        ):
            content = re.sub(r"^[-*]\s+", "", line)
            content = re.sub(r"^\d+\.\s*", "", content)
            if content:
                fallback.append(content)
        if len(fallback) >= 5:
            break
    return fallback


def extract_results(lines: list[str]) -> list[str]:
    data = parse_sections(lines)
    if data["results"]:
        return data["results"]
    results: list[str] = []
    for line in lines:
        if re.search(r"\d", line) and re.search(
            r"%|ms|s|秒|分钟|下降|提升|降低|降至|提高", line
        ):
            results.append(line)
        if len(results) >= 3:
            break
    return results


def extract_stack(text: str, lines: list[str]) -> list[str]:
    data = parse_sections(lines)
    if data["stack"]:
        return unique_list([token for token in data["stack"]])
    found: list[str] = []
    for token in TECH_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", text):
            found.append(token)
    return found


def extract_artifacts(text: str, lines: list[str]) -> list[str]:
    data = parse_sections(lines)
    artifacts: list[str] = list(data["artifacts"])
    if not artifacts:
        for match in re.finditer(
            r"[\w\-./]+\.(pdf|png|jpg|jpeg|md|xlsx|pptx|docx)", text, re.IGNORECASE
        ):
            artifacts.append(match.group(0))
        artifacts.extend(re.findall(r"https?://\S+", text))
    return unique_list(artifacts)


def extract_tags(text: str) -> list[str]:
    tags: list[str] = []
    for token in TAG_TOKENS:
        if token in text:
            tags.append(token)
    return tags


def extract_context(lines: list[str]) -> str:
    data = parse_sections(lines)
    if data["context"]:
        return data["context"]
    for line in lines:
        if len(line) >= 10 and not re.match(r"^[-*]|^\d+\.", line):
            return line
    return ""


def guess_title(lines: list[str]) -> str:
    for line in lines:
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line.startswith("项目："):
            return line.replace("项目：", "", 1).strip()
    return ""


def build_gaps(card: EvidenceCardDraft) -> list[str]:
    gaps: list[str] = []
    if not card["time_range"]:
        gaps.append("缺少时间范围")
    if len(card["actions"]) < 3:
        gaps.append("动作不足 3 条")
    if not card["results"]:
        gaps.append("缺少量化结果")
    if not card["artifacts"]:
        gaps.append("缺少可验证证据/附件")
    if not card["stack"]:
        gaps.append("缺少技术栈")
    return gaps


def build_draft(
    text: str,
    *,
    card_id: str,
    title: str = "",
    raw_source: str = "",
) -> EvidenceCardDraft:
    """把原始文本转成 Evidence Card 草稿（字段完整、确定性）。"""

    lines = split_lines(text)
    resolved_title = title or guess_title(lines) or "未命名经历"
    return EvidenceCardDraft(
        id=card_id,
        title=resolved_title,
        raw_source=raw_source,
        time_range=extract_time_range(text),
        context=extract_context(lines),
        role_scope=extract_role_scope(text),
        actions=extract_actions(lines),
        results=extract_results(lines),
        stack=extract_stack(text, lines),
        artifacts=extract_artifacts(text, lines),
        tags=extract_tags(text),
        interview_hooks=[],
    )


def dump_yaml(evidence_card: EvidenceCardDraft, gaps: list[str]) -> str:
    def dump_list(items: list[str], indent: int = 2) -> str:
        if not items:
            return "[]"
        prefix = " " * indent
        return "\n".join([f'{prefix}- "{item}"' for item in items])

    lines = [
        f"id: \"{evidence_card['id']}\"",
        f"title: \"{evidence_card['title']}\"",
        f"raw_source: \"{evidence_card['raw_source']}\"",
        f"time_range: \"{evidence_card['time_range']}\"",
        f"context: \"{evidence_card['context']}\"",
        f"role_scope: \"{evidence_card['role_scope']}\"",
        "actions:",
        dump_list(evidence_card["actions"], indent=2),
        "results:",
        dump_list(evidence_card["results"], indent=2),
        "stack:",
        dump_list(evidence_card["stack"], indent=2),
        "artifacts:",
        dump_list(evidence_card["artifacts"], indent=2),
        "tags:",
        dump_list(evidence_card["tags"], indent=2),
        "interview_hooks:",
        dump_list(evidence_card["interview_hooks"], indent=2),
        "gaps:",
        dump_list(gaps, indent=2),
    ]
    return "\n".join(lines) + "\n"


class RuleEvidenceExtractor:
    """规则提炼引擎：domain EvidenceCard 适配。

    供 Agent 编排的 evidence 策略注册使用；字段缺失不在这里编造，
    是否可入池由 domain 的 evidence-first 守卫判断。
    """

    def extract(self, raw_material: str) -> EvidenceCard:
        draft = build_draft(
            raw_material,
            card_id="ec-rule-extract",
            raw_source="",
        )
        return EvidenceCard(
            id=draft["id"],
            title=draft["title"],
            raw_source=draft["raw_source"],
            results=tuple(draft["results"]),
            artifacts=tuple(draft["artifacts"]),
            tags=tuple(draft["tags"]),
            stack=tuple(draft["stack"]),
            period=draft["time_range"],
            context=draft["context"],
            role_scope=draft["role_scope"],
        )
