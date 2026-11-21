"""PDF 产物与质量快照的本地文件校验（跨 handler 共享）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.sidecar.handlers._shared import agent_state


def local_file(value, suffix):
    path=Path(value)
    if not path.is_absolute():path=agent_state.project_root()/path
    if path.is_symlink() or not path.resolve().is_relative_to(agent_state.project_root().resolve()) or path.suffix.lower()!=suffix or not path.is_file():
        raise ValueError('invalid_native_pdf_artifact')
    return path


def quality_snapshot(saved,markdown,pdf):
    try:
        path=local_file(saved['artifacts']['scorecard'],'.md').with_suffix('.json')
        if path.is_symlink() or not path.is_file():raise ValueError('missing scorecard')
        raw=path.read_bytes();score=json.loads(raw)
        md_sha=hashlib.sha256(markdown).hexdigest()
        if score.get('resume_sha256')!=md_sha:raise ValueError('changed resume')
        semantic=score.get('semantic_review') or {};ready=saved.get('resume_readiness',{})
        number=lambda v:v if type(v) in (int,float) and 0<=v<=100 else None
        expression=number(score.get('expression_score'))
        gaps=list(dict.fromkeys(str(s) for s in score.get('gap_tasks',[])))
        report=score.get('quality_report')
        if report is not None and not isinstance(report,dict):raise ValueError('invalid quality report')
        auto_pass=bool(report.get('auto_pass')) if report else False
        legacy=score.get('legacy_scores') if isinstance(score.get('legacy_scores'),dict) else {
            'rule_total':number(score.get('total_score')),'llm_expression':expression}
        passed=bool(ready.get('content_ready') is True and ready.get('quality_passed') is True and auto_pass
                    and score.get('traceability',{}).get('status')=='verified')
        return {'status':'bound','resume_sha256':md_sha,'pdf_sha256':hashlib.sha256(pdf).hexdigest(),
                'scorecard_sha256':hashlib.sha256(raw).hexdigest(),'evaluation_version':score.get('evaluation_version','legacy'),'matching_mode':'semantic' if semantic else 'rule',
                'matching_score':number(semantic.get('fit_score',saved.get('score_total'))),
                'resume_score':number(semantic.get('resume_score')),'expression_score':expression,
                'content_ready':ready.get('content_ready') is True,'quality_passed':passed,'gap_tasks':gaps,
                'auto_pass':auto_pass,'quality_report':report,
                'quality_failures':list(ready.get('quality_failures') or [])[:20],
                'legacy_scores':legacy}
    except (KeyError,TypeError,OSError,ValueError) as exc:
        raise ValueError('quality_scorecard_missing_or_changed') from exc
