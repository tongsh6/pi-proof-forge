import {useTranslation} from 'react-i18next';
import {useNavigate} from 'react-router-dom';

import type {QualityReport, QualityTier} from '@/lib/sidecar/types';

const TIERS: Array<[keyof NonNullable<QualityReport['tiers']>, string]> = [
  ['eligible', 'quality.report.tier.eligible'],
  ['fit', 'quality.report.tier.fit'],
  ['strong', 'quality.report.tier.strong'],
  ['distinct', 'quality.report.tier.distinct'],
];

type CandidateDetail = {
  highlight_id?: string;
  bullet_ref?: string;
  jd_item_id?: string;
  exceeds?: string;
  level?: string;
  reason?: string;
  rejected?: boolean;
};

type HighlightDecision = (highlightId: string, action: 'reject' | 'select') => void | Promise<void>;

export function QualityReportPanel({report,title,onHighlightDecision}:{report?:QualityReport|null;title?:string;onHighlightDecision?:HighlightDecision}){
  const {t}=useTranslation();
  const navigate=useNavigate();
  if(!report||!report.tiers)return <p className="rounded-card border border-border p-3 text-xs text-text-muted">{t('quality.report.missing')}</p>;
  const pending=report.llm_pending||[];
  const legacy=report.legacy_scores;
  const distinct=report.tiers.distinct;
  const highlights=(distinct?.highlights||[]) as Array<Record<string, unknown>>;
  const candidates=(((distinct?.metrics||{}) as Record<string, unknown>).candidates||[]) as CandidateDetail[];
  const highlightIds=new Set(highlights.map(item=>String(item.highlight_id||'')));
  return <section aria-label={title||t('quality.report.title')} className="space-y-3 text-sm">
    <div className="flex items-center justify-between gap-3">
      <p className="font-medium">{title||t('quality.report.title')}</p>
      <span className={report.auto_pass?'text-success':'text-warning'}>{t(report.auto_pass?'quality.passed':'quality.failed')}</span>
    </div>
    {TIERS.map(([name,label])=>{
      const tier: QualityTier | undefined = report.tiers?.[name];
      if(!tier)return null;
      const failures=tier.failures||[];
      const dependency=TIERS.find(([key])=>key===tier.blocked_by);
      return <details key={name} open={!tier.passed} className="rounded-card border border-border bg-bg-primary/40 p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t(label)} · <span className={tier.passed?'text-success':'text-warning'}>{t(tier.passed?'quality.report.passed':'quality.report.failed')}</span>
          {!tier.passed&&<span className="text-text-muted"> ({failures.length})</span>}
          {dependency&&report.tiers?.[dependency[0]]?.passed===false&&<span className="ml-2 text-xs text-text-muted">{t('quality.report.blockedBy',{tier:t(dependency[1])})}</span>}
        </summary>
        {failures.length>0?
          <ul className="mt-2 space-y-1 text-xs text-text-secondary">{failures.map((failure,index)=>{
            const cardId=/ec_[A-Za-z0-9_-]{4,}/.exec(failure.target||'')?.[0];
            return <li className="break-words" key={`${failure.rule}-${index}`}>
              <span className="font-mono text-warning">{failure.rule}</span>
              {failure.target&&<span> · {failure.target}</span>}
              {failure.reason&&<span>：{failure.reason}</span>}
              {cardId&&<button type="button" className="ml-2 text-accent underline" onClick={()=>navigate(`/evidence?card=${encodeURIComponent(cardId)}`)}>{t('quality.report.openCard')}</button>}
            </li>;
          })}</ul>:
          <p className="mt-2 text-xs text-text-muted">{t('quality.report.noFailures')}</p>}
        {name==='distinct'&&(highlights.length>0||candidates.length>0)&&<div className="mt-3 space-y-2">
          <p className="text-xs font-medium text-text-primary">{t('quality.report.highlights')}</p>
          {highlights.map((item,index)=>{
            const highlightId=String(item.highlight_id||'');
            return <div key={highlightId||index} className="rounded-card border border-accent/40 p-2 text-xs">
              <p className="break-words">{String(item.bullet_ref||'')} ↔ {String(item.jd_item_id||'')} · {t('quality.report.exceeds')}: {String(item.exceeds||'')} · {String(item.level||'')}</p>
              {!!item.reason&&<p className="mt-1 break-words text-text-secondary">{String(item.reason)}</p>}
              {onHighlightDecision&&<div className="mt-2 flex flex-wrap gap-2">
                <button type="button" className="text-warning underline" onClick={()=>void onHighlightDecision(highlightId,'reject')}>{t('quality.report.reject')}</button>
                {candidates.filter(candidate=>!candidate.rejected&&!highlightIds.has(String(candidate.highlight_id||''))).slice(0,2).map(candidate=><button type="button" key={String(candidate.highlight_id)} className="text-accent underline"
                  onClick={()=>void onHighlightDecision(String(candidate.highlight_id||''),'select')}>{t('quality.report.select')}</button>)}
              </div>}
            </div>;
          })}
          {candidates.length>0&&<div className="space-y-1">
            {candidates.map(candidate=><p key={String(candidate.highlight_id)} className="break-words text-text-muted">
              {candidate.rejected?t('quality.report.rejected'):t('quality.report.candidate')} · {String(candidate.bullet_ref||'')} ↔ {String(candidate.jd_item_id||'')} · {String(candidate.level||'')}
              {!candidate.rejected&&onHighlightDecision&&!highlightIds.has(String(candidate.highlight_id||''))&&
                <button type="button" className="ml-2 text-accent underline" onClick={()=>void onHighlightDecision(String(candidate.highlight_id||''),'select')}>{t('quality.report.select')}</button>}
            </p>)}
          </div>}
        </div>}
      </details>;
    })}
    {pending.length>0&&<p className="text-xs text-warning">{t('quality.report.llmPending',{rules:pending.join('、')})}</p>}
    <details className="text-xs text-text-secondary">
      <summary className="cursor-pointer text-accent">{t('quality.report.legacy')}</summary>
      <p className="mt-1">{t('quality.report.legacyValue',{rule:legacy?.rule_total??'--',expression:legacy?.llm_expression??'--'})}</p>
    </details>
  </section>;
}
