"""白名单来源目录的导航盘点；附件只登记元信息，不进入正文或事实池。"""
from __future__ import annotations

import hashlib
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.infra.material_documents import material_document_skip_reason, split_material_documents
from tools.infra.referenced_materials import ALLOWED_SUFFIXES, is_sensitive_name
from tools.policy.exclusions import load_material_source_roots, resolve_policy_path

ATTACHMENT_SUFFIXES = {
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.pps', '.ppsx', '.xls', '.xlsx',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.tif', '.tiff',
}
LFS_HEADER = b'version https://git-lfs.github.com/spec/v1\n'


def _references_by_path(materials: dict, roots: list[dict]) -> dict[str, list[dict]]:
    references = defaultdict(list)
    allowed = [Path(item['path']).resolve() for item in roots]
    for material_id, material in materials.items():
        if material.get('source_mode') == 'referenced':
            base = Path(material['source_root']) / material['source_relpath']
        elif material.get('source_path') and not material['source_path'].startswith('uploaded_file:'):
            base = Path(material['source_path'])
        else:
            continue
        direct = base.is_absolute() and any(base.resolve().is_relative_to(r) for r in allowed)
        for doc in material['documents']:
            source = doc.get('source_name', doc['label'])
            if direct:
                paths = [base / source] if material['kind'] == 'raw_work_material_directory' else [base]
            else:
                # 历史策展包保留根内相对路径；仍须按正文指纹确认，不能仅凭同名认定覆盖。
                relative = Path(source)
                if relative.is_absolute() or '..' in relative.parts:
                    continue
                paths = [r / relative for r in allowed]
            for path in paths:
                references[str(path.resolve())].append({
                    'material_id': material_id, 'document_id': doc['document_id'], 'sha256': doc['sha256'],
                })
    return references


def build_source_coverage(root: Path, materials: dict[str, Any]) -> dict[str, Any]:
    """盘点配置根，目录/附件只读；读取失败保留明确错误，不影响其他根。"""
    roots = sorted(load_material_source_roots(resolve_policy_path(root)), key=lambda x: (x['id'], x['path']))
    refs = _references_by_path(materials, roots)
    items: list[dict] = []
    errors: list[dict] = []
    excluded: Counter = Counter()
    for source in roots:
        base = Path(source['path'])
        if base.is_symlink() or not base.is_dir():
            errors.append({'root_id': source['id'], 'path': '.', 'reason': 'source_root_unavailable'})
            continue
        base = base.resolve()

        def walk_error(exc: OSError) -> None:
            filename = Path(exc.filename) if exc.filename else base
            relative = str(filename.relative_to(base)) if filename.is_relative_to(base) else '.'
            errors.append({'root_id': source['id'], 'path': relative, 'reason': type(exc).__name__})

        for directory, dirs, files in os.walk(base, followlinks=False, onerror=walk_error):
            parent = Path(directory)
            kept = []
            for name in sorted(dirs):
                if (parent / name).is_symlink():
                    excluded['symlink'] += 1
                elif name.startswith('.'):
                    excluded['hidden_directory'] += 1
                else:
                    kept.append(name)
            dirs[:] = kept
            for name in sorted(files):
                path = parent / name
                if path.is_symlink():
                    excluded['symlink'] += 1
                    continue
                if name.startswith('.'):
                    excluded['hidden_file'] += 1
                    continue
                if is_sensitive_name(name):
                    excluded['sensitive_name'] += 1
                    continue
                suffix = path.suffix.lower()
                if suffix not in ALLOWED_SUFFIXES | ATTACHMENT_SUFFIXES:
                    excluded['unsupported_suffix'] += 1
                    continue
                relative = path.relative_to(base).as_posix()
                item = {'root_id': source['id'], 'path': relative, 'suffix': suffix,
                        'kind': 'text' if suffix in ALLOWED_SUFFIXES else 'attachment',
                        'status': 'metadata_only', 'availability': 'local', 'references': []}
                try:
                    stat = path.stat()
                    # 不记 mtime：checkout/touch 不改内容时不应触发重建。
                    item.update(bytes=stat.st_size)
                    with path.open('rb') as stream:
                        head = stream.read(256)
                    if head.replace(b'\r\n', b'\n').startswith(LFS_HEADER):
                        item['availability'] = 'lfs_pointer'
                    elif suffix in ALLOWED_SUFFIXES:
                        reason = material_document_skip_reason(relative)
                        if reason or not stat.st_size:
                            item.update(status='filtered', reason=reason or 'empty')
                        else:
                            data = path.read_bytes()
                            # 与材料入口 read_text 的通用换行处理一致。
                            text = data.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
                            item['sha256'] = hashlib.sha256(data).hexdigest()
                            current = [d['sha256'] for d in split_material_documents(text, path.name)]
                            candidates = refs.get(str(path), [])
                            by_material = defaultdict(list)
                            for ref in candidates:
                                by_material[ref['material_id']].append(ref)
                            # 必须有一个完整版本按原顺序覆盖，不能跨快照拼接或忽略分片顺序。
                            complete = [group for group in by_material.values()
                                        if [ref['sha256'] for ref in group] == current]
                            item['references'] = [ref for group in complete for ref in group]
                            if not current:
                                item.update(status='filtered', reason='empty_or_filtered_content')
                            elif complete:
                                item['status'] = 'indexed'
                            else:
                                item['status'] = 'stale' if candidates else 'unindexed'
                except UnicodeError:
                    item.update(status='metadata_only', reason='unsupported_text_encoding')
                except OSError as exc:
                    item.update(status='unavailable', availability='unreadable')
                    errors.append({'root_id': source['id'], 'path': relative, 'reason': type(exc).__name__})
                items.append(item)
    items.sort(key=lambda x: (x['root_id'], x['path']))
    return {'roots': roots, 'items': items, 'counts': dict(Counter(x['status'] for x in items)),
            'excluded_counts': dict(sorted(excluded.items())),
            'errors': sorted(errors, key=lambda x: (x['root_id'], x['path'], x['reason']))}
