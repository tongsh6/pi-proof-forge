"""批量证据提炼命令：按项目聚类把材料目录转成待审核证据卡。

用法：:

    python3 -m tools.cli.entrypoints extract-batch --material-id mat_example
    python3 -m tools.cli.entrypoints extract-batch --material-id mat_example --use-llm
    python3 -m tools.cli.entrypoints extract-batch --material-id mat_example --dry-run

事实边界：
- 规则模式只写目录统计（文档数、文档构成），不推测业务内容；
- LLM 模式的每条事实必须能在所选文档原文中定位，否则剔除并记录；
- 两种模式都写 `status: draft` + `candidate_pool_eligible: false`，
  必须由用户在 App 内审核后才能进入候选池。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

from tools.engines.evidence import batch_extract
from tools.infra.persistence.atomic_io import atomic_write_text
from tools.infra.persistence.yaml_io import parse_simple_yaml
from tools.infra.evidence_sources import read_source_documents

DEFAULT_MATERIALS_DIR = Path("materials")
DEFAULT_OUTPUT_DIR = Path("evidence_cards")
DEFAULT_PROGRESS_DIR = Path("outputs/batch_extract")


def _read_material_path(materials_dir: Path, material_id: str) -> Path:
    meta_path = materials_dir / f"{material_id}.meta.yaml"
    if not meta_path.is_file():
        raise ValueError(f"material_metadata_missing:{material_id}")
    meta = parse_simple_yaml(meta_path.read_text(encoding="utf-8"))
    filename = str(meta["scalars"].get("filename") or "")
    if not filename:
        raise ValueError(f"material_filename_missing:{material_id}")
    path = materials_dir / filename
    if not path.is_file():
        raise ValueError(f"material_file_missing:{material_id}")
    return path


def _card_id(cluster_key: str) -> str:
    digest = hashlib.sha256(cluster_key.encode("utf-8")).hexdigest()[:8]
    return f"ec_batch_{digest}"


def _yaml_value(value: Any) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _yaml_list_block(name: str, values: list[str]) -> list[str]:
    """空列表必须写成 `name: []`；写成 `name:` + `[]` 不是合法 YAML。"""
    if not values:
        return [f"{name}: []"]
    return [f"{name}:", *[f"  - {_yaml_value(value)}" for value in values]]


def dump_card(card: dict) -> str:
    reference_json = card.get("source_documents_json") or ""
    lines = [
        f"id: {_yaml_value(card['id'])}",
        f"title: {_yaml_value(card['title'])}",
        f"time_range: {_yaml_value(card.get('time_range', ''))}",
        f"context: {_yaml_value(card.get('context', ''))}",
        f"role_scope: {_yaml_value(card.get('role_scope', ''))}",
        f"status: {_yaml_value(card.get('status', 'draft'))}",
        f"created_at: {_yaml_value(card.get('created_at', ''))}",
        f"updated_at: {_yaml_value(card.get('updated_at', ''))}",
        *_yaml_list_block("actions", list(card.get("actions") or [])),
        *_yaml_list_block("results", list(card.get("results") or [])),
        *_yaml_list_block("planned_results", list(card.get("planned_results") or [])),
        *_yaml_list_block("stack", list(card.get("stack") or [])),
        *_yaml_list_block("artifacts", list(card.get("artifacts") or [])),
        *_yaml_list_block("tags", list(card.get("tags") or [])),
        f"raw_source: {_yaml_value(card.get('raw_source', ''))}",
        *( [f"project_key: {_yaml_value(card['project_key'])}"] if card.get("project_key") else [] ),
        *_yaml_list_block("source_material_ids", list(card.get("source_material_ids") or [])),
        f"source_documents_json: {_yaml_value(reference_json)}",
        f"review_decision: {_yaml_value(card.get('review_decision', 'pending'))}",
        f"candidate_pool_eligible: {_yaml_value(card.get('candidate_pool_eligible', 'false'))}",
        f"missing_items: {_yaml_value(card.get('missing_items', ''))}",
        *( [f"card_category: {_yaml_value(card['card_category'])}"] if card.get("card_category") else [] ),
    ]
    if card.get("batch_scale_card"):
        lines.append("batch_scale_card: \"true\"")
    return "\n".join(lines) + "\n"


def _load_progress(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_progress(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def _llm_cards(
    cluster: batch_extract.ProjectCluster,
    selected: list[batch_extract.CollectedDocument],
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout: float,
) -> list[dict]:
    from tools.infra.llm.client import LLMClient

    prompt = batch_extract.build_extraction_prompt(cluster, selected)
    client = LLMClient(base_url=base_url, api_key=api_key, timeout=timeout)
    response = client.post_json(
        client.chat_completions_url,
        {
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return batch_extract.parse_extraction_response(client.extract_content(response))


def _apply_llm_facts(
    cards: list[dict],
    selected: list[batch_extract.CollectedDocument],
    cluster: batch_extract.ProjectCluster,
) -> tuple[list[dict], list[str]]:
    """校验 LLM 事实：逐条核对原文，剔除无法定位的条目。"""
    source_text = "\n\n".join(doc.text for doc in selected)
    verified: list[dict] = []
    rejections: list[str] = []
    for card in cards:
        missing = batch_extract.verify_card_against_sources(card, source_text)
        if missing:
            rejections.extend(missing)
            card = {
                **card,
                "actions": [value for value in card["actions"] if value not in missing],
                "results": [value for value in card["results"] if value not in missing],
            }
        if not card["actions"] and not card["results"]:
            continue
        verified.append(card)
    return verified, rejections


def _material_records(materials_dir: Path, material_id: str) -> list[dict]:
    meta = parse_simple_yaml((materials_dir / f"{material_id}.meta.yaml").read_text(encoding="utf-8"))
    filename = str(meta["scalars"].get("filename") or "")
    return [{"material_id": material_id, "path": materials_dir / filename, "filename": filename}]


def _rebind_sources(
    materials_dir: Path,
    output_dir: Path,
    material_id: str,
    *,
    min_documents: int,
    max_docs: int,
) -> int:
    """给缺来源绑定的批量卡回填代表文档引用。

    LLM 卡的来源与规则卡相同：该簇被选中的代表文档。回填后仍要能通过
    `read_source_documents` 的 document_id/sha256 校验才算数。
    """
    import yaml

    try:
        material_path = _read_material_path(materials_dir, material_id)
    except ValueError as exc:
        print(f"[extract-batch] {exc}")
        return 1
    clusters = batch_extract.cluster_by_project(
        batch_extract.collect_documents(material_path), min_documents=min_documents
    )
    records = _material_records(materials_dir, material_id)
    rebound = 0
    for cluster in clusters:
        base_id = _card_id(cluster.key)
        candidates = sorted(output_dir.glob(f"{base_id}*.yaml"))
        if not candidates:
            continue
        selected = batch_extract.select_representative(cluster, max_docs=max_docs)
        references = [
            {
                "document_id": doc.document_id,
                "sha256": doc.sha256,
                "label": doc.label,
                "material_id": material_id,
            }
            for doc in selected
        ]
        for path in candidates:
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(data, dict):
                continue
            if json.loads(data.get("source_documents_json") or "[]"):
                continue
            data["source_documents_json"] = json.dumps(references, ensure_ascii=False)
            if not data.get("artifacts"):
                data["artifacts"] = [material_id]
            _documents, source_text = read_source_documents(records, references)
            if data.get("batch_scale_card") != "true":
                unverified = batch_extract.verify_card_against_sources(data, source_text)
                if unverified:
                    data["missing_items"] = (
                        str(data.get("missing_items") or "")
                        + f"；回填后仍有 {len(unverified)} 条事实无法定位"
                    )
                    data["tags"] = [*list(data.get("tags") or []), "存在不可核验事实"]
            path.write_text(dump_card(data), encoding="utf-8")
            rebound += 1
    print(f"[extract-batch] 来源回填完成：{rebound} 张卡已绑定代表文档")
    return 0


APPROVE_MIN_RESULTS = 1


def _approve_batch(
    materials_dir: Path,
    output_dir: Path,
    material_id: str,
    *,
    now: str,
) -> int:
    """批量入池的唯一入口：按宪法第 1 条硬门槛逐卡校验。

    门槛：有 title、有 results、有 artifacts、来源绑定可校验。
    任一不满足即拒绝入池并说明原因，不做"先入池再补救"。
    """
    import yaml

    try:
        material_path = _read_material_path(materials_dir, material_id)
    except ValueError as exc:
        print(f"[extract-batch] {exc}")
        return 1
    records = _material_records(materials_dir, material_id)
    progress = _load_progress(DEFAULT_PROGRESS_DIR / f"{material_id}.json")
    cards = set()
    for state in (progress.get("clusters") or {}).values():
        cards.update(state.get("cards") or [])
        if state.get("card"):
            cards.add(state["card"])

    approved: list[str] = []
    rejected: list[tuple[str, str]] = []
    for card_id in sorted(cards):
        path = output_dir / f"{card_id}.yaml"
        if not path.is_file():
            rejected.append((card_id, "card_file_missing"))
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            rejected.append((card_id, "card_unreadable"))
            continue
        if not isinstance(data, dict):
            rejected.append((card_id, "card_invalid"))
            continue
        if data.get("status") == "saved_eligible":
            continue
        references = json.loads(data.get("source_documents_json") or "[]")
        source_ok = False
        if references:
            try:
                _documents, _text = read_source_documents(records, references)
                source_ok = True
            except ValueError:
                source_ok = False
        reason = batch_extract.pool_approval_reason(data, source_verifiable=source_ok)
        if reason:
            rejected.append((card_id, reason))
            continue
        data["status"] = "saved_eligible"
        data["candidate_pool_eligible"] = "true"
        data["review_decision"] = "approved"
        data["reviewed_at"] = now
        data["review_authorized_by"] = f"user_batch_authorization:{material_id}"
        path.write_text(dump_card(data), encoding="utf-8")
        approved.append(card_id)

    print(f"[extract-batch] 入池通过 {len(approved)} 张，拒绝 {len(rejected)} 张")
    for card_id, reason in rejected:
        print(f"  - 拒绝 {card_id}: {reason}")
    return 0 if not rejected else 1


def _backfill_project_keys(progress_path: Path, output_dir: Path) -> int:
    """按进度记录把 card → 项目簇 写回卡上，供生成阶段合并同一项目的多张卡。"""
    import yaml

    progress = _load_progress(progress_path)
    mapping: dict[str, str] = {}
    for key, state in (progress.get("clusters") or {}).items():
        cards = state.get("cards") or ([state["card"]] if state.get("card") else [])
        for card_id in cards:
            mapping[str(card_id)] = key
    changed = 0
    for card_id, cluster_key in mapping.items():
        path = output_dir / f"{card_id}.yaml"
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or data.get("project_key"):
            continue
        data["project_key"] = cluster_key
        path.write_text(dump_card(data), encoding="utf-8")
        changed += 1
    print(f"[extract-batch] project_key 回填：{changed} 张卡")
    return changed


def _backfill_categories(output_dir: Path) -> int:
    """回填卡分类（project/operation/activity），供生成阶段排除活动类。"""
    import yaml

    changed = 0
    for path in sorted(output_dir.glob("ec_batch_*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict) or data.get("card_category"):
            continue
        data["card_category"] = batch_extract.classify_card_category(
            str(data.get("title") or ""), data.get("actions") or []
        )
        path.write_text(dump_card(data), encoding="utf-8")
        changed += 1
    print(f"[extract-batch] 卡分类回填：{changed} 张")
    return changed


def _normalize_existing(output_dir: Path) -> int:
    """后处理已落盘的批量卡：时间统一到年月、"预计/计划"结果单列。

    PyYAML 在 App/打包环境可能缺失，这里延迟导入，保证 CLI 入口本身可导入。
    """
    import yaml

    changed = 0
    for path in sorted(output_dir.glob("ec_batch_*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        updated = dict(data)
        normalized = batch_extract.normalize_period(str(data.get("time_range") or ""))
        updated["time_range"] = normalized
        verified, planned = batch_extract.split_planned_results(data.get("results") or [])
        if planned:
            updated["results"] = verified
            updated["planned_results"] = planned
        if updated != data:
            path.write_text(dump_card(updated), encoding="utf-8")
            changed += 1
    print(f"[extract-batch] 规范化完成：{changed} 张卡已更新")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批量提炼证据卡（项目聚类）")
    _ = parser.add_argument("--material-id", required=True)
    _ = parser.add_argument("--materials-dir", default=str(DEFAULT_MATERIALS_DIR))
    _ = parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    _ = parser.add_argument("--min-documents", type=int, default=2)
    _ = parser.add_argument("--max-clusters", type=int, default=0, help="0 表示全部")
    _ = parser.add_argument("--max-docs", type=int, default=5)
    _ = parser.add_argument("--use-llm", action="store_true")
    _ = parser.add_argument("--require-llm", action="store_true")
    _ = parser.add_argument("--dry-run", action="store_true")
    _ = parser.add_argument(
        "--exclude-clusters",
        default="",
        help="逗号分隔的项目簇名，匹配到的簇不参与提炼（如 assets）",
    )
    _ = parser.add_argument("--force", action="store_true", help="忽略进度记录重新处理")
    _ = parser.add_argument(
        "--rebind-sources",
        action="store_true",
        help="为缺少 source_documents_json 的已落盘批量卡回填代表文档绑定（不调用模型）",
    )
    _ = parser.add_argument(
        "--approve-batch",
        action="store_true",
        help="按入池硬门槛批量审核：results/artifacts/来源必须齐备，否则拒绝入池",
    )
    _ = parser.add_argument(
        "--repair",
        action="store_true",
        help="统一后处理：回填来源绑定与 project_key、规范化时间与计划值（不调用模型）",
    )
    _ = parser.add_argument(
        "--normalize-existing",
        action="store_true",
        help="只规范化已落盘的 ec_batch_* 卡（时间精度、计划值分离），不调用模型",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    material_id = cast(str, args.material_id)
    if cast(bool, args.normalize_existing):
        return _normalize_existing(Path(cast(str, args.output_dir)))
    if cast(bool, args.approve_batch):
        return _approve_batch(
            Path(cast(str, args.materials_dir)),
            Path(cast(str, args.output_dir)),
            material_id,
            now=datetime.datetime.now(datetime.timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        )
    if cast(bool, args.repair):
        repair_progress = DEFAULT_PROGRESS_DIR / f"{material_id}.json"
        code = _rebind_sources(
            Path(cast(str, args.materials_dir)),
            Path(cast(str, args.output_dir)),
            material_id,
            min_documents=cast(int, args.min_documents),
            max_docs=cast(int, args.max_docs),
        )
        if code != 0:
            return code
        _backfill_project_keys(repair_progress, Path(cast(str, args.output_dir)))
        _backfill_categories(Path(cast(str, args.output_dir)))
        return _normalize_existing(Path(cast(str, args.output_dir)))
    if cast(bool, args.rebind_sources):
        return _rebind_sources(
            Path(cast(str, args.materials_dir)),
            Path(cast(str, args.output_dir)),
            material_id,
            min_documents=cast(int, args.min_documents),
            max_docs=cast(int, args.max_docs),
        )
    materials_dir = Path(cast(str, args.materials_dir))
    output_dir = Path(cast(str, args.output_dir))

    try:
        material_path = _read_material_path(materials_dir, material_id)
    except ValueError as exc:
        print(f"[extract-batch] {exc}")
        return 1

    documents = batch_extract.collect_documents(material_path)
    clusters = batch_extract.cluster_by_project(documents, min_documents=cast(int, args.min_documents))
    clusters = batch_extract.exclude_clusters(
        clusters,
        [name for name in str(cast(str, args.exclude_clusters) or "").split(",") if name.strip()],
    )
    if cast(int, args.max_clusters) > 0:
        clusters = clusters[: cast(int, args.max_clusters)]
    print(f"[extract-batch] 材料 {material_id}: {len(documents)} 篇文档 / {len(clusters)} 个项目簇")

    if cast(bool, args.dry_run):
        for cluster in clusters:
            selected = batch_extract.select_representative(cluster, max_docs=cast(int, args.max_docs))
            print(f"  - {cluster.key}: {cluster.document_count} 篇 / 代表 {len(selected)} 篇")
        return 0

    use_llm = cast(bool, args.use_llm)
    if cast(bool, args.require_llm) and not use_llm:
        print("[extract-batch] --require-llm 需要同时传 --use-llm")
        return 1
    model = os.getenv("LLM_MODEL", "")
    base_url = os.getenv("LLM_BASE_URL", "")
    api_key = os.getenv("LLM_API_KEY", "")
    timeout = float(os.getenv("LLM_TIMEOUT", "600"))
    if use_llm:
        from tools.infra.llm.client import llm_request_available

        if not llm_request_available(provider=os.getenv("LLM_PROVIDER", ""), api_key=api_key, model=model, base_url=base_url):
            print("[extract-batch] LLM 配置不可用（provider/model/key）；可用 --dry-run 或规则模式。")
            return 1

    progress_path = DEFAULT_PROGRESS_DIR / f"{material_id}.json"
    progress = _load_progress(progress_path)
    progress.setdefault("material_id", material_id)
    progress.setdefault("clusters", {})
    if cast(bool, args.force):
        progress["clusters"] = {}

    records = _material_records(materials_dir, material_id)
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    written = 0
    failed = 0
    for cluster in clusters:
        state = progress["clusters"].get(cluster.key, {})
        if state.get("status") == "done":
            continue
        selected = batch_extract.select_representative(cluster, max_docs=cast(int, args.max_docs))
        if not selected:
            progress["clusters"][cluster.key] = {"status": "skipped", "reason": "no_representative_document"}
            continue
        card_id = _card_id(cluster.key)
        cards: list[dict] = []
        rejections: list[str] = []
        if use_llm:
            try:
                raw_cards = _llm_cards(
                    cluster,
                    selected,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    timeout=timeout,
                )
                cards, rejections = _apply_llm_facts(raw_cards, selected, cluster)
            except (ValueError, OSError, RuntimeError, KeyError) as exc:
                progress["clusters"][cluster.key] = {"status": "failed", "reason": str(exc)[:160]}
                failed += 1
                continue
        inferred_period = batch_extract.infer_period(cluster.documents)
        if not cards:
            cards = [
                batch_extract.build_scale_card(
                    cluster,
                    selected,
                    material_id=material_id,
                    card_id=card_id,
                    raw_source=f"materials:{material_id}",
                    now=now,
                )
            ]
        else:
            # LLM 卡常缺时间：用同一簇文档里真实出现的日期补，并在卡上标注推断来源。
            for card in cards:
                if not card.get("time_range") and inferred_period:
                    card["time_range"] = inferred_period
                    card["time_source"] = "document_dates_pending_confirmation"
        for card in cards:
            card["time_range"] = batch_extract.normalize_period(card.get("time_range", ""))
            verified, planned = batch_extract.split_planned_results(card.get("results") or [])
            if planned:
                card["results"] = verified
                card["planned_results"] = planned
        written_ids: list[str] = []
        cluster_failed = False
        for index, payload in enumerate(cards):
            payload_id = card_id if index == 0 else f"{card_id}_{index + 1}"
            payload.setdefault("id", payload_id)
            payload.setdefault("raw_source", f"materials:{material_id}")
            payload.setdefault(
                "source_documents_json",
                json.dumps(
                    [
                        {
                            "document_id": doc.document_id,
                            "sha256": doc.sha256,
                            "label": doc.label,
                            "material_id": material_id,
                        }
                        for doc in selected
                    ],
                    ensure_ascii=False,
                ),
            )
            payload.setdefault("source_material_ids", [material_id])
            payload.setdefault("created_at", now)
            payload.setdefault("updated_at", now)
            payload.setdefault("status", "draft")
            payload.setdefault("review_decision", "pending")
            payload.setdefault("candidate_pool_eligible", "false")
            payload.setdefault("artifacts", [material_id])
            payload.setdefault("tags", ["批量提炼", cluster.key])
            payload.setdefault(
                "missing_items",
                "本人职责、任职时间与量化成果待用户确认"
                + (f"；被剔除的不可核验事实 {len(rejections)} 条" if rejections else ""),
            )
            if rejections:
                payload["tags"] = [*payload["tags"], "存在被剔除事实"]
            try:
                references = json.loads(payload.get("source_documents_json") or "[]")
                if references:
                    _documents, source_text = read_source_documents(records, references)
                    # 规模卡写的是目录统计（元事实），不对应原文句子；LLM 卡必须逐条可定位。
                    if payload.get("batch_scale_card") != "true":
                        unverified = batch_extract.verify_card_against_sources(payload, source_text)
                        if unverified:
                            raise ValueError("batch_extract_unverified_facts")
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / f"{payload_id}.yaml").write_text(dump_card(payload), encoding="utf-8")
            except (ValueError, OSError) as exc:
                progress["clusters"][cluster.key] = {"status": "failed", "reason": str(exc)[:160]}
                failed += 1
                cluster_failed = True
                break
            written_ids.append(payload_id)
        if cluster_failed:
            continue
        progress["clusters"][cluster.key] = {
            "status": "done",
            "cards": written_ids,
            "card": written_ids[0] if written_ids else "",
            "rejected": len(rejections),
        }
        written += len(written_ids)
        print(
            f"  + {cluster.key}: {', '.join(written_ids)} "
            f"({cluster.document_count} 篇文档)"
        )
        _save_progress(progress_path, progress)

    progress["finished_at"] = now
    progress["written"] = progress.get("written", 0) + written
    progress["failed"] = failed
    _save_progress(progress_path, progress)
    print(f"[extract-batch] 完成：写入 {written} 张草稿卡，失败 {failed} 个簇；进度 {progress_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
