import {useTranslation} from 'react-i18next';
import {useNavigate} from 'react-router-dom';

import type {QualityReport, QualityTier} from '@/lib/sidecar/types';

const TIERS: Array<[keyof NonNullable<QualityReport['tiers']>, string]> = [
  ['eligible', 'quality.report.tier.eligible'],
  ['fit', 'quality.report.tier.fit'],
  ['strong', 'quality.report.tier.strong'],
  ['distinct', 'quality.report.tier.distinct'],
];

export function QualityReportPanel({report,title}:{report?:QualityReport|null;title?:string}){
  const {t}=useTranslation();
  const navigate=useNavigate();
  if(!report||!report.tiers)return <p className="rounded-card border border-border p-3 text-xs text-text-muted">{t('quality.report.missing')}</p>;
  const pending=report.llm_pending||[];
  const legacy=report.legacy_scores;
  return <section aria-label={title||t('quality.report.title')} className="space-y-3 text-sm">
    <div className="flex items-center justify-between gap-3">
      <p className="font-medium">{title||t('quality.report.title')}</p>
      <span className={report.auto_pass?'text-success':'text-warning'}>{t(report.auto_pass?'quality.passed':'quality.failed')}</span>
    </div>
    {TIERS.map(([name,label])=>{
      const tier: QualityTier | undefined = report.tiers?.[name];
      if(!tier)return null;
      const failures=tier.failures||[];
      return <details key={name} open={!tier.passed} className="rounded-card border border-border bg-bg-primary/40 p-3">
        <summary className="cursor-pointer text-sm font-medium">
          {t(label)} · <span className={tier.passed?'text-success':'text-warning'}>{t(tier.passed?'quality.report.passed':'quality.report.failed')}</span>
          {!tier.passed&&<span className="text-text-muted"> ({failures.length})</span>}
          {tier.blocked_by&&<span className="ml-2 text-xs text-text-muted">{t('quality.report.blockedBy',{tier:tier.blocked_by})}</span>}
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
      </details>;
    })}
    {pending.length>0&&<p className="text-xs text-warning">{t('quality.report.llmPending',{rules:pending.join('、')})}</p>}
    <details className="text-xs text-text-secondary">
      <summary className="cursor-pointer text-accent">{t('quality.report.legacy')}</summary>
      <p className="mt-1">{t('quality.report.legacyValue',{rule:legacy?.rule_total??'--',expression:legacy?.llm_expression??'--'})}</p>
    </details>
  </section>;
}
