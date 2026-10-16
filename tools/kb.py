"""kb：知识索引构建与查询 CLI（面向 AI 代理的确定性接口，非 RAG）。

用法见 AIEF/docs/plans/2026-10-17-knowledge-index.md；纪律：
索引只做导航，引用前用 `kb read` 回原文，引用必须带
material_id / document_id / sha256 三元组。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.infra import knowledge_index as ki
from tools.infra.material_documents import split_material_documents

INDEX_DIR = "knowledge-index"


def _load_index(root: str):
    path = Path(root) / INDEX_DIR / "index.json"
    if not path.is_file():
        print("index_not_built: run `kb build` first")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _doc_line(material_id: str, doc: dict) -> str:
    window = doc["dates"]["window"]
    hint = f"{window[0]}~{window[1]}" if window else "-"
    return f"{material_id}/{doc['label']}  {doc['chars']}字  类型:{doc['doc_type']}  日期窗口:{hint}"


def _iter_docs(index: dict):
    for material_id in sorted(index["materials"]):
        for doc in index["materials"][material_id]["documents"]:
            yield material_id, doc


def _cmd_build(args) -> int:
    index = ki.build_index(Path(args.root))
    out = Path(args.out) if args.out else Path(args.root) / INDEX_DIR
    ki.save_index(index, out)
    assets = index["assets"]
    cards = sum(assets["cards"].values())
    jobs = assets["job_profiles"]["real"] + assets["job_profiles"]["samples"]
    print(f"built ok: materials={assets['materials']} documents={assets['documents']} "
          f"cards={cards} jobs={jobs} leads={assets['leads']['real'] + assets['leads']['samples']} -> {out}")
    return 0


def _cmd_tree(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    material = index["materials"].get(args.material)
    if material is None:
        print(f"unknown_material: {args.material}")
        return 1
    docs = [d for d in material["documents"] if d["label"].startswith(args.prefix or "")]
    if args.json:
        print(json.dumps(docs, ensure_ascii=False, indent=1))
        return 0
    if not docs:
        print("no_documents")
        return 0
    for doc in docs:
        print(_doc_line(args.material, doc))
    return 0


def _window_overlaps(window, date_from: str | None, date_to: str | None) -> bool:
    if not window:
        return False
    if date_from and window[1] < date_from:
        return False
    if date_to and window[0] > date_to:
        return False
    return True


def _cmd_find(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    token = (args.title_token or "").casefold()
    rows: list[tuple[str, dict]] = []
    for material_id, doc in _iter_docs(index):
        if args.material and material_id != args.material:
            continue
        if args.type and doc["doc_type"] != args.type:
            continue
        if args.path and not doc["label"].startswith(args.path):
            continue
        if token and token not in (doc["title"] + " " + doc["label"]).casefold():
            continue
        if (args.date_from or args.date_to) and not _window_overlaps(doc["dates"]["window"], args.date_from, args.date_to):
            continue
        rows.append((material_id, doc))
        if len(rows) >= args.limit:
            break
    if args.json:
        print(json.dumps([{"material_id": m, **d} for m, d in rows], ensure_ascii=False, indent=1))
        return 0
    if not rows:
        print("no_matches")
        return 0
    for material_id, doc in rows:
        print(_doc_line(material_id, doc))
    return 0


def _snippet(text: str, needle: str) -> str:
    lowered = text.casefold()
    position = lowered.find(needle.casefold())
    if position < 0:
        return ""
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    if end < 0:
        end = len(text)
    line = text[start:end].strip()
    return line[:160]


def _cmd_grep(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    needle = args.pattern
    scope = args.scope
    results: list[dict] = []
    if scope in {"docs", "all"}:
        for material_id in sorted(index["materials"]):
            if args.material and material_id != args.material:
                continue
            material = index["materials"][material_id]
            path = Path(args.root) / "materials" / material["filename"]
            if not path.is_file():
                continue
            docs = split_material_documents(path.read_text(encoding="utf-8"), material["filename"])
            for doc in docs:
                if needle.casefold() in doc["text"].casefold():
                    created = next((d["dates"]["frontmatter"]["created"] for d in material["documents"]
                                    if d["document_id"] == doc["document_id"] and d["dates"]["frontmatter"]), None)
                    results.append({"scope": "docs", "material_id": material_id, "document_id": doc["document_id"],
                                    "label": doc["label"], "created": created, "snippet": _snippet(doc["text"], needle)})
                    if len(results) >= args.limit:
                        break
            if len(results) >= args.limit:
                break
    if scope in {"cards", "all"} and len(results) < args.limit:
        for card_id in sorted(index["cards"]):
            card = index["cards"][card_id]
            haystack = " ".join([card["title"], card["role_scope"], card["time_range"],
                                 *[r["label"] for r in card["source_documents"]]])
            if needle.casefold() in haystack.casefold():
                results.append({"scope": "cards", "ref": f"card:{card_id}", "title": card["title"],
                                "status": card["status"]})
    if scope in {"jobs", "all"} and len(results) < args.limit:
        for job_id in sorted(index["jobs"]):
            job = index["jobs"][job_id]
            haystack = " ".join([job["target_role"], job["company"]])
            if needle.casefold() in haystack.casefold():
                results.append({"scope": "jobs", "ref": f"job:{job_id}", "target_role": job["target_role"],
                                "company": job["company"], "status": job["status"]})
    if scope in {"leads", "all"} and len(results) < args.limit:
        for lead_id in sorted(index["leads"]):
            lead = index["leads"][lead_id]
            haystack = " ".join([lead["company"], lead["position"], lead["salary"], lead["location"], lead["industry"]])
            if needle.casefold() in haystack.casefold():
                results.append({"scope": "leads", "ref": f"lead:{lead_id}", "position": lead["position"],
                                "company": lead["company"], "status": lead["status"]})
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
        return 0
    if not results:
        print("no_matches")
        return 0
    for row in results:
        if row["scope"] == "docs":
            created = f"  created {row['created']}" if row["created"] else ""
            print(f"{row['material_id']}  {row['label']}{created}")
            if row["snippet"]:
                print(f"    ▸ {row['snippet']}")
        elif row["scope"] == "cards":
            print(f"{row['ref']}  {row['title']}  {row['status']}")
        elif row["scope"] == "jobs":
            print(f"{row['ref']}  {row['target_role']}  {row['company']}  {row['status']}")
        else:
            print(f"{row['ref']}  {row['position']}  {row['company']}  {row['status']}")
    return 0


def _cmd_read(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    material = index["materials"].get(args.material)
    if material is None:
        print(f"unknown_material: {args.material}")
        return 1
    path = Path(args.root) / "materials" / material["filename"]
    if not path.is_file():
        print(f"stale_document: {args.material}/{args.document_id} material file missing")
        return 2
    docs = split_material_documents(path.read_text(encoding="utf-8"), material["filename"])
    doc = next((d for d in docs if d["document_id"] == args.document_id), None)
    if doc is None:
        print(f"stale_document: {args.material}/{args.document_id} not found in current material; "
              f"run `kb verify` and rebuild")
        return 2
    print(f"# {args.material} / {doc['label']}")
    print(f"# document_id {doc['document_id']}  sha256 {doc['sha256']}  chars {doc['char_count']}")
    print()
    print(doc["text"])
    return 0


def _cmd_refs(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    ident = args.ident.replace("card:", "")
    if ident in index["cards"]:
        card = index["cards"][ident]
        lines = [f"card:{ident}  {card['title']}  [{card['status'] or 'demo'}]"]
        for ref in card["source_documents"]:
            lines.append(f"  cites → {ref['material_id']}:{ref['document_id']}  "
                         f"({ref['label']}, sha256 {ref['sha256'][:12]}…)")
        for relation in index["relations"]:
            if relation["type"] == "evidence" and relation["to"] == f"card:{ident}":
                work_id = relation["from"].replace("work:", "")
                work = next((w for w in index["profile"].get("work", []) if w["id"] == work_id), None)
                suffix = f" ({work['short']} {work['start']}~{work['end'] or '至今'})" if work else ""
                lines.append(f"  used_by → work:{work_id}{suffix}")
        missing = ", ".join(card["missing"]) or "-"
        hints = ", ".join(card["date_hints"]) or "-"
        lines.append(f"  missing: {missing} ｜ date hints: {hints}")
        if args.json:
            print(json.dumps(card, ensure_ascii=False, indent=1))
        else:
            print("\n".join(lines))
        return 0
    work = next((w for w in index["profile"].get("work", []) if w["id"] == ident), None)
    if work:
        lines = [f"work:{ident}  {work['company']}  {work['start']}~{work['end'] or '至今'}"]
        for evidence_id in work["evidence_ids"]:
            card = index["cards"].get(evidence_id, {})
            lines.append(f"  evidence → card:{evidence_id}  {card.get('title', '')}")
        print("\n".join(lines))
        return 0
    print(f"unknown_ref: {args.ident}")
    return 1


def _cmd_cards(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    selected: dict[str, dict] = {}
    for card_id, card in sorted(index["cards"].items()):
        if card["demo"] and not args.include_demo:
            continue
        if args.missing == "time" and "time_range" not in card["missing"]:
            continue
        if args.missing == "role" and "role_scope" not in card["missing"]:
            continue
        if args.missing == "any" and not card["missing"]:
            continue
        if args.has_date_hints and not card["date_hints"]:
            continue
        if args.employer and card["employer"] != args.employer:
            continue
        if args.status and card["status"] != args.status:
            continue
        selected[card_id] = card
    if args.json:
        print(json.dumps(selected, ensure_ascii=False, indent=1))
        return 0
    if not selected:
        print("no_matches")
        return 0
    for card_id, card in selected.items():
        missing = ",".join(card["missing"]) or "-"
        hints = card["date_hints"]
        hint_text = f"{hints[0]}~{hints[-1]}" if hints else "-"
        print(f"{card_id}  {card['title']}  {card['employer'] or '-'}  missing:{missing}  线索:{hint_text}")
    return 0


def _cmd_leads(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    selected: dict[str, dict] = {}
    for lead_id in sorted(index["leads"]):
        lead = index["leads"][lead_id]
        if lead["demo"] and not args.include_demo:
            continue
        if args.status and lead["status"] != args.status:
            continue
        if args.has_profile and not lead["job_profile_id"]:
            continue
        if args.size and args.size not in lead["company_size"]:
            continue
        selected[lead_id] = lead
        if len(selected) >= args.limit:
            break
    if args.json:
        print(json.dumps(selected, ensure_ascii=False, indent=1))
        return 0
    if not selected:
        print("no_matches")
        return 0
    for lead_id, lead in selected.items():
        print(f"{lead_id}  {lead['position']}  {lead['company']}  [{lead['status'] or 'demo'}]  "
              f"{lead['salary'] or '-'}  {lead['location'] or '-'}  {lead['company_size'] or '-'}")
    return 0


def _cmd_person_docs(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    if args.json:
        print(json.dumps(index["person_docs"], ensure_ascii=False, indent=1))
        return 0
    for item in index["person_docs"]:
        print(f"{item['material_id']}  {item['label']}  ({item['note']})")
    return 0


def _cmd_verify(args) -> int:
    index = _load_index(args.root)
    if index is None:
        return 1
    stale = ki.verify_index(Path(args.root), index)
    if args.json:
        print(json.dumps({"ok": not stale, "stale": stale}, ensure_ascii=False, indent=1))
    elif not stale:
        print("ok: index verified")
    else:
        for item in stale:
            print(f"stale {item['kind']}: {item['ref']} ({item['path']})")
        print("run `kb build` to rebuild")
    return 0 if not stale else 2


def _cmd_index(args) -> int:
    path = Path(args.root) / INDEX_DIR / "INDEX.md"
    if not path.is_file():
        print("index_not_built: run `kb build` first")
        return 1
    print(path.read_text(encoding="utf-8"), end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kb", description="知识索引构建与查询（本地，非 RAG）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_root(sp):
        sp.add_argument("--root", default=".", help="知识资产根目录（含 materials/ 等）")
        sp.add_argument("--json", action="store_true", help="输出 JSON")

    build = sub.add_parser("build", help="重建索引（index.json + INDEX.md）")
    add_root(build)
    build.add_argument("--out", default="", help="输出目录（默认 <root>/knowledge-index）")
    build.set_defaults(func=_cmd_build)

    tree = sub.add_parser("tree", help="列出某个材料下的文档")
    add_root(tree)
    tree.add_argument("material")
    tree.add_argument("prefix", nargs="?", default="")
    tree.set_defaults(func=_cmd_tree)

    find = sub.add_parser("find", help="按类型/路径/标题/日期窗口筛选文档")
    add_root(find)
    find.add_argument("--type", default="")
    find.add_argument("--material", default="")
    find.add_argument("--path", default="")
    find.add_argument("--title-token", default="")
    find.add_argument("--date-from", default="")
    find.add_argument("--date-to", default="")
    find.add_argument("--limit", type=int, default=200)
    find.set_defaults(func=_cmd_find)

    grep = sub.add_parser("grep", help="字面检索（docs/cards/jobs）")
    add_root(grep)
    grep.add_argument("pattern")
    grep.add_argument("--scope", choices=["docs", "cards", "jobs", "leads", "all"], default="docs")
    grep.add_argument("--material", default="")
    grep.add_argument("--limit", type=int, default=50)
    grep.set_defaults(func=_cmd_grep)

    read = sub.add_parser("read", help="回读某档原文（校验档号）")
    add_root(read)
    read.add_argument("material")
    read.add_argument("document_id")
    read.set_defaults(func=_cmd_read)

    refs = sub.add_parser("refs", help="查看卡片/任职的引用链")
    add_root(refs)
    refs.add_argument("ident")
    refs.set_defaults(func=_cmd_refs)

    cards = sub.add_parser("cards", help="按缺字段/线索/任职筛选证据卡")
    add_root(cards)
    cards.add_argument("--missing", choices=["time", "role", "any"], default="")
    cards.add_argument("--has-date-hints", action="store_true")
    cards.add_argument("--employer", default="")
    cards.add_argument("--status", default="")
    cards.add_argument("--include-demo", action="store_true")
    cards.set_defaults(func=_cmd_cards)

    leads = sub.add_parser("leads", help="查询岗位线索（默认排除示例）")
    add_root(leads)
    leads.add_argument("--status", default="")
    leads.add_argument("--has-profile", action="store_true")
    leads.add_argument("--size", default="", help="公司规模包含片段")
    leads.add_argument("--include-demo", action="store_true")
    leads.add_argument("--limit", type=int, default=200)
    leads.set_defaults(func=_cmd_leads)

    person = sub.add_parser("person-docs", help="列出人写文档白名单（角色句可信来源）")
    add_root(person)
    person.set_defaults(func=_cmd_person_docs)

    verify = sub.add_parser("verify", help="重哈希校验索引是否失效")
    add_root(verify)
    verify.set_defaults(func=_cmd_verify)

    index = sub.add_parser("index", help="打印 INDEX.md")
    add_root(index)
    index.set_defaults(func=_cmd_index)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
