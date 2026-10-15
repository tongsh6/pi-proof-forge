import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import type {EvidenceDraftPayload,EvidenceFieldSource,MaterialSourceItem} from '@/lib/sidecar/types';
import type {MaterialDocumentRef} from '@/lib/sidecar/api';
import {MaterialDocumentPicker} from './material-document-picker';
import {adoptSource} from './source-merge';

export function EvidenceSourceMerge({draft,materials,disabled,onChange}:{draft:EvidenceDraftPayload;materials:MaterialSourceItem[];disabled:boolean;onChange:(draft:EvidenceDraftPayload)=>void}){
  const {t}=useTranslation();
  const [material,setMaterial]=useState(''),[document,setDocument]=useState<MaterialDocumentRef|null>(null),[text,setText]=useState('');
  const [field,setField]=useState<EvidenceFieldSource['field']>('role_scope'),[quote,setQuote]=useState(''),[checked,setChecked]=useState(false);
  const labels={time_range:'timeRange',role_scope:'role',context:'context',actions:'actions',results:'results'};
  const valid=!!document&&!!quote.trim()&&text.includes(quote.trim())&&checked;
  const input='w-full rounded-card border border-border bg-bg-primary px-3 py-2 text-sm';
  return <details className="rounded-card border border-border p-3" data-testid="source-merge">
    <summary className="cursor-pointer text-sm font-medium text-accent">{t('sourceMerge.title')}</summary>
    <div className="mt-3 space-y-3">
      <p className="text-xs text-text-secondary">{t('sourceMerge.help')}</p>
      <select aria-label={t('sourceMerge.material')} className={input} value={material} disabled={disabled} onChange={e=>{setMaterial(e.target.value);setDocument(null);setText('');setChecked(false);}}>
        <option value="">{t('sourceMerge.material')}</option>
        {materials.filter(m=>['.md','.txt'].includes(m.extension)).map(m=><option key={m.material_id} value={m.material_id}>{m.label||m.filename}</option>)}
      </select>
      <MaterialDocumentPicker materialId={material} disabled={disabled} onRead={setText} onSelect={ref=>{setDocument(ref);setChecked(false);}}/>
      <select aria-label={t('sourceMerge.field')} className={input} value={field} disabled={disabled} onChange={e=>{setField(e.target.value as EvidenceFieldSource['field']);setChecked(false);}}>
        {Object.entries(labels).map(([key,label])=><option key={key} value={key}>{t(`pages.evidence.fields.${label}`)}</option>)}
      </select>
      <p className="text-xs text-text-secondary">{t('sourceMerge.current')}</p>
      <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-words text-xs">{draft[field]||t('sourceMerge.empty')}</pre>
      <textarea aria-label={t('sourceMerge.quote')} className={`${input} min-h-24`} value={quote} disabled={disabled} onChange={e=>{setQuote(e.target.value);setChecked(false);}} placeholder={t('sourceMerge.quote')}/>
      {!!quote.trim()&&!!document&&!text.includes(quote.trim())&&<p role="alert" className="text-xs text-warning">{t('sourceMerge.notFound')}</p>}
      <label className="flex items-start gap-2 text-xs text-text-secondary"><input type="checkbox" checked={checked} disabled={disabled} onChange={e=>setChecked(e.target.checked)}/>{t('sourceMerge.confirm')}</label>
      <button type="button" disabled={disabled||!valid||(draft.source_documents?.length||0)>=8&&!draft.source_documents?.some(d=>d.document_id===document?.document_id&&d.material_id===document?.material_id)} className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-40" onClick={()=>{if(document){onChange(adoptSource(draft,field,quote.trim(),document));setQuote('');setChecked(false);}}}>
        {t(field==='actions'||field==='results'?'sourceMerge.append':'sourceMerge.replace')}
      </button>
      {!!draft.field_sources?.length&&<div className="space-y-2 border-t border-border pt-3"><p className="text-xs font-medium">{t('sourceMerge.bound')}</p>{draft.field_sources.map((s,i)=><p className="break-words text-xs text-text-secondary" key={i}>{t(`pages.evidence.fields.${labels[s.field]}`)}：{s.value}<br/>{draft.source_documents?.find(d=>d.document_id===s.document_id&&d.material_id===s.material_id)?.label}</p>)}</div>}
    </div>
  </details>;
}
