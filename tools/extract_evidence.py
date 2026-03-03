#!/usr/bin/env python3
import argparse
import datetime
import re
from pathlib import Path
from typing import TypedDict, cast


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


def read_text(input_path: str) -> str:
    if input_path == "-":
        return Path("/dev/stdin").read_text(encoding="utf-8")
    return Path(input_path).read_text(encoding="utf-8")


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


def split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


class SectionData(TypedDict):
    context: str
    actions: list[str]
    results: list[str]
    artifacts: list[str]
    stack: list[str]


class EvidenceCard(TypedDict):
    id: str
    title: str
    time_range: str
    context: str
    role_scope: str
    actions: list[str]
    results: list[str]
    stack: list[str]
    artifacts: list[str]
    tags: list[str]
    interview_hooks: list[str]


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


def split_stack(text: str) -> list[str]:
    tokens = re.split(r"[,，/\s]+", text.strip())
    return [token for token in tokens if token]


def extract_actions(lines: list[str]) -> list[str]:
    data = parse_sections(lines)
    if data["actions"]:
        return data["actions"]
    fallback: list[str] = []
    for line in lines:
        if (re.match(r"^[-*]\s+", line) or re.match(r"^\d+\.", line)) and not re.search(r"\d", line):
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
        if re.search(r"\d", line) and re.search(r"%|ms|s|秒|分钟|下降|提升|降低|降至|提高", line):
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
        for match in re.finditer(r"[\w\-./]+\.(pdf|png|jpg|jpeg|md|xlsx|pptx|docx)", text, re.IGNORECASE):
            artifacts.append(match.group(0))
        artifacts.extend(re.findall(r"https?://\S+", text))
    return unique_list(artifacts)


def unique_list(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        if item not in unique:
            unique.append(item)
    return unique


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


def build_gaps(card: EvidenceCard) -> list[str]:
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


def dump_yaml(evidence_card: EvidenceCard, gaps: list[str]) -> str:
    def dump_list(items: list[str], indent: int = 2) -> str:
        if not items:
            return "[]"
        prefix = " " * indent
        return "\n".join([f"{prefix}- \"{item}\"" for item in items])

    lines = [
        "evidence_card:",
        f"  id: \"{evidence_card['id']}\"",
        f"  title: \"{evidence_card['title']}\"",
        f"  time_range: \"{evidence_card['time_range']}\"",
        f"  context: \"{evidence_card['context']}\"",
        f"  role_scope: \"{evidence_card['role_scope']}\"",
        "  actions:",
        dump_list(evidence_card["actions"], indent=4),
        "  results:",
        dump_list(evidence_card["results"], indent=4),
        "  stack:",
        dump_list(evidence_card["stack"], indent=4),
        "  artifacts:",
        dump_list(evidence_card["artifacts"], indent=4),
        "  tags:",
        dump_list(evidence_card["tags"], indent=4),
        "  interview_hooks:",
        dump_list(evidence_card["interview_hooks"], indent=4),
        "gaps:",
        dump_list(gaps, indent=2),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract evidence card from raw material")
    _ = parser.add_argument("--input", required=True, help="Raw material path or '-' for stdin")
    _ = parser.add_argument("--id", help="Evidence card id (optional)")
    _ = parser.add_argument("--title", help="Title override (optional)")
    _ = parser.add_argument("--output", help="Output YAML path (optional)")
    args = parser.parse_args()

    input_path = cast(str, args.input)
    output_path = cast(str | None, args.output)
    id_arg = cast(str | None, args.id)
    title_arg = cast(str | None, args.title)

    text = read_text(input_path)
    lines = split_lines(text)
    evidence_id = id_arg or datetime.datetime.now().strftime("ec-%Y%m%d%H%M%S")
    title = title_arg or guess_title(lines) or "未命名经历"

    card: EvidenceCard = {
        "id": evidence_id,
        "title": title,
        "time_range": extract_time_range(text),
        "context": extract_context(lines),
        "role_scope": extract_role_scope(text),
        "actions": extract_actions(lines),
        "results": extract_results(lines),
        "stack": extract_stack(text, lines),
        "artifacts": extract_artifacts(text, lines),
        "tags": extract_tags(text),
        "interview_hooks": [],
    }

    gaps = build_gaps(card)
    output = dump_yaml(card, gaps)

    if output_path:
        _ = Path(output_path).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
