import type {EvidenceDraftPayload, EvidenceFieldSource} from '@/lib/sidecar/types';
import type {MaterialDocumentRef} from '@/lib/sidecar/api';

/** 只在审核草稿中采用原句；时间精度及责任限定不作推断。 */
export function adoptSource(draft:EvidenceDraftPayload,field:EvidenceFieldSource['field'],value:string,ref:MaterialDocumentRef):EvidenceDraftPayload {
  const multiple=field==='actions'||field==='results';
  const adopted=multiple?[...new Set(value.split('\n').map(line=>line.trim()).filter(Boolean))]:[value];
  const values=multiple?[...new Set([...(draft[field]||'').split('\n').filter(Boolean),...adopted])]:adopted;
  const sources=(draft.field_sources||[]).filter(s=>s.field!==field||(multiple&&!adopted.includes(s.value)));
  sources.push(...adopted.map(value=>({field,value,quote:value,material_id:ref.material_id,document_id:ref.document_id})));
  const documents=draft.source_documents||[];
  return {...draft,[field]:values.join('\n'),field_sources:sources,
    source_material_ids:[...new Set([...draft.source_material_ids,ref.material_id])],
    source_documents:documents.some(d=>d.material_id===ref.material_id&&d.document_id===ref.document_id)?documents:[...documents,ref],
    artifacts:draft.artifacts.some(a=>a.ref===ref.material_id)?draft.artifacts:[...draft.artifacts,{type:'text_document',ref:ref.material_id,label:ref.label}]};
}
