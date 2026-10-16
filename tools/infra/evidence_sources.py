"""同一卡片的精确文档引用与字段补证；复用材料文件，不建立第二份事实库。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tools.infra.material_documents import split_material_documents

SOURCE_FIELDS = ('time_range', 'role_scope', 'context', 'actions', 'results')


def field_values(fields, field):
    value = fields.get(field, '')
    if isinstance(value, list):
        return value
    return [line.strip() for line in value.splitlines() if line.strip()] if field in {'actions', 'results'} else [value.strip()] if value.strip() else []


def read_source_documents(records, references, whole_material_ids=()):
    if not isinstance(references, list) or len(references) > 8:
        raise ValueError('material_document_reference_invalid')
    by_id = {r['material_id']: r for r in records}
    documents = {}; selected = set()
    for ref in references:
        if not isinstance(ref, dict) or ref.get('material_id') not in by_id:
            raise ValueError('material_document_reference_invalid')
        key = (ref['material_id'], ref.get('document_id'))
        if key in documents:
            raise ValueError('material_document_reference_invalid')
        record = by_id[key[0]]; path = record['path']
        matches = [d for d in split_material_documents(path.read_text(encoding='utf-8'), path.name) if d['document_id'] == key[1]]
        if len(matches) != 1 or matches[0]['sha256'] != ref.get('sha256'):
            raise ValueError('material_document_changed_or_missing')
        documents[key] = matches[0]['text']; selected.add(key[0])
    # 兼容旧卡绑定整份材料；有精确引用的材料仅允许所选片段。
    texts = [*documents.values(), *(r['path'].read_text(encoding='utf-8') for r in records if r['material_id'] not in selected or r['material_id'] in whole_material_ids)]
    return documents, '\n\n'.join(texts)


def validate_field_sources(fields, bindings, documents):
    if not isinstance(bindings, list) or len(bindings) > 80:
        raise ValueError('field_source_invalid')
    verified = set()
    for binding in bindings:
        if not isinstance(binding, dict) or any(not isinstance(binding.get(k), str) or not binding[k].strip()
                                               for k in ('field', 'value', 'quote', 'material_id', 'document_id')):
            raise ValueError('field_source_invalid')
        field, value, quote = (binding[k] for k in ('field', 'value', 'quote'))
        source = documents.get((binding['material_id'], binding['document_id']), '')
        if (field not in SOURCE_FIELDS or value not in field_values(fields, field)
                or value not in quote or quote not in source):
            raise ValueError('field_source_not_traceable')
        verified.add((field, value))
    return verified


def source_fingerprints(records):
    out = {}
    for r in records:
        filename = str(r.get("filename") or r["path"].name)
        entry = {"filename": filename, "sha256": hashlib.sha256(r["path"].read_bytes()).hexdigest()}
        if r.get("source_mode") == "referenced":
            entry.update({"mode": "referenced",
                          "manifest_sha256": str(r.get("manifest_sha256") or ""),
                          "source_root": str(r.get("source_root") or ""),
                          "source_relpath": str(r.get("source_relpath") or "")})
        out[r["material_id"]] = entry
    return out


def validated_source_inputs(doc, material_dir: Path):
    """补证卡须重验材料字节和字段引用；返回可纳入缓存/trace 的输入路径。"""
    s = doc['scalars']; raw = s.get('source_material_fingerprints_json')
    if not raw:
        if s.get('field_sources_json'):
            raise ValueError('field_source_fingerprints_missing')
        return {}
    try:
        fingerprints = json.loads(raw); refs = json.loads(s.get('source_documents_json') or '[]')
        bindings = json.loads(s.get('field_sources_json') or '[]')
        if not isinstance(fingerprints, dict) or set(fingerprints) != set(doc['lists'].get('source_material_ids', [])):
            raise ValueError('material_source_changed')
        records = []
        for mid, data in fingerprints.items():
            filename = str(data.get('filename') or ''); raw_path = Path(filename)
            path = material_dir / filename
            if (not filename or raw_path.is_absolute() or path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(material_dir.resolve())
                    or hashlib.sha256(path.read_bytes()).hexdigest() != data.get('sha256')):
                raise ValueError('material_source_changed')
            if data.get('mode') == 'referenced':
                # 引用材料：先验允许根，再重验清单与源文件哈希，最后核对缓存字节
                manifest_path = material_dir / '.referenced' / f'{mid}.manifest.json'
                if not manifest_path.is_file():
                    raise ValueError('material_source_changed')
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                if manifest.get('manifest_sha256') != data.get('manifest_sha256'):
                    raise ValueError('material_source_changed')
                from tools.infra import referenced_materials as rm
                from tools.policy.exclusions import load_material_source_roots
                target = Path(str(data.get('source_root') or '')) / str(data.get('source_relpath') or '')
                try:
                    rm.resolve_under_roots(target, load_material_source_roots())
                except ValueError as exc:
                    raise ValueError('material_source_changed') from exc
                if rm.verify_manifest(target, manifest).get('status') != 'ok':
                    raise ValueError('material_source_changed')
            records.append({'material_id': mid, 'path': path})
        documents, _ = read_source_documents(records, refs)
        validate_field_sources({**s, **doc['lists']}, bindings, documents)
        return {f'evidence_material:{r["material_id"]}': r['path'] for r in records}
    except (KeyError, TypeError, OSError, UnicodeError, ValueError) as exc:
        raise ValueError('material_source_changed_or_invalid') from exc
