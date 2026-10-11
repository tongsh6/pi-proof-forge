import {useEffect,useRef,useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getErrorMessage} from '@/lib/errors';
import {listMaterialDocuments,readMaterialDocument,type MaterialDocument,type MaterialDocumentRef} from '@/lib/sidecar/api';

/** 预览只显示正文：去掉 Markdown 文件头部的 YAML front matter。 */
const stripFrontMatter=(text:string)=>text.replace(/^\s*---[\s\S]*?\n---\s*/,'');
export function MaterialDocumentPicker({materialId,onSelect,disabled}:{materialId:string;onSelect:(value:MaterialDocumentRef|null)=>void;disabled:boolean}){
  const {t}=useTranslation();const [query,setQuery]=useState(''),[items,setItems]=useState<MaterialDocument[]>([]),[selected,setSelected]=useState('');
  const [preview,setPreview]=useState(''),[count,setCount]=useState({matched:0,total:0}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const revision=useRef(0);
  const search=async(term:string)=>{const rev=++revision.current;onSelect(null);setSelected('');setPreview('');setBusy(true);setError('');
    try{const r=await listMaterialDocuments(materialId,term);if(rev===revision.current){setItems(r.items);setCount(r);}}
    catch(e){if(rev===revision.current)setError(getErrorMessage(e));}finally{if(rev===revision.current)setBusy(false);}};
  useEffect(()=>{setQuery('');setItems([]);onSelect(null);if(materialId)void search('');return()=>{revision.current++;};},[materialId]);
  const select=async(id:string)=>{const rev=++revision.current;onSelect(null);setSelected(id);setPreview('');setError('');if(!id)return;setBusy(true);
    try{const r=await readMaterialDocument(materialId,id);if(rev===revision.current){setPreview(stripFrontMatter(r.text));onSelect({material_id:materialId,document_id:r.document_id,sha256:r.sha256,label:r.label});}}
    catch(e){if(rev===revision.current)setError(getErrorMessage(e));}finally{if(rev===revision.current)setBusy(false);}};
  return <div className="mt-4 space-y-3 rounded-card border border-border bg-bg-primary/40 p-4">
    <p className="text-sm font-medium">{t('materialDocument.title')}</p><p className="text-xs text-text-secondary">{t('materialDocument.help')}</p>
    <div className="flex gap-2"><input data-testid="document-query" aria-label={t('materialDocument.query')} value={query} onChange={e=>setQuery(e.target.value)} disabled={disabled||busy||!materialId} placeholder={t('materialDocument.query')} className="min-w-0 flex-1 rounded-card border border-border bg-bg-primary px-3 py-2 text-sm"/><button data-testid="document-search" disabled={disabled||busy||!materialId} onClick={()=>void search(query)} className="rounded-card border border-border px-3 py-2 text-sm disabled:opacity-40">{t('materialDocument.search')}</button></div>
    <select data-testid="document-select" aria-label={t('materialDocument.select')} value={selected} onChange={e=>void select(e.target.value)} disabled={disabled||busy||!items.length} className="w-full min-w-0 rounded-card border border-border bg-bg-primary px-3 py-2 text-sm"><option value="">{t('materialDocument.select')}</option>{items.map(i=><option key={i.document_id} value={i.document_id}>{i.label} ({i.char_count})</option>)}</select>
    <p className="text-xs text-text-muted">{t('materialDocument.count',{matched:count.matched,total:count.total,shown:items.length})}</p>
    {preview&&<details><summary className="cursor-pointer text-sm text-accent">{t('materialDocument.preview')}</summary><pre data-testid="document-preview" className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs text-text-secondary">{preview}</pre></details>}
    {error&&<p role="alert" className="text-sm text-error">{error}</p>}
  </div>;
}
