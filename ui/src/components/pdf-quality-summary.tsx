import {useTranslation} from 'react-i18next';

import type {PdfQuality} from '@/lib/sidecar/types';

export function PdfQualitySummary({quality}:{quality?:PdfQuality}){
  const {t}=useTranslation();
  if(!quality||quality.status==='unrecorded')return <p className="rounded-card border border-warning/40 p-3 text-sm text-warning">{t('quality.unrecorded')}</p>;
  return <section className="space-y-3 rounded-card border border-border bg-bg-primary/40 p-3 text-sm" aria-label={t('quality.title')}>
    <p className="font-medium">{t(quality.status==='bound'?'quality.bound':'quality.current')}</p>
    <dl className="space-y-1 text-text-secondary">
      {([[quality.matching_mode==='rule'?'quality.ruleFit':'quality.fit',quality.matching_score],['quality.coverage',quality.resume_score],['quality.expression',quality.expression_score]] as const).map(([label,value])=><div className="flex justify-between gap-3" key={label}><dt>{t(label)}</dt><dd>{value??'--'}/100</dd></div>)}
      <div className="flex justify-between gap-3"><dt>{t('quality.facts')}</dt><dd>{t(quality.content_ready?'quality.complete':'quality.incomplete')}</dd></div>
    </dl>
    <p className={quality.quality_passed?'text-success':'text-warning'}>{t(quality.quality_passed?'quality.passed':'quality.failed')}</p>
    <p className="text-xs text-text-muted">{t('quality.advisory')}</p>
    {!!quality.gap_tasks?.length&&<details><summary className="cursor-pointer text-accent">{t('quality.gaps')} ({quality.gap_tasks.length})</summary><ul className="mt-2 max-h-72 list-disc space-y-2 overflow-auto pl-4 text-xs text-text-secondary">{quality.gap_tasks.map((gap,index)=><li className="whitespace-pre-wrap break-words" key={index}>{gap}</li>)}</ul></details>}
  </section>;
}
