import {useEffect,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getErrorMessage} from '@/lib/errors';
import {buttonClass,confirmAction,notify} from '@/lib/ui';
import {listEvidence,updateProfile,reviewCareerProfile} from '@/lib/sidecar/api';
import type {ProfilePayload,CareerProfile,CareerEntry,EvidenceListItem} from '@/lib/sidecar/types';

type Group='work'|'education'|'skills'|'extras';
const empty:CareerProfile={schema_version:1,summary:'',work:[],education_visibility:'show',education:[],skills:[],extras:[]};
const definitions:Record<Group,string[]>={work:['company','department','title','start','end','scope','contributions'],education:['school','major','degree','start','end'],skills:['category','description'],extras:['title','description','url']};
/** 条目摘要：折叠时一行显示公司 · 职务 · 时间（教育：学校 · 专业 · 学历；能力：分类；成果：名称）。 */
function entrySummary(group:Group,row:CareerEntry,now:string):string{
  const s=(k:string)=>String(row[k]||'').trim();
  const period=[s('start'),row.current?now:s('end')].filter(Boolean).join(' – ');
  if(group==='work')return [s('company'),s('title'),period].filter(Boolean).join(' · ');
  if(group==='education')return [s('school'),s('major'),s('degree')].filter(Boolean).join(' · ');
  if(group==='skills')return s('category');
  return s('title');
}
export function CareerProfileEditor({profile,onSaved}:{profile:ProfilePayload|null;onSaved:()=>Promise<void>}){
  const {t}=useTranslation();
  const [draft,setDraft]=useState<CareerProfile>(profile?.career||empty),[revision,setRevision]=useState(profile?.revision||'');
  const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[consent,setConsent]=useState(false),[error,setError]=useState('');
  const [evidence,setEvidence]=useState<EvidenceListItem[]>([]);
  useEffect(()=>{if(!dirty){setDraft(profile?.career||empty);setRevision(profile?.revision||'');setConsent(false);}},[profile?.revision,dirty]);
  useEffect(()=>{let alive=true;void listEvidence({query:'',status:'saved_eligible',role:null,tags:[],date_range:null}).then(r=>{if(alive)setEvidence(r.items.filter(e=>e.candidate_pool_eligible!==false&&e.status==='saved_eligible'));}).catch(e=>{if(alive)setError(getErrorMessage(e));});return()=>{alive=false;};},[]);
  const change=(value:CareerProfile)=>{setDraft(value);setDirty(true);setConsent(false);};
  const rowChange=(group:Group,id:string,patch:Partial<CareerEntry>)=>change({...draft,[group]:draft[group].map(row=>row.id===id?{...row,...patch}:row)});
  const add=(group:Group)=>{const item:CareerEntry={id:group+'_'+crypto.randomUUID()};definitions[group].forEach(field=>{item[field]=field==='contributions'?[]:'';});if(group==='work'||group==='education')item.current=false;if(group==='work'||group==='skills')item.evidence_ids=[];change({...draft,[group]:[...draft[group],item]});};
  const act=async(fn:()=>Promise<unknown>,successKey:string)=>{setBusy(true);setError('');try{await fn();setDirty(false);setConsent(false);await onSaved();notify('success',t(successKey));}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}};
  const removeEntry=async(group:Group,id:string)=>{if(!(await confirmAction({title:t('confirmations.career.removeEntry.title'),description:t('confirmations.career.removeEntry.description'),confirmLabel:t('confirmations.career.removeEntry.confirm'),tone:'danger'})))return;change({...draft,[group]:draft[group].filter(item=>item.id!==id)});};
  const reload=async()=>{if(dirty&&!(await confirmAction({title:t('confirmations.career.reload.title'),description:t('confirmations.career.reload.description'),confirmLabel:t('confirmations.career.reload.confirm'),tone:'danger'})))return;setDraft(profile?.career||empty);setRevision(profile?.revision||'');setDirty(false);setConsent(false);setError('');};
  const missing=profile?.career_status?.missing||[],stale=revision!==profile?.revision;
  // 确认复选框不可用时给出具体原因，而不是只变灰。
  const consentReason=stale?t('reasons.career.consentStale'):dirty?t('reasons.career.consentDirty'):missing.length?t('reasons.career.consentMissing'):'';
  const input='w-full rounded-card border border-border bg-bg-primary p-2 text-sm disabled:opacity-50';
  const button=buttonClass.secondary;
  return <section data-testid="career-editor" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-lg font-semibold">{t('career.title')}</h2><p className="mt-1 text-sm text-text-secondary">{t('career.help')}</p></div><span className="text-sm text-text-secondary">{t(profile?.career_status?.reviewed&&!dirty?'career.reviewed':'career.draft')}</span></div>
    <label className="block space-y-2 text-sm">{t('career.summary')}<textarea data-testid="career-summary" aria-label={t('career.summary')} className={input} rows={3} maxLength={4000} value={draft.summary} disabled={busy} onChange={e=>change({...draft,summary:e.target.value})}/><span className="text-xs text-text-muted">{t('career.summaryHint')}</span></label>
    {(['work','skills','education','extras'] as Group[]).map(group=><details key={group} open={group==='work'} className="rounded-card border border-border p-3">
      <summary className="cursor-pointer font-medium">{t('career.groups.'+group)} ({draft[group].length})</summary>
      {group==='education'&&<label className="mt-3 flex gap-2 text-sm"><input type="checkbox" checked={draft.education_visibility==='show'} disabled={busy} onChange={e=>change({...draft,education_visibility:e.target.checked?'show':'omit'})}/>{t('career.showEducation')}</label>}
      <div className="mt-3 space-y-3">{draft[group].map((row,index)=>{const summary=entrySummary(group,row,t('career.now'));return <details key={row.id} open={!summary} className="rounded-card border border-border bg-bg-primary/30">
        <summary className="flex cursor-pointer select-none flex-wrap items-baseline gap-x-3 px-4 py-3 text-sm"><span className="font-medium">{t('career.groups.'+group)} {index+1}</span><span className="min-w-0 truncate text-text-secondary">{summary||t('common.notFilled')}</span><span className="ml-auto text-xs text-text-muted">{t('career.expandEntry')}</span></summary>
        <fieldset className="space-y-3 px-4 pb-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{definitions[group].map(field=>{
          const multiline=['scope','contributions','description'].includes(field);const value=field==='contributions'?(row.contributions||[]).join('\n'):String(row[field]||'');
          const props={'data-field':field,'aria-label':t('career.fields.'+(group==='extras'&&field==='title'?'achievementTitle':field))+' '+(index+1),className:input,disabled:busy||((field==='end')&&row.current),value,onChange:(e:{target:{value:string}})=>rowChange(group,row.id,{[field]:field==='contributions'?e.target.value.split('\n'):e.target.value})};
          return <label key={field} className={multiline?'space-y-1 text-sm md:col-span-2':'space-y-1 text-sm'}><span>{t('career.fields.'+(group==='extras'&&field==='title'?'achievementTitle':field))}</span>{multiline?<textarea {...props} rows={3} maxLength={4000}/>:<input {...props} type={['start','end'].includes(field)?'month':field==='url'?'url':'text'} maxLength={4000}/>}</label>;
        })}</div>
        {(group==='work'||group==='education')&&<label className="flex gap-2 text-sm"><input type="checkbox" checked={Boolean(row.current)} disabled={busy} onChange={e=>rowChange(group,row.id,{current:e.target.checked,end:e.target.checked?'':row.end})}/>{t(group==='work'?'career.currentWork':'career.currentEducation')}</label>}
        {(group==='work'||group==='skills')&&<details><summary className="cursor-pointer text-sm text-accent">{t('career.linkEvidence')} ({row.evidence_ids?.length||0})</summary><div className="mt-2 grid gap-2 md:grid-cols-2">{evidence.map(item=><label key={item.evidence_id} className="flex gap-2 text-sm"><input type="checkbox" checked={row.evidence_ids?.includes(item.evidence_id)||false} disabled={busy} onChange={e=>rowChange(group,row.id,{evidence_ids:e.target.checked?[...(row.evidence_ids||[]),item.evidence_id]:(row.evidence_ids||[]).filter(id=>id!==item.evidence_id)})}/>{item.title||item.evidence_id}</label>)}</div><p className="mt-2 text-xs text-text-muted">{t('career.linkHint')}</p></details>}
        <button type="button" className={buttonClass.ghost} disabled={busy} onClick={()=>void removeEntry(group,row.id)}>{t('career.remove')}</button>
      </fieldset></details>;})}</div>
      <button type="button" data-testid={'career-add-'+group} className={'mt-3 '+button} disabled={busy} onClick={()=>add(group)}>{t('career.add.'+group)}</button>
    </details>)}
    <div className="sticky bottom-0 z-10 -mx-5 space-y-3 border-t border-border bg-bg-panel px-5 py-3">
    {!!missing.length&&<div className="rounded-card border border-warning/40 p-3 text-sm text-warning"><p>{t('career.missing')}</p><ul className="mt-2 list-inside list-disc">{missing.map(item=><li key={item.field}>{item.label}</li>)}</ul></div>}
    {stale&&<p className="text-sm text-warning">{t('career.stale')}</p>}{error&&<p role="alert" className="text-sm text-error">{error}</p>}
    <label className="flex gap-2 text-sm"><input data-testid="career-consent" type="checkbox" checked={consent} disabled={busy||dirty||stale||!revision||!!missing.length} onChange={e=>setConsent(e.target.checked)}/><span>{t('career.consent')}{consentReason&&<span className="ml-2 text-xs text-text-muted">（{consentReason}）</span>}</span></label>
    <div className="flex flex-wrap gap-2"><button type="button" data-testid="career-save" className={buttonClass.secondary} disabled={busy||!dirty||stale||!revision} title={!dirty?t('reasons.career.saveClean'):undefined} onClick={()=>void act(()=>updateProfile({career:draft},revision),'toasts.resumes.careerSaved')}>{t('career.save')}</button><button type="button" data-testid="career-confirm" className={buttonClass.primary} disabled={busy||dirty||stale||!consent||!revision||!!missing.length} title={consentReason||undefined} onClick={()=>void act(()=>reviewCareerProfile(revision),'toasts.resumes.careerConfirmed')}>{t('career.confirm')}</button><button type="button" className={buttonClass.ghost} disabled={busy} onClick={()=>void reload()}>{t('career.reload')}</button></div>
    </div>
  </section>;
}
