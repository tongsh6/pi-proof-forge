"""审批前固定简历与岗位；恢复执行只读取、校验快照。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from typing import Any


_IDENTITY_FIELDS = (
    'job_lead_id', 'company', 'position', 'resume_version', 'job_url', 'platform',
    'platform_job_id', 'platform_job_type', 'job_profile_id', 'jd_status',
    'source_jd_sha256', 'source', 'legal_entity',
)


def _render_pdf(source: Path, destination: Path) -> None:
    from tools.infra.export.pdf_exporter import markdown_to_pdf
    markdown_to_pdf(source, destination)


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identity(candidate: dict) -> dict:
    fields = {key: candidate.get(key, '') for key in _IDENTITY_FIELDS}
    for key in ('delivery_kind', 'platform_resume_sha256', 'content_basis', 'career_revision', 'content_schema_version', 'pdf_filename'):
        if key in candidate:
            fields[key] = candidate[key]
    return fields


class ReviewSnapshotStore:
    def __init__(self, root: Path = Path('outputs/agent_runs')) -> None:
        self.root = root.resolve()

    def _base(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', run_id):
            raise ValueError('review_snapshot_invalid_run')
        base = self.root / run_id / 'review_snapshots'
        if not base.resolve().is_relative_to(self.root):
            raise ValueError('review_snapshot_invalid_path')
        return base

    def create(self, run_id: str, candidate: dict, content: str, *, dry_run: bool, pdf_content: bytes | None = None) -> dict:
        if not content.strip() or type(dry_run) is not bool:
            raise ValueError('review_snapshot_invalid_input')
        snapshot_id = uuid4().hex
        directory = self._base(run_id) / snapshot_id
        try:
            directory.mkdir(parents=True, mode=0o700)
            directory.chmod(0o700)
            md, pdf = directory / 'resume.md', directory / 'resume.pdf'
            md.write_text(content, encoding='utf-8')
            platform_default = candidate.get('delivery_kind') == 'platform_default'
            if platform_default:
                if candidate.get('platform_resume_sha256') != _digest(md.read_bytes()):
                    raise ValueError('platform resume changed')
            else:
                if pdf_content is not None:
                    if (not isinstance(pdf_content, bytes) or len(pdf_content) > 10_000_000
                            or not pdf_content.startswith(b'%PDF-') or not pdf_content.rstrip().endswith(b'%%EOF')):
                        raise ValueError('invalid pdf')
                    pdf.write_bytes(pdf_content)
                else:
                    _render_pdf(md, pdf)
                if not pdf.read_bytes().startswith(b'%PDF-'):
                    raise ValueError('invalid pdf')
            manifest = {
                'run_id': run_id, 'candidate': _identity(candidate), 'dry_run': dry_run,
                'markdown_sha256': _digest(md.read_bytes()), 'pdf_sha256': '' if platform_default else _digest(pdf.read_bytes()),
            }
            encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode('utf-8')
            manifest_path = directory / 'manifest.json'
            manifest_path.write_bytes(encoded)
            for path in ((md, manifest_path) if platform_default else (md, pdf, manifest_path)):
                path.chmod(0o444)
            return {'id': snapshot_id, 'sha256': _digest(encoded)}
        except (OSError, RuntimeError, ValueError):
            shutil.rmtree(directory, ignore_errors=True)
        raise ValueError('review_snapshot_export_failed')

    def load(self, run_id: str, candidate: dict) -> dict:
        try:
            ref = candidate['snapshot']
            if not isinstance(ref, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(ref.get('id', ''))):
                raise ValueError('invalid reference')
            directory = self._base(run_id) / ref['id']
            if directory.is_symlink() or not directory.resolve().is_relative_to(self.root):
                raise ValueError('invalid path')
            contents = {}
            platform_default = candidate.get('delivery_kind') == 'platform_default'
            files = [('manifest.json', 65536), ('resume.md', 2_000_000)]
            if not platform_default:
                files.append(('resume.pdf', 10_000_000))
            for name, maximum in files:
                path = directory / name
                if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
                    raise ValueError('invalid artifact')
                contents[name] = path.read_bytes()
            if _digest(contents['manifest.json']) != ref.get('sha256'):
                raise ValueError('manifest changed')
            manifest = json.loads(contents['manifest.json'])
            if (manifest.get('run_id') != run_id or manifest.get('candidate') != _identity(candidate)
                    or type(manifest.get('dry_run')) is not bool
                    or _digest(contents['resume.md']) != manifest.get('markdown_sha256')
                    or (platform_default and (manifest.get('pdf_sha256') != '' or
                        candidate.get('platform_resume_sha256') != manifest.get('markdown_sha256')))
                    or (not platform_default and (_digest(contents['resume.pdf']) != manifest.get('pdf_sha256')
                        or not contents['resume.pdf'].startswith(b'%PDF-')))):
                raise ValueError('snapshot changed')
            return {**manifest, 'resume_markdown': contents['resume.md'].decode('utf-8'),
                    'resume_path': '' if platform_default else str(directory / 'resume.pdf'),
                    'resume_markdown_path': str(directory / 'resume.md')}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        raise ValueError('review_snapshot_invalid')


def read_generation_trace(resume_path: Path) -> tuple[dict[str, Any], bool]:
    """读取独立追溯，核对正文与输入指纹；旧正文内的 ID 不作为证明。"""
    trace: dict[str, Any] = {}
    try:
        loaded = json.loads(resume_path.with_suffix(".trace.json").read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return {}, False
        trace = loaded
        text = resume_path.read_text(encoding="utf-8")
        if trace.get("schema_version") != 1 or trace.get("resume_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest():
            return trace, False
        if re.search(r"Evidence trace|Source report|Resume Version|(?:/Users/|/private/|/tmp/)|\bec[-_][\w-]+", text, re.I):
            return trace, False
        ids = trace.get("evidence_card_ids")
        inputs = trace.get("inputs")
        claims = trace.get("claims")
        if not isinstance(ids, list) or not ids or not all(isinstance(item, str) for item in ids):
            return trace, False
        if not isinstance(inputs, dict) or not set(ids).issubset(inputs) or not isinstance(claims, list) or not claims:
            return trace, False
        for source in inputs.values():
            if not isinstance(source, dict) or not source.get("exists"):
                return trace, False
            path = Path(source["path"])
            if source.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
                return trace, False
        for claim in claims:
            if not isinstance(claim, dict) or not claim.get("text") or claim["text"] not in text:
                return trace, False
            if claim.get("source_kind") == "evidence" and claim.get("evidence_id") not in ids:
                return trace, False
        return trace, True
    except (OSError, ValueError, KeyError, TypeError):
        return trace, False
