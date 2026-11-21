import type {EvidenceDetail, EvidenceDraftPayload, EvidenceFactPosition, EvidenceFieldSource} from '@/lib/sidecar/types';
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

/** 扩大既有事实的一条引文；事实身份、其它绑定和来源版本保持不变。 */
export function extendSourceQuote(
  draft: EvidenceDraftPayload,
  position: EvidenceFactPosition,
  binding: EvidenceFieldSource,
  document: MaterialDocumentRef,
  sourceText: string,
  quote: string,
): EvidenceDraftPayload {
  const {field, index, value} = position;
  const values = (field === 'actions' || field === 'results')
    ? draft[field].split(/\r?\n/).map(item => item.trim()).filter(Boolean) : [];
  if (!Number.isInteger(index) || index < 0 || values[index] !== value ||
      values.filter(item => item === value).length !== 1) {
    throw new Error('fact_scope_invalid_position');
  }
  const sources = draft.field_sources ?? [];
  const keys = ['field', 'value', 'quote', 'material_id', 'document_id'] as const;
  const matches = sources.flatMap((source, sourceIndex) =>
    keys.every(key => source[key] === binding[key]) ? [sourceIndex] : []);
  if (binding.field !== field || binding.value !== value || matches.length !== 1 ||
      !binding.quote || !binding.quote.includes(value)) {
    throw new Error('field_source_not_traceable');
  }
  const references = (draft.source_documents ?? []).filter(ref =>
    ref.material_id === binding.material_id && ref.document_id === binding.document_id);
  if (references.length !== 1 || document.material_id !== binding.material_id ||
      document.document_id !== binding.document_id || document.sha256 !== references[0].sha256) {
    throw new Error('material_document_changed_or_missing');
  }
  if (quote.length <= binding.quote.length || !quote.includes(binding.quote) || !sourceText.includes(quote)) {
    throw new Error('field_source_not_traceable');
  }
  if (sourceText.indexOf(quote) !== sourceText.lastIndexOf(quote) ||
      quote.indexOf(binding.quote) !== quote.lastIndexOf(binding.quote)) {
    throw new Error('fact_scope_source_not_unique');
  }
  return {...draft, field_sources: sources.map((source, sourceIndex) =>
    sourceIndex === matches[0] ? {...source, quote} : source)};
}

/** Match the saved source baseline. Only an actual append requests source merging. */
export function hasSourceAppend(
  previous: Pick<EvidenceDetail, 'source_material_ids' | 'source_documents'>,
  draft: Pick<EvidenceDraftPayload, 'source_material_ids' | 'source_documents'>,
): boolean {
  const oldIds = previous.source_material_ids ?? [];
  const oldRefs = previous.source_documents ?? [];
  const nextIds = draft.source_material_ids;
  const nextRefs = draft.source_documents ?? [];
  const sameRef = (left: MaterialDocumentRef, right: MaterialDocumentRef | undefined) =>
    right !== undefined && Object.keys(left).length === Object.keys(right).length &&
    Object.entries(left).every(([key, value]) => right[key as keyof MaterialDocumentRef] === value);
  if (!oldIds.every((id, index) => nextIds[index] === id) ||
      !oldRefs.every((ref, index) => sameRef(ref, nextRefs[index]))) {
    throw new Error('evidence_review_source_mismatch');
  }
  const appended = nextIds.length > oldIds.length || nextRefs.length > oldRefs.length;
  if (appended && (new Set(nextIds).size !== nextIds.length ||
      new Set(nextRefs.map(ref => JSON.stringify([ref.material_id, ref.document_id]))).size !== nextRefs.length)) {
    throw new Error('evidence_review_source_mismatch');
  }
  return appended;
}
