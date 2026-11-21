"""同一卡片的精确文档引用与字段补证；复用材料文件，不建立第二份事实库。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from tools.infra.material_documents import split_material_documents

SOURCE_FIELDS = ('time_range', 'role_scope', 'context', 'actions', 'results')


def field_values(fields, field):
    value = fields.get(field, '')
    if isinstance(value, list):
        return value
    return [line.strip() for line in value.splitlines() if line.strip()] if field in {'actions', 'results'} else [value.strip()] if value.strip() else []


def exact_document_groups(material_ids, references, whole_ids):
    """An all-exact source set is eligible for the narrow document validation path."""
    if not isinstance(whole_ids, list) or any(mid not in material_ids for mid in whole_ids):
        raise ValueError("material_document_reference_invalid")
    if not isinstance(references, list) or len(references) > 8:
        raise ValueError("material_document_reference_invalid")
    groups, keys = {}, set()
    for ref in references:
        if (not isinstance(ref, dict) or ref.get("material_id") not in material_ids
                or any(not isinstance(ref.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}",ref[k])
                       for k in ("document_id","sha256"))):
            raise ValueError("material_document_reference_invalid")
        key = (ref["material_id"],ref["document_id"])
        if key in keys:
            raise ValueError("material_document_reference_invalid")
        groups.setdefault(key[0], []).append(ref)
        keys.add(key)
    return groups if groups and not whole_ids and set(groups) == set(material_ids) and len(set(material_ids)) == len(material_ids) else {}


def assert_source_snapshot(snapshots):
    for key, (path, expected) in snapshots.items():
        escaped = not key.startswith("evidence_material:") and path.resolve() != path.absolute()
        if escaped or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("material_source_changed")


def read_source_documents(records, references, whole_material_ids=(), *, results=()):
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
        if 'verified_documents' in record:
            text = record['verified_documents'].get(key[1])
            if text is None or hashlib.sha256(text.encode()).hexdigest() != ref.get('sha256'):
                raise ValueError('material_document_changed_or_missing')
        else:
            matches = [d for d in split_material_documents(path.read_text(encoding='utf-8'), path.name) if d['document_id'] == key[1]]
            if len(matches) != 1 or matches[0]['sha256'] != ref.get('sha256'):
                raise ValueError('material_document_changed_or_missing')
            text = matches[0]['text']
        documents[key] = text; selected.add(key[0])
    # 兼容旧卡绑定整份材料；有精确引用的材料仅允许所选片段。
    texts = [*documents.values(), *(r['path'].read_text(encoding='utf-8') for r in records if r['material_id'] not in selected or r['material_id'] in whole_material_ids)]
    # 完整结果须来自一个授权原文单元，不能跨拼接边界借证。
    for result in results:
        if not any(result.casefold() in text.casefold() for text in texts):
            raise ValueError('no_fabrication_guard: result is not traceable to selected document')
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


class ValidatedSourcePaths(dict):
    """Path mapping with hashes captured from the bytes actually validated."""

    def __init__(self, snapshots=(), *, documents=None):
        self.snapshots = dict(snapshots)
        self.documents = documents if documents is not None else {}
        super().__init__((key,path) for key,(path,_) in self.snapshots.items())


def assert_captured_source(sources, key, digest):
    expected = getattr(sources, "snapshots", {}).get(key)
    if expected is not None:
        path, sha = expected
        escaped = not key.startswith("evidence_material:") and path.resolve() != path.absolute()
        if escaped or path.is_symlink() or digest != sha:
            raise ValueError("material_source_changed")


def validated_source_inputs(doc, material_dir: Path):
    """Revalidate existing source bindings and return original paths with captured hashes."""
    s = doc['scalars']; raw = s.get('source_material_fingerprints_json')
    if not raw:
        if s.get('field_sources_json'):
            raise ValueError('field_source_fingerprints_missing')
        return ValidatedSourcePaths()
    try:
        from tools.infra import referenced_materials as rm
        from tools.infra.persistence.yaml_io import parse_simple_yaml
        from tools.policy.exclusions import load_material_source_roots

        fingerprints = json.loads(raw)
        refs = json.loads(s.get('source_documents_json') or '[]')
        whole = json.loads(s.get('source_whole_material_ids_json') or '[]')
        mids = doc['lists'].get('source_material_ids', [])
        bindings = json.loads(s.get('field_sources_json') or '[]')
        if not isinstance(fingerprints, dict) or set(fingerprints) != set(mids):
            raise ValueError('material_source_changed')
        groups = exact_document_groups(mids, refs, whole)
        snapshots, records = {}, []
        for mid in mids if groups else fingerprints:
            data = fingerprints.get(mid)
            item = None
            if mid in groups:
                if not re.fullmatch(r'[A-Za-z0-9_-]+', mid):
                    raise ValueError('material_source_changed')
                meta = material_dir / (mid + '.meta.yaml')
                if meta.is_symlink():
                    raise ValueError('material_source_changed')
                if meta.is_file():
                    item = parse_simple_yaml(meta.read_text(encoding='utf-8'))['scalars']
                    if item.get('material_id') != mid:
                        raise ValueError('material_source_changed')
                if item and item.get('source_mode') == 'referenced':
                    cache, docs, exact = rm.verify_bound_documents(
                        material_dir,item,groups[mid],load_material_source_roots(),fingerprint=data)
                    snapshots.update(exact)
                    records.append({'material_id':mid,'path':cache,'verified_documents':docs})
                    continue
                if data and data.get('mode') == 'referenced':
                    raise ValueError('material_source_changed')
            filename = str(data.get('filename') or ''); raw_path = Path(filename)
            path = material_dir / filename
            if (not filename or raw_path.is_absolute() or path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(material_dir.resolve())):
                raise ValueError('material_source_changed')
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != data.get('sha256'):
                raise ValueError('material_source_changed')
            if data.get('mode') == 'referenced':
                manifest_path = material_dir / '.referenced' / f'{mid}.manifest.json'
                if not manifest_path.is_file():
                    raise ValueError('material_source_changed')
                manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                if manifest.get('manifest_sha256') != data.get('manifest_sha256'):
                    raise ValueError('material_source_changed')
                target = Path(str(data.get('source_root') or '')) / str(data.get('source_relpath') or '')
                rm.resolve_under_roots(target,load_material_source_roots())
                if rm.verify_manifest(target, manifest).get('status') != 'ok':
                    raise ValueError('material_source_changed')
            records.append({'material_id':mid,'path':path})
            snapshots[f'evidence_material:{mid}'] = (path,digest)
        documents, _ = read_source_documents(records, refs, whole)
        validate_field_sources({**s, **doc['lists']}, bindings, documents)
        assert_source_snapshot(snapshots)
        return ValidatedSourcePaths(snapshots, documents=documents)
    except (KeyError,TypeError,OSError,UnicodeError,ValueError,AttributeError) as exc:
        raise ValueError(f'material_source_changed_or_invalid:{type(exc).__name__}:{str(exc)[:160]}') from exc
