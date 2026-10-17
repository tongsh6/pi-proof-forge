"""知识索引：材料/证据卡/职业档案/岗位画像的确定性导航索引（非 RAG）。

索引只做导航：派生值（日期窗口/类型）不是事实；引用必须回读原文并以
material_id / document_id / sha256 三元组锚定。设计见
AIEF/docs/plans/2026-10-17-knowledge-index.md。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.infra.material_documents import split_material_documents
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.career_profile import parse_project_period
from tools.infra import referenced_materials as rm
from tools.infra.knowledge_coverage import build_source_coverage

BUILDER_VERSION = "kb-index-v1"

# 人写文档白名单：本人角色/经历的逐字来源；其余文档的"负责/主导"多为系统职责噪声。
PERSON_DOC_MATERIALS = {
    "mat_331bc1bc": "已确认职业与教育时间线（时间事实唯一来源）",
    "mat_723e3040": "EC+工作经历详细底稿（含'我的角色'段落）",
    "mat_ff4f2006": "九恒星项目经验原始记录（逐项目区间与责任描述）",
    "mat_2e91704b": "早期个人与工作经历原始记录（2017 版项目角色）",
    "mat_4c98d63a": "个人 AI 开源作品集（个人项目自述）",
    "mat_ae7f0dbd": "Sophon 面试准备排练稿（未排练；不新增事实）",
    "mat_2b6f65a5": "职业方向综合分析（含已确认求职偏好来源）",
    "mat_660ac6d6": "众安入职月工作日志",
}
PERSON_DOC_LABELS = {"工作汇总-1.md", "工作汇总.md"}
PERSON_DOC_LABEL_MATERIALS = {"mat_7dad703c": "工作汇总（品牌级周期与角色句）"}
# 合成测试夹具：任何情况下不得作为简历事实来源。
NONFACT_MATERIALS = {"mat_quick_run_verify": "合成测试夹具，不得作为简历事实来源"}

DOC_TYPES = (
    ("速读卡", "速读卡"), ("业务地图", "业务地图"), ("架构切片", "架构切片"),
    ("验收", "验收"), ("发布", "发布"), ("复盘", "复盘"), ("术语表", "术语表"),
    ("总结", "总结"), ("需求", "需求"), ("方案", "方案"), ("日志", "日志"),
    ("清单", "清单"), ("手册", "手册"), ("规范", "规范"), ("INDEX", "索引"),
)
SHORT_COMPANY = {
    "一里智辉（EC+）": "EC+",
    "众安保险": "众安",
    "九恒星（上海）金融信息服务有限公司": "九恒星",
    "上海伊尔普信息技术有限公司": "伊尔普",
}

_DATE_RE = re.compile(r"(20\d{2})\s*[-./年]\s*(\d{1,2})")
_CREATED_RE = re.compile(r"created:\s*'?(\d{4}-\d{2}-\d{2})")
_UPDATED_RE = re.compile(r"updated:\s*'?(\d{4}-\d{2}-\d{2})")
_TITLE_RE = re.compile(r"^\s*title:\s*'?([^'\n]+?)'?\s*$", re.M)
_HEADING_RE = re.compile(r"^#\s+(.+)$", re.M)


def doc_type_for(label: str) -> str:
    stem = label.split("/")[-1]
    for key, value in DOC_TYPES:
        if key in stem:
            return value
    return "文档"


def title_from(text: str, label: str) -> str:
    match = _TITLE_RE.search(text[:400])
    if match:
        return match.group(1).strip()
    heading = _HEADING_RE.search(text)
    if heading:
        return heading.group(1).strip()[:60]
    stem = label.split("/")[-1].rsplit(".", 1)[0]
    return stem or label


def extract_dates(text: str) -> dict[str, Any]:
    created = _CREATED_RE.search(text[:600])
    updated = _UPDATED_RE.search(text[:600])
    frontmatter = None
    if created or updated:
        frontmatter = {"created": created.group(1) if created else None,
                       "updated": updated.group(1) if updated else None}
    months = sorted({f"{year}-{int(month):02d}" for year, month in _DATE_RE.findall(text)})
    return {"frontmatter": frontmatter, "window": [months[0], months[-1]] if months else None}


def short_company(company: str) -> str:
    if company in SHORT_COMPANY:
        return SHORT_COMPANY[company]
    inner = re.search(r"[（(]([^）)]{1,10})[）)]", company)
    if inner:
        return inner.group(1)
    cleaned = re.sub(r"(股份有限公司|有限责任公司|有限公司|（上海）|\(上海\))", "", company).strip()
    return (cleaned or company)[:6]


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_person_doc(material_id: str, label: str) -> bool:
    if material_id in PERSON_DOC_MATERIALS:
        return True
    if material_id in PERSON_DOC_LABEL_MATERIALS and label.split("/")[-1] in PERSON_DOC_LABELS:
        return True
    return False


def _build_materials(root: Path, skipped: list[dict[str, str]]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], list[str] | None]]:
    materials: dict[str, dict[str, Any]] = {}
    windows: dict[tuple[str, str], list[str] | None] = {}
    meta_dir = root / "materials"
    if not meta_dir.is_dir():
        return materials, windows
    for meta_path in sorted(meta_dir.glob("*.meta.yaml")):
        try:
            meta = parse_simple_yaml(meta_path.read_text(encoding="utf-8"))["scalars"]
        except (OSError, UnicodeDecodeError, ValueError, KeyError):
            skipped.append({"kind": "material", "file": meta_path.name, "error": "unreadable"})
            continue
        material_id = str(meta.get("material_id") or meta_path.stem.replace(".meta", ""))
        filename = str(meta.get("filename") or "")
        path = meta_dir / filename
        if not filename or not path.is_file():
            skipped.append({"kind": "material", "file": meta_path.name, "error": "filename_missing"})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped.append({"kind": "material", "file": meta_path.name, "error": "unreadable"})
            continue
        source_mode = str(meta.get("source_mode") or "")
        reference_status = ""
        if source_mode == "referenced":
            manifest_path = meta_dir / ".referenced" / f"{material_id}.manifest.json"
            manifest: dict[str, Any] = {}
            manifest_ok = manifest_path.is_file()
            if manifest_ok:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except ValueError:
                    manifest_ok = False
            target = Path(str(meta.get("source_root") or "")) / str(meta.get("source_relpath") or "")
            if not manifest_ok:
                reference_status = "changed"
            else:
                try:
                    from tools.policy.exclusions import load_material_source_roots, resolve_policy_path
                    rm.resolve_under_roots(target, load_material_source_roots(resolve_policy_path(root)))
                    reference_status = rm.verify_manifest(target, manifest).get("status", "changed")
                except (OSError, ValueError):
                    reference_status = "changed"
            if not text and reference_status == "ok" and manifest.get("files"):
                try:
                    text = rm.merge_text(target, manifest["files"])
                except OSError:
                    text = ""
        entries: list[dict[str, Any]] = []
        for doc in split_material_documents(text, Path(filename).name):
            dates = extract_dates(doc["text"])
            windows[(material_id, doc["document_id"])] = dates["window"]
            entries.append({
                "document_id": doc["document_id"],
                "label": doc["label"],
                "source_name": doc["source_name"],
                "path": doc["label"].split("/")[:-1],
                "doc_type": doc_type_for(doc["label"]),
                "title": title_from(doc["text"], doc["label"]),
                "chars": doc["char_count"],
                "sha256": doc["sha256"],
                "dates": dates,
                "person_doc": _is_person_doc(material_id, doc["label"]),
            })
        materials[material_id] = {
            "material_id": material_id,
            "label": str(meta.get("label") or ""),
            "kind": str(meta.get("kind") or ""),
            "filename": filename,
            "source_path": str(meta.get("source_path") or ""),
            "sha256": _file_sha(path),
            "bytes": path.stat().st_size,
            "document_count": len(entries),
            "source_mode": source_mode,
            "reference_status": reference_status,
            "source_root": str(meta.get("source_root") or ""),
            "source_relpath": str(meta.get("source_relpath") or ""),
            "file_count": str(meta.get("file_count") or ""),
            "frontmatter_dated": sum(1 for e in entries if e["dates"]["frontmatter"]),
            "date_hint_docs": sum(1 for e in entries if e["dates"]["window"]),
            "documents": entries,
        }
    return materials, windows


def _build_profile(root: Path) -> tuple[dict[str, Any], dict[str, str]]:
    path = root / "personal_profile.yaml"
    if not path.is_file():
        return {}, {}
    try:
        scalars = parse_simple_yaml(path.read_text(encoding="utf-8"))["scalars"]
    except (OSError, UnicodeDecodeError, ValueError):
        return {}, {}
    career: dict[str, Any] = {}
    try:
        career = json.loads(scalars.get("career_json") or "{}")
    except ValueError:
        career = {}
    try:
        revision = str(json.loads(scalars.get("career_review_json") or "{}").get("revision") or "")
    except ValueError:
        revision = ""
    try:
        prefs = json.loads(scalars.get("job_preferences_json") or "{}")
    except ValueError:
        prefs = {}
    work = [{"id": w.get("id", ""), "company": w.get("company", ""),
             "short": short_company(str(w.get("company", ""))), "start": w.get("start", ""),
             "end": w.get("end", ""), "current": bool(w.get("current")),
             "evidence_ids": [str(e) for e in w.get("evidence_ids", [])]}
            for w in career.get("work", [])]
    profile = {
        "file": path.name,
        "file_sha256": _file_sha(path),
        "revision": revision,
        "work": work,
        "education_count": len(career.get("education", [])),
        "skills_count": len(career.get("skills", [])),
        "extras_count": len(career.get("extras", [])),
    }
    if prefs:
        profile["job_preferences"] = {
            "confirmed_at": prefs.get("confirmed_at", ""),
            "items_count": len(prefs.get("items", [])),
            "source": prefs.get("source") or {},
        }
    employer_by_card = {eid: w["short"] for w in work for eid in w["evidence_ids"]}
    return profile, employer_by_card


def _build_cards(root: Path, windows: dict[tuple[str, str], list[str] | None],
                 employer_by_card: dict[str, str], skipped: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    cards_dir = root / "evidence_cards"
    if not cards_dir.is_dir():
        return cards
    for path in sorted(cards_dir.glob("*.yaml")):
        try:
            doc = parse_simple_yaml(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, KeyError) as exc:
            skipped.append({"kind": "card", "file": path.name, "error": type(exc).__name__})
            continue
        scalars, lists = doc["scalars"], doc["lists"]
        card_id = str(scalars.get("id") or path.stem)
        status = str(scalars.get("status") or "")
        missing = []
        if not parse_project_period(str(scalars.get("time_range") or "")):
            missing.append("time_range")
        if not str(scalars.get("role_scope") or "").strip():
            missing.append("role_scope")
        try:
            refs = json.loads(scalars.get("source_documents_json") or "[]")
        except ValueError:
            refs = []
        hints = sorted({month for ref in refs
                        for month in (windows.get((ref.get("material_id"), ref.get("document_id"))) or [])})[:6]
        cards[card_id] = {
            "file": path.name,
            "sha256": _file_sha(path),
            "title": str(scalars.get("title") or ""),
            "status": status,
            "demo": not status,
            "time_range": str(scalars.get("time_range") or ""),
            "role_scope": str(scalars.get("role_scope") or ""),
            "candidate_pool_eligible": scalars.get("candidate_pool_eligible") == "true",
            "missing": missing,
            "date_hints": hints,
            "employer": employer_by_card.get(card_id, ""),
            "source_material_ids": [str(m) for m in lists.get("source_material_ids", [])],
            "source_documents": [{"material_id": str(r.get("material_id") or ""),
                                  "document_id": str(r.get("document_id") or ""),
                                  "sha256": str(r.get("sha256") or ""),
                                  "label": str(r.get("label") or "")} for r in refs],
        }
    return cards


def _build_jobs(root: Path, skipped: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    jobs_dir = root / "job_profiles"
    if not jobs_dir.is_dir():
        return jobs
    for path in sorted(jobs_dir.glob("jp*.yaml")):
        try:
            scalars = parse_simple_yaml(path.read_text(encoding="utf-8"))["scalars"]
        except (OSError, UnicodeDecodeError, ValueError, KeyError) as exc:
            skipped.append({"kind": "job", "file": path.name, "error": type(exc).__name__})
            continue
        status = str(scalars.get("status") or "")
        jobs[path.stem] = {
            "file": path.name,
            "sha256": _file_sha(path),
            "job_id": path.stem,
            "target_role": str(scalars.get("target_role") or ""),
            "company": str(scalars.get("company") or ""),
            "status": status,
            "demo": not status,
            "lead_id": str(scalars.get("job_lead_id") or ""),
            "platform": str(scalars.get("platform") or ""),
            "created_at": str(scalars.get("created_at") or ""),
            "updated_at": str(scalars.get("updated_at") or ""),
            "jd_chars": len(str(scalars.get("source_jd") or "")),
            "jd_sha256": str(scalars.get("source_jd_sha256") or ""),
        }
    return jobs


def _build_leads(root: Path, skipped: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    leads: dict[str, dict[str, Any]] = {}
    leads_dir = root / "job_leads"
    if not leads_dir.is_dir():
        return leads
    for path in sorted(leads_dir.glob("jl*.yaml")):
        try:
            scalars = parse_simple_yaml(path.read_text(encoding="utf-8"))["scalars"]
        except (OSError, UnicodeDecodeError, ValueError, KeyError) as exc:
            skipped.append({"kind": "lead", "file": path.name, "error": type(exc).__name__})
            continue
        status = str(scalars.get("status") or "")
        leads[path.stem] = {
            "file": path.name,
            "sha256": _file_sha(path),
            "lead_id": path.stem,
            "company": str(scalars.get("company") or ""),
            "position": str(scalars.get("position") or ""),
            "status": status,
            "demo": not status,
            "favorited": scalars.get("favorited") == "true",
            "job_profile_id": str(scalars.get("job_profile_id") or ""),
            "platform": str(scalars.get("platform") or ""),
            "salary": str(scalars.get("salary") or ""),
            "location": str(scalars.get("location") or ""),
            "company_size": str(scalars.get("company_size") or ""),
            "industry": str(scalars.get("industry") or ""),
            "work_years": str(scalars.get("work_years") or ""),
            "education": str(scalars.get("education") or ""),
            "jd_status": str(scalars.get("jd_status") or ""),
            "created_at": str(scalars.get("created_at") or ""),
            "updated_at": str(scalars.get("updated_at") or ""),
        }
    return leads


def _build_relations(cards: dict[str, dict[str, Any]], profile: dict[str, Any],
                     jobs: dict[str, dict[str, Any]], leads: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    relations: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source: str, kind: str, target: str) -> None:
        key = (source, kind, target)
        if key not in seen:
            seen.add(key)
            relations.append({"from": source, "type": kind, "to": target})

    for card_id in sorted(cards):
        for ref in cards[card_id]["source_documents"]:
            if ref["material_id"] and ref["document_id"]:
                add(f"card:{card_id}", "cites", f"doc:{ref['material_id']}:{ref['document_id']}")
    for work in profile.get("work", []):
        for evidence_id in work["evidence_ids"]:
            add(f"work:{work['id']}", "evidence", f"card:{evidence_id}")
    source = (profile.get("job_preferences") or {}).get("source") or {}
    if source.get("material_id") and source.get("document_id"):
        add("profile:job_preferences", "sourced_from", f"doc:{source['material_id']}:{source['document_id']}")
    promoted = {(lead_id, lead["job_profile_id"]) for lead_id, lead in leads.items() if lead["job_profile_id"]}
    promoted |= {(job["lead_id"], job_id) for job_id, job in jobs.items() if job["lead_id"]}
    for lead_id, job_id in sorted(promoted):
        add(f"lead:{lead_id}", "promoted_to", f"job:{job_id}")
    return relations


def build_index(root: Path, now: str | None = None) -> dict[str, Any]:
    root = Path(root)
    skipped: list[dict[str, str]] = []
    materials, windows = _build_materials(root, skipped)
    profile, employer_by_card = _build_profile(root)
    cards = _build_cards(root, windows, employer_by_card, skipped)
    jobs = _build_jobs(root, skipped)
    leads = _build_leads(root, skipped)
    status_counts: dict[str, int] = {}
    for card in cards.values():
        key = card["status"] or "demo"
        status_counts[key] = status_counts.get(key, 0) + 1
    person_docs = [{"material_id": material_id, "label": materials[material_id]["label"], "note": note}
                   for material_id, note in (*PERSON_DOC_MATERIALS.items(), *PERSON_DOC_LABEL_MATERIALS.items())
                   if material_id in materials]
    nonfact = [{"material_id": material_id, "reason": reason}
               for material_id, reason in NONFACT_MATERIALS.items() if material_id in materials]
    return {
        "builder": BUILDER_VERSION,
        "built_at": now or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "assets": {
            "materials": len(materials),
            "documents": sum(m["document_count"] for m in materials.values()),
            "referenced_materials": sum(1 for m in materials.values() if m.get("source_mode") == "referenced"),
            "cards": {**status_counts, "demo": sum(1 for c in cards.values() if c["demo"])},
            "job_profiles": {"real": sum(1 for j in jobs.values() if not j["demo"]),
                             "samples": sum(1 for j in jobs.values() if j["demo"])},
            "leads": {"real": sum(1 for x in leads.values() if not x["demo"]),
                      "samples": sum(1 for x in leads.values() if x["demo"])},
            "profile": {"revision": profile.get("revision", "")},
        },
        "materials": materials,
        "cards": cards,
        "jobs": jobs,
        "leads": leads,
        "profile": profile,
        "relations": _build_relations(cards, profile, jobs, leads),
        "person_docs": person_docs,
        "nonfact_materials": nonfact,
        "skipped": skipped,
        "asset_inventory": _asset_inventory(root),
        "source_coverage": build_source_coverage(root, materials),
    }


def _asset_inventory(root: Path) -> dict[str, str]:
    paths = [p for folder, pattern in (("materials", "*.meta.yaml"), ("evidence_cards", "*.yaml"),
                                      ("job_profiles", "*.yaml"), ("job_leads", "*.yaml"))
             for p in (root / folder).glob(pattern)]
    if (root / "personal_profile.yaml").is_file():
        paths.append(root / "personal_profile.yaml")
    result = {}
    for path in sorted(paths):
        try:
            result[path.relative_to(root).as_posix()] = _file_sha(path)
        except OSError:
            result[path.relative_to(root).as_posix()] = "unreadable"
    return result


def _top_dirs(entry: dict[str, Any], limit: int = 5) -> str:
    counts: dict[str, int] = {}
    for doc in entry["documents"]:
        parts = doc["label"].split("/")
        key = parts[0] if len(parts) > 1 else "（单档）"
        counts[key] = counts.get(key, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return "/".join(f"{name}{count}" for name, count in ordered)


def render_index_md(index: dict[str, Any]) -> str:
    assets = index["assets"]
    cards = index["cards"]
    real = [c for c in cards.values() if not c["demo"]]
    missing_any = [c for c in real if c["missing"]]
    with_hints = [c for c in missing_any if c["date_hints"]]
    by_employer: dict[str, int] = {}
    for card in missing_any:
        key = card["employer"] or "未关联任职"
        by_employer[key] = by_employer.get(key, 0) + 1
    lines = [
        "# 知识索引 · INDEX（本地生成，不入库）",
        "",
        f"> built_at: {index['built_at']} ｜ builder: {index['builder']} ｜ 校验: `kb verify`",
        "",
        "## 资产盘点",
        "| 资产 | 数量 | 备注 |",
        "|---|---|---|",
        f"| 材料 | {assets['materials']} 份 → **{assets['documents']} 档** | 逐档含 document_id/sha256 与日期线索 |",
        f"| 证据卡 | {sum(assets['cards'].values())} 张 | " + " / ".join(f"{k} {v}" for k, v in sorted(assets['cards'].items() if isinstance(assets['cards'], dict) else [])) + " |",
        f"| 岗位画像 | {assets['job_profiles']['real'] + assets['job_profiles']['samples']} 份 | {assets['job_profiles']['real']} 真实 + {assets['job_profiles']['samples']} 示例 |",
        f"| 岗位线索 | {assets['leads']['real'] + assets['leads']['samples']} 条 | {assets['leads']['real']} 真实 + {assets['leads']['samples']} 示例 |",
        f"| 职业档案 | 1 份 | revision {(assets['profile']['revision'] or '（未确认）')[:16]} |",
        "",
        "## 材料树",
        "| 材料 | 档数 | 主要目录 |",
        "|---|---|---|",
    ]
    for material in sorted(index["materials"].values(), key=lambda m: (-m["document_count"], m["material_id"])):
        marker = "（引用）" if material.get("source_mode") == "referenced" else ""
        lines.append(f"| {material['material_id']} {material['label']}{marker} | {material['document_count']} 档 | {_top_dirs(material)} |")
    lines += ["", "## 非事实材料警示"]
    if index["nonfact_materials"]:
        for item in index["nonfact_materials"]:
            lines.append(f"- {item['material_id']}：{item['reason']}")
    else:
        lines.append("- 无")
    lines += ["", "## 索引缺口"]
    if index.get("skipped"):
        for item in index["skipped"]:
            lines.append(f"- {item['kind']}：{item['file']}（{item['error']}）")
    else:
        lines.append("- 已登记资产构建无错误；不代表上游来源已全部纳入正文。")
    coverage = index.get("source_coverage", {})
    lines += ["", "## 来源覆盖（文件数，不等于正文分片数）"]
    if not coverage.get("roots"):
        lines.append("- 未配置材料来源根；本次仅检查已登记资产。")
    else:
        labels = {"indexed": "正文已索引", "unindexed": "未纳入正文", "stale": "来源与快照不一致",
                  "filtered": "按拆档规则过滤", "metadata_only": "仅目录（附件/LFS/非UTF-8）", "unavailable": "无法读取"}
        lines += ["| 状态 | 数量 |", "|---|---|"]
        for status, count in sorted(coverage.get("counts", {}).items()):
            lines.append(f"| {labels.get(status, status)} `{status}` | {count} |")
        pointers = sum(x["availability"] == "lfs_pointer" for x in coverage["items"])
        lines += [f"- Git LFS 指针：{pointers}；不含原件正文，不自动下载。",
                  "- 附件只提供路径/格式/可用状态，不进入证据池；学习资料与模板未纳入项不等于遗漏事实。",
                  "- 明细：`kb coverage --status unindexed` / `kb coverage --status metadata_only --json`。"]
        if coverage.get("excluded_counts"):
            lines.append("- 扫描排除（隐藏目录按目录计数）：" + " / ".join(
                f"{reason} {count}" for reason, count in coverage["excluded_counts"].items()))
        for error in coverage.get("errors", []):
            lines.append(f"- 扫描未完成：{error['root_id']}/{error['path']}（{error['reason']}）")
    lines += ["", "## 范围说明",
              "- 纳入：材料 / 证据卡 / 职业档案 / 岗位画像 / 岗位线索",
              "- 上游：私有工作仓 worklog-private/ 为材料来源；引用式材料（source_mode=referenced）不复制纳入，其余未纳入部分按需分批",
              "- 正文只纳入材料库的 md/txt；INDEX/AGENTS/CLAUDE/local-paths 与 templates/rules 目录按原拆档规则过滤。",
              "- 排除：匹配报告与运行产物（matching_reports/、outputs/，属运行输出）、上传简历记录（uploaded_resumes/，平台产物）、"
              "profiles/candidate_profile.yaml（模板占位）、release-notes/ 与 scripts/（仓库工程）；"
              "ui/src-tauri/resources/evidence_cards|job_profiles 为本地镜像副本，不重复索引",
              "", "## 待办信号（自动统计）",
              f"- 真实卡 {len(real)} 张，其中 **{len(missing_any)} 张缺时间或职责**（"
              + " / ".join(f"{k} {v}" for k, v in sorted(by_employer.items(), key=lambda kv: -kv[1])) + "）",
              f"- 其中 {len(with_hints)} 张引用文档含日期线索；人写文档白名单 {len(index['person_docs'])} 份（角色句可信来源）",
              "", "## AI 使用说明（纪律）",
              "1. 索引里的派生值（日期窗口/类型/线索）**不是事实**；引用前必须 `kb read` 回原文",
              "2. 每个引用必须携带 material_id / document_id / sha256 三元组",
              "3. 材料变化后先 `kb verify`，不通过则 `kb build` 重建",
              "4. 常用命令：`kb tree / kb find / kb grep / kb read / kb refs / kb cards / kb person-docs`"]
    return "\n".join(lines) + "\n"


def verify_index(root: Path, index: dict[str, Any]) -> list[dict[str, str]]:
    root = Path(root)
    stale: list[dict[str, str]] = []
    if index.get("asset_inventory") != _asset_inventory(root):
        stale.append({"kind": "inventory", "ref": "registered_assets", "path": "."})
    coverage = build_source_coverage(root, index.get("materials", {}))
    if coverage != index.get("source_coverage") or coverage["errors"]:
        stale.append({"kind": "source_coverage", "ref": "allowed_roots", "path": "."})

    def check(kind: str, ref: str, path: Path, expected: str) -> None:
        if not path.is_file() or _file_sha(path) != expected:
            stale.append({"kind": kind, "ref": ref, "path": str(path.relative_to(root))})

    for material_id, material in index.get("materials", {}).items():
        check("material", material_id, root / "materials" / material["filename"], material["sha256"])
        if material.get("source_mode") == "referenced":
            manifest_path = root / "materials" / ".referenced" / f"{material_id}.manifest.json"
            source_ok = manifest_path.is_file()
            if source_ok:
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    target = Path(str(material.get("source_root") or "")) / str(material.get("source_relpath") or "")
                    from tools.policy.exclusions import load_material_source_roots, resolve_policy_path
                    rm.resolve_under_roots(target, load_material_source_roots(resolve_policy_path(root)))
                    source_ok = rm.verify_manifest(target, manifest).get("status") == "ok"
                except (OSError, ValueError):
                    source_ok = False
            if not source_ok:
                stale.append({"kind": "material", "ref": material_id,
                              "path": f"{material.get('source_root', '')}/{material.get('source_relpath', '')}"})
    for card_id, card in index.get("cards", {}).items():
        check("card", card_id, root / "evidence_cards" / card["file"], card["sha256"])
    for job_id, job in index.get("jobs", {}).items():
        check("job", job_id, root / "job_profiles" / job["file"], job["sha256"])
    for lead_id, lead in index.get("leads", {}).items():
        check("lead", lead_id, root / "job_leads" / lead["file"], lead["sha256"])
    profile = index.get("profile") or {}
    if profile.get("file"):
        check("profile", "personal_profile", root / profile["file"], profile["file_sha256"])
    return sorted(stale, key=lambda item: (item["kind"], item["ref"]))


def save_index(index: dict[str, Any], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
    (out_dir / "INDEX.md").write_text(render_index_md(index), encoding="utf-8")


def load_index(out_dir: Path) -> dict[str, Any]:
    return json.loads((Path(out_dir) / "index.json").read_text(encoding="utf-8"))
