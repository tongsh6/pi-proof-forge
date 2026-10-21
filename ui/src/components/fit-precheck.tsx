import {useTranslation} from 'react-i18next';

import type {FitPrecheck, FitPrecheckState, JobProfileListItem} from '@/lib/sidecar/types';

const STATE_TONES: Record<FitPrecheckState, string> = {
  recommended: 'border-success/40 bg-success/10 text-success',
  consider: 'border-success/40 bg-success/10 text-success',
  promising: 'border-accent/40 bg-accent/10 text-accent',
  caution: 'border-warning/40 bg-warning/10 text-warning',
  hold: 'border-warning/40 bg-warning/10 text-warning',
  unknown: 'border-border bg-bg-hover text-text-secondary',
  low: 'border-error/40 bg-error/10 text-error',
};

const RANKING_LIMIT = 3;

function rankOf(precheck?: FitPrecheck | null): number {
  return typeof precheck?.rank === 'number' ? precheck.rank : 5;
}

function percentOf(coverage?: number | null): number | null {
  return typeof coverage === 'number' && Number.isFinite(coverage)
    ? Math.round(coverage * 100)
    : null;
}

const RANKABLE_STATES: FitPrecheckState[] = ['recommended', 'consider', 'promising', 'caution'];

function isRankable(profile: JobProfileListItem, precheck: FitPrecheck): boolean {
  // 只推荐可立即进入 Quick Run 的 active 画像；hold 需先核对事实，不进入推荐清单。
  if (profile.status !== 'active') return false;
  if (precheck.source === 'insufficient') return false;
  return RANKABLE_STATES.includes(precheck.state);
}

export function FitPrecheckBadge({precheck,compact}:{precheck?:FitPrecheck|null;compact?:boolean}){
  const {t}=useTranslation();
  if(!precheck)return null;
  const state: FitPrecheckState = precheck.state || 'unknown';
  return <span
    data-testid={`fit-precheck-badge-${state}`}
    className={`inline-flex w-fit items-center rounded-chip border px-2.5 py-1 text-xs ${compact?'':'text-sm '}${STATE_TONES[state]||STATE_TONES.unknown}`}
  >
    {t(`pages.jobs.precheck.state.${state}`, {defaultValue: state})}
  </span>;
}

export function FitPrecheckRanking({profiles,onSelect}:{profiles:JobProfileListItem[];onSelect:(profileId:string)=>void}){
  const {t}=useTranslation();
  const candidates: Array<{profile: JobProfileListItem; precheck: FitPrecheck}> = [];
  profiles.forEach(profile=>{
    const precheck=profile.fit_precheck;
    if(precheck&&isRankable(profile,precheck))candidates.push({profile,precheck});
  });
  candidates.sort((left,right)=>rankOf(left.precheck)-rankOf(right.precheck));
  const ranked=candidates.slice(0,RANKING_LIMIT);
  return <section
    data-testid="jobs-precheck-ranking"
    aria-label={t('pages.jobs.precheck.heading')}
    className="rounded-panel border border-border bg-bg-panel p-5 shadow-[var(--shadow-panel)]"
  >
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-base font-semibold text-text-primary">{t('pages.jobs.precheck.heading')}</h2>
      <p className="text-xs text-text-secondary">{t('pages.jobs.precheck.subtitle')}</p>
    </div>
    {ranked.length===0
      ? <p className="mt-3 text-sm text-text-muted">{t('pages.jobs.precheck.empty')}</p>
      : <ol className="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {ranked.map(({profile,precheck},index)=>{
          const percent=percentOf(precheck.coverage);
          const total=precheck.total_requirements;
          return <li key={profile.job_profile_id}>
            <button
              type="button"
              className="flex w-full items-start gap-3 rounded-card border border-border bg-bg-primary/40 p-3 text-left transition-colors hover:bg-bg-hover/60"
              onClick={()=>onSelect(profile.job_profile_id)}
            >
              <span className="text-xs font-medium text-text-muted">{String(index+1).padStart(2,'0')}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-text-primary">{profile.title}</span>
                <span className="mt-1 block truncate text-xs text-text-secondary">{profile.company||profile.business_domain||'--'}</span>
                <span className="mt-2 flex flex-wrap items-center gap-2">
                  <FitPrecheckBadge precheck={precheck} compact />
                  {percent!==null?<span className="text-xs text-text-secondary">{t('pages.jobs.precheck.coverage',{percent})}</span>:null}
                  {typeof total==='number'&&total>0?<span className="text-xs text-text-secondary">{t('pages.jobs.precheck.matched',{matched:precheck.matched_requirements??0,total})}</span>:null}
                </span>
              </span>
            </button>
          </li>;
        })}
      </ol>}
  </section>;
}

export function FitPrecheckDetail({precheck}:{precheck?:FitPrecheck|null}){
  const {t}=useTranslation();
  if(!precheck)return null;
  const percent=percentOf(precheck.coverage);
  const assessed=precheck.source==='assessed';
  const total=precheck.total_requirements;
  const matchedTerms=precheck.matched_terms||[];
  const missingTerms=precheck.missing_terms||[];
  const missingCount=typeof total==='number'&&typeof precheck.matched_requirements==='number'
    ? Math.max(0,total-precheck.matched_requirements)
    : missingTerms.length;
  // assessed 复用 Quick Run 结论，没有逐项命中明细；只有规则预检可展示覆盖与命中数。
  const countsText=typeof total==='number'&&total>0
    ? `${percent!==null?`${t('pages.jobs.precheck.coverage',{percent})} · `:''}${t('pages.jobs.precheck.matched',{matched:precheck.matched_requirements??0,total})}`
    : null;
  return <section data-testid="fit-precheck-detail" className="rounded-card border border-border bg-bg-primary/40 p-3 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="font-medium text-text-primary">{t('pages.jobs.precheck.heading')}</p>
      <FitPrecheckBadge precheck={precheck} compact />
    </div>
    <p className="mt-2 text-xs text-text-secondary">
      {assessed
        ? t('pages.jobs.precheck.basisAssessed')
        : precheck.source==='rule'
          ? t('pages.jobs.precheck.basisRule')
          : t('pages.jobs.precheck.basisInsufficient')}
    </p>
    {countsText?<p className="mt-1 text-xs text-text-secondary">{countsText}</p>:null}
    {matchedTerms.length>0&&<p className="mt-2 flex flex-wrap gap-1.5">
      {matchedTerms.map(term=><span key={`matched-${term}`} className="rounded-chip border border-success/40 bg-success/10 px-2 py-0.5 text-xs text-success">{term}</span>)}
    </p>}
    {missingTerms.length>0&&<div className="mt-2 text-xs text-text-secondary">
      <p>{t('pages.jobs.precheck.missing',{count:missingCount})}</p>
      <p className="mt-1 flex flex-wrap gap-1.5">
        {missingTerms.map(term=><span key={`missing-${term}`} className="rounded-chip border border-warning/40 bg-warning/10 px-2 py-0.5 text-xs text-warning">{term}</span>)}
      </p>
    </div>}
    {!assessed&&<p className="mt-2 text-xs text-text-muted">{t('pages.jobs.precheck.limitation')}</p>}
  </section>;
}
