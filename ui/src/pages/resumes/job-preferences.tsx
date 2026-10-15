import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {generateJobPreferences,listMaterialDocuments,saveJobPreferences} from '@/lib/sidecar/api';
import {getErrorMessage} from '@/lib/errors';
import {buttonClass,notify} from '@/lib/ui';
import type {JobPreferences,MaterialSourceItem,ProfilePayload} from '@/lib/sidecar/types';

export function JobPreferencesEditor({profile,materials,onSaved}:{profile:ProfilePayload|null;materials:MaterialSourceItem[];onSaved:()=>Promise<void>}){
  const {t}=useTranslation();
  const [material,setMaterial]=useState(''),[document,setDocument]=useState('');
  const [documents,setDocuments]=useState<Array<{document_id:string;label:string}>>([]);
  const [draft,setDraft]=useState<JobPreferences|null>(null),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const request=useRef(0);
  useEffect(()=>{let alive=true;setDocument('');setDocuments([]);if(material)void listMaterialDocuments(material).then(r=>{if(alive){setDocuments(r.items);setDocument(r.items[0]?.document_id||'');}}).catch(e=>{if(alive)setError(getErrorMessage(e));});return()=>{alive=false;};},[material]);
  useEffect(()=>{setDraft(null);setConfirmed(false);request.current++;},[profile?.job_preferences?.revision]);
  const generate=async()=>{const version=++request.current;setBusy(true);setError('');try{const r=await generateJobPreferences(material,document);if(version===request.current){setDraft(r.draft);setConfirmed(false);}}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}};
  const save=async()=>{if(!draft||!confirmed)return;setBusy(true);setError('');try{await saveJobPreferences(draft,profile?.job_preferences?.revision||'');await onSaved();setDraft(null);setConfirmed(false);notify('success',t('pages.resumes.preferences.saved'));}catch(e){setError(getErrorMessage(e));}finally{setBusy(false);}};
  const shown=draft||profile?.job_preferences;
  return <details className="rounded-panel border border-border bg-bg-panel p-5" data-testid="job-preferences-editor">
    <summary className="cursor-pointer font-semibold text-text-primary">{t('pages.resumes.preferences.title')} <span className="ml-2 text-xs font-normal text-text-secondary">{shown?.items.length||0} {t('pages.resumes.preferences.count')}</span></summary>
    <p className="mt-3 text-sm text-text-secondary">{t('pages.resumes.preferences.help')}</p>
    <div className="mt-4 grid gap-3 md:grid-cols-2">
      <label className="text-sm">{t('pages.resumes.preferences.material')}<select data-testid="preferences-material" className="field-input mt-1 w-full" value={material} disabled={busy} onChange={e=>{request.current++;setMaterial(e.target.value);setDraft(null);setConfirmed(false);}}>
        <option value="">{t('pages.resumes.preferences.choose')}</option>{materials.map(m=><option key={m.material_id} value={m.material_id}>{m.label}</option>)}
      </select></label>
      <label className="text-sm">{t('pages.resumes.preferences.document')}<select className="field-input mt-1 w-full" value={document} disabled={busy||!material} onChange={e=>{request.current++;setDocument(e.target.value);setDraft(null);setConfirmed(false);}}>{documents.map(d=><option key={d.document_id} value={d.document_id}>{d.label}</option>)}</select></label>
    </div>
    <button type="button" data-testid="preferences-generate" className={`${buttonClass.secondary} mt-3`} disabled={busy||!material||!document} onClick={generate}>{t(busy?'pages.resumes.preferences.processing':'pages.resumes.preferences.generate')}</button>
    {error&&<p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    {shown?.source&&<p className="mt-3 text-xs text-text-muted">{t('pages.resumes.preferences.source')}：{shown.source.label}</p>}
    <div className="mt-3 space-y-3">{shown?.items.map((item,index)=><div key={index} className="rounded-card border border-border p-3">
      <p className="text-xs font-semibold text-accent">{t(`pages.resumes.preferences.kind.${item.kind}`)}</p>
      {draft?<textarea className="field-input mt-1 w-full" rows={2} value={item.text} onChange={e=>{setDraft({...draft,items:draft.items.map((v,i)=>i===index?{...v,text:e.target.value}:v)});setConfirmed(false);}} disabled={busy}/>:<p className="mt-1 text-sm">{item.text}</p>}
      <blockquote className="mt-2 border-l-2 border-border pl-2 text-xs text-text-secondary">{item.quote}</blockquote>
    </div>)}</div>
    {draft&&<div className="mt-4 space-y-3"><label className="flex items-start gap-2 text-sm"><input data-testid="preferences-confirm" type="checkbox" checked={confirmed} disabled={busy} onChange={e=>setConfirmed(e.target.checked)}/>{t('pages.resumes.preferences.confirm')}</label>
      <button type="button" data-testid="preferences-save" className={buttonClass.primary} disabled={busy||!confirmed} onClick={save}>{t('pages.resumes.preferences.save')}</button></div>}
  </details>;
}
