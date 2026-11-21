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
    for key in ('delivery_kind', 'platform_resume_sha256', 'content_basis', 'career_revision', 'content_schema_version', 'pdf_filename', 'quality_sha256'):
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

    def create(self, run_id: str, candidate: dict, content: str, *, dry_run: bool,
               pdf_content: bytes | None = None, generation_trace: dict | None = None) -> dict:
        if not content.strip() or type(dry_run) is not bool:
            raise ValueError('review_snapshot_invalid_input')
        trace_bytes = None
        if generation_trace is not None:
            # 捕获同一份标准 trace；导出期间调用方改字典不能替换其来源身份。
            try:
                trace_bytes = json.dumps(generation_trace, ensure_ascii=False, sort_keys=True).encode('utf-8')
                generation_trace = json.loads(trace_bytes)
            except (TypeError, ValueError) as exc:
                raise ValueError('review_snapshot_generation_trace_invalid') from exc
            if not validate_generation_trace(content, generation_trace):
                raise ValueError('review_snapshot_generation_trace_invalid')
        snapshot_id = uuid4().hex
        directory = self._base(run_id) / snapshot_id
        try:
            directory.mkdir(parents=True, mode=0o700)
            directory.chmod(0o700)
            md, pdf = directory / 'resume.md', directory / 'resume.pdf'
            md.write_text(content, encoding='utf-8')
            trace_path = md.with_suffix('.trace.json')
            if trace_bytes is not None:
                trace_path.write_bytes(trace_bytes)
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
            if trace_bytes is not None:
                if (md.read_bytes() != content.encode('utf-8')
                        or trace_path.read_bytes() != trace_bytes
                        or not validate_generation_trace(content, generation_trace)):
                    raise ValueError('review_snapshot_generation_trace_changed')
                manifest['generation_trace_sha256'] = _digest(trace_bytes)
            encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode('utf-8')
            manifest_path = directory / 'manifest.json'
            manifest_path.write_bytes(encoded)
            artifacts = [md, manifest_path] if platform_default else [md, pdf, manifest_path]
            if trace_bytes is not None:
                artifacts.append(trace_path)
            for path in artifacts:
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
            if 'generation_trace_sha256' in manifest:
                trace_path = directory / 'resume.trace.json'
                if (trace_path.is_symlink() or not trace_path.is_file()
                        or trace_path.stat().st_size > 2_000_000):
                    raise ValueError('invalid generation trace')
                trace_bytes = trace_path.read_bytes()
                if (_digest(trace_bytes) != manifest['generation_trace_sha256']
                        or not validate_generation_trace(contents['resume.md'].decode('utf-8'), json.loads(trace_bytes))):
                    raise ValueError('generation trace changed')
            return {**manifest, 'resume_markdown': contents['resume.md'].decode('utf-8'),
                    'resume_path': '' if platform_default else str(directory / 'resume.pdf'),
                    'resume_markdown_path': str(directory / 'resume.md')}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        raise ValueError('review_snapshot_invalid')


def validate_generation_trace(text: str, trace: object) -> bool:
    """内存与文件产物使用同一份正文、事实位置及当前来源校验。"""
    from tools.domain.quality_text import matches_fact_occurrence
    from tools.infra.persistence.yaml_io import parse_simple_yaml

    if not isinstance(text, str) or not isinstance(trace, dict):
        return False
    try:
        if (trace.get("schema_version") != 1 or trace.get("occurrence_lineage_version") != 1
                or trace.get("resume_sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest()):
            return False
        if re.search(r"Evidence trace|Source report|Resume Version|(?:/Users/|/private/|/tmp/)|\bec[-_][\w-]+", text, re.I):
            return False
        ids = trace.get("evidence_card_ids")
        inputs = trace.get("inputs")
        claims = trace.get("claims")
        if not isinstance(ids, list) or not ids or not all(isinstance(item, str) for item in ids):
            return False
        if not isinstance(inputs, dict) or not set(ids).issubset(inputs) or not isinstance(claims, list) or not claims:
            return False
        card_documents = {}
        for key, source in inputs.items():
            if not isinstance(source, dict) or not source.get("exists"):
                return False
            raw = Path(source["path"]).read_bytes()
            if source.get("sha256") != hashlib.sha256(raw).hexdigest():
                return False
            if key in ids:
                card_documents[key] = parse_simple_yaml(raw.decode("utf-8"))
        lines = text.splitlines()
        for claim in claims:
            if not isinstance(claim, dict) or not claim.get("text") or claim["text"] not in text:
                return False
            kind = claim.get("source_kind")
            if kind == "evidence" and claim.get("evidence_id") not in ids:
                return False
            if kind == "evidence" or "fact_id" in claim or "render_line" in claim:
                line = claim.get("render_line")
                if (type(line) is not int or not 1 <= line <= len(lines)
                        or claim["text"] not in lines[line - 1] or kind not in ("evidence", "personal_profile")):
                    return False
                owner = claim.get("evidence_id") if kind == "evidence" else "personal_profile"
                field = claim.get("field")
                if (not owner or not isinstance(field, str) or not field
                        or not re.fullmatch(re.escape(f"{owner}:{field}:") + r"[0-9]+", str(claim.get("fact_id", "")))):
                    return False
                if kind == "evidence":
                    doc = card_documents[owner]
                    values = doc["lists"].get(field)
                    if values is None and field in doc["scalars"]:
                        values = [doc["scalars"][field]]
                    if not matches_fact_occurrence(owner, field, values, claim):
                        return False
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def read_generation_trace(resume_path: Path) -> tuple[dict[str, Any], bool]:
    """读取标准独立追溯；文件和 Agent 内存输出使用同一验证器。"""
    trace: dict[str, Any] = {}
    try:
        loaded = json.loads(resume_path.with_suffix(".trace.json").read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            return {}, False
        trace = loaded
        text = resume_path.read_text(encoding="utf-8")
        return trace, validate_generation_trace(text, trace)
    except (OSError, ValueError, TypeError):
        return trace, False
