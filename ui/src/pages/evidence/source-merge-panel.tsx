import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import type {EvidenceDraftPayload, EvidenceFactPosition, EvidenceFieldSource, MaterialSourceItem} from '@/lib/sidecar/types';
import type {MaterialDocumentRef} from '@/lib/sidecar/api';
import {MaterialDocumentPicker} from './material-document-picker';
import {adoptSource, extendSourceQuote} from './source-merge';

export function EvidenceSourceMerge({draft, materials, disabled, onChange}: {
  draft: EvidenceDraftPayload;
  materials: MaterialSourceItem[];
  disabled: boolean;
  onChange: (draft: EvidenceDraftPayload) => void;
}) {
  const {t} = useTranslation();
  const emptyReview = {
    material: '', document: null as MaterialDocumentRef | null, text: '',
    field: 'role_scope' as EvidenceFieldSource['field'], quote: '',
    confirmation: null as {revision: number; draftKey: string} | null,
    extension: null as {position: EvidenceFactPosition; binding: EvidenceFieldSource} | null,
  };
  const [review, setReview] = useState(emptyReview);
  const {material, document, text, field, quote, extension} = review;
  const draftKey = JSON.stringify(draft);
  const context = JSON.stringify([extension ? draftKey : null, disabled, material, extension]);
  const reader = useRef({context, revision: 0});
  if (reader.current.context !== context) reader.current = {context, revision: reader.current.revision + 1};
  const revision = reader.current.revision;
  // 普通补证可沿用已读原文，但核对确认始终绑定当前草稿。
  const checked = review.confirmation?.revision === revision && review.confirmation.draftKey === draftKey;
  const view = {};
  const currentView = useRef<object | null>(view);
  currentView.current = view;
  const mounted = useRef(true);
  const isCurrent = () => mounted.current && currentView.current === view && !disabled;
  const isCurrentRead = () => mounted.current && reader.current.revision === revision && !disabled;
  const invalidate = () => { reader.current.revision++; currentView.current = null; };
  const reset = () => {
    invalidate(); setReview({...emptyReview});
  };
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => {
    if (extension || disabled) reset();
    else {
      currentView.current = null;
      setReview(previous => ({...previous, confirmation: null}));
    }
  }, [draftKey, disabled]);

  const labels = {time_range: 'timeRange', role_scope: 'role', context: 'context', actions: 'actions', results: 'results'};
  const input = 'w-full rounded-card border border-border bg-bg-primary px-3 py-2 text-sm';
  let extensionError = '';
  if (extension && document) {
    try {
      extendSourceQuote(draft, extension.position, extension.binding, document, text, quote);
    } catch (error) {
      extensionError = error instanceof Error ? error.message : 'field_source_not_traceable';
    }
  }
  const errorLabels: Record<string, string> = {
    fact_scope_invalid_position: 'extensionTargetChanged',
    field_source_not_traceable: 'extensionInvalid',
    material_document_changed_or_missing: 'extensionSourceChanged',
    fact_scope_source_not_unique: 'extensionAmbiguous',
  };
  const valid = !!document && checked && (extension
    ? !extensionError
    : !!quote.trim() && text.includes(quote.trim()));
  const sourceLimit = !extension && (draft.source_documents?.length ?? 0) >= 8 &&
    !draft.source_documents?.some(ref => ref.material_id === document?.material_id && ref.document_id === document?.document_id);
  const apply = () => {
    if (!isCurrent() || !valid || !document || sourceLimit) return;
    const next = extension
      ? extendSourceQuote(draft, extension.position, extension.binding, document, text, quote)
      : adoptSource(draft, field, quote.trim(), document);
    if (extension) reset();
    else {
      currentView.current = null;
      setReview(previous => ({...previous, quote: '', confirmation: null}));
    }
    onChange(next);
  };

  return <details className="rounded-card border border-border p-3" data-testid="source-merge">
    <summary className="cursor-pointer text-sm font-medium text-accent">{t('sourceMerge.title')}</summary>
    <div className="mt-3 space-y-3">
      <p className="text-xs text-text-secondary">{t(extension ? 'sourceMerge.extensionHelp' : 'sourceMerge.help')}</p>
      <select aria-label={t('sourceMerge.material')} className={input} value={material} disabled={disabled || !!extension} onChange={event => {
        if (!isCurrent()) return;
        invalidate();
        const value = event.target.value;
        setReview(previous => ({...previous, material: value, document: null, text: '', confirmation: null}));
      }}>
        <option value="">{t('sourceMerge.material')}</option>
        {materials.filter(item => ['.md', '.txt'].includes(item.extension)).map(item =>
          <option key={item.material_id} value={item.material_id}>{item.label || item.filename}</option>)}
      </select>
      {extension && <p className="text-xs text-text-secondary">{t('sourceMerge.boundDocument')}：{
        draft.source_documents?.find(ref => ref.material_id === extension.binding.material_id && ref.document_id === extension.binding.document_id)?.label
      }</p>}
      <MaterialDocumentPicker key={revision} materialId={material} disabled={disabled} onRead={value => {
        if (!isCurrentRead()) return;
        currentView.current = null;
        setReview(previous => ({...previous, text: value, confirmation: null}));
      }} onSelect={ref => {
        if (!isCurrentRead()) return;
        currentView.current = null;
        setReview(previous => ({...previous, document: ref, text: ref ? previous.text : '', confirmation: null}));
      }}/>
      <select aria-label={t('sourceMerge.field')} className={input} value={field} disabled={disabled || !!extension} onChange={event => {
        if (!isCurrent()) return;
        currentView.current = null;
        const value = event.target.value as EvidenceFieldSource['field'];
        setReview(previous => ({...previous, field: value, confirmation: null}));
      }}>
        {Object.entries(labels).map(([key, label]) => <option key={key} value={key}>{t('pages.evidence.fields.' + label)}</option>)}
      </select>
      <p className="text-xs text-text-secondary">{t('sourceMerge.current')}</p>
      <pre className="max-h-28 overflow-auto whitespace-pre-wrap break-words text-xs">{extension?.position.value ?? (draft[field] || t('sourceMerge.empty'))}</pre>
      {extension && <div className="space-y-1">
        <p className="text-xs text-text-secondary">{t('sourceMerge.previousQuote')}</p>
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs">{extension.binding.quote}</pre>
      </div>}
      <textarea aria-label={t('sourceMerge.quote')} className={input + ' min-h-24'} value={quote} disabled={disabled} onChange={event => {
        if (!isCurrent()) return;
        currentView.current = null;
        const value = event.target.value;
        setReview(previous => ({...previous, quote: value, confirmation: null}));
      }} placeholder={t('sourceMerge.quote')}/>
      {extensionError && <p role="alert" className="text-xs text-warning">{t('sourceMerge.' + errorLabels[extensionError])}</p>}
      {!extension && !!quote.trim() && !!document && !text.includes(quote.trim()) &&
        <p role="alert" className="text-xs text-warning">{t('sourceMerge.notFound')}</p>}
      <label className="flex items-start gap-2 text-xs text-text-secondary">
        <input type="checkbox" checked={checked} disabled={disabled} onChange={event => {
          if (!isCurrent()) return;
          currentView.current = null;
          const confirmation = event.target.checked ? {revision, draftKey} : null;
          setReview(previous => ({...previous, confirmation}));
        }}/>{t(extension ? 'sourceMerge.extensionConfirm' : 'sourceMerge.confirm')}
      </label>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={disabled || !valid || sourceLimit} className="rounded-card border border-accent px-3 py-2 text-sm text-accent disabled:opacity-40" onClick={apply}>
          {t(extension ? 'sourceMerge.applyExtension' : field === 'actions' || field === 'results' ? 'sourceMerge.append' : 'sourceMerge.replace')}
        </button>
        {extension && <button type="button" disabled={disabled} className="rounded-card border border-border px-3 py-2 text-sm" onClick={() => {
          if (isCurrent()) reset();
        }}>{t('sourceMerge.cancelExtension')}</button>}
      </div>
      {!!draft.field_sources?.length && <div className="space-y-2 border-t border-border pt-3">
        <p className="text-xs font-medium">{t('sourceMerge.bound')}</p>
        <p className="text-xs text-text-secondary">{t('sourceMerge.reviewExtension')}</p>
        {draft.field_sources.map((binding, index) => {
          const bound = draft.source_documents?.find(ref => ref.material_id === binding.material_id && ref.document_id === binding.document_id);
          const field = binding.field;
          const values = field === 'actions' || field === 'results' ? draft[field].split(/\r?\n/).map(value => value.trim()).filter(Boolean) : [];
          const position: EvidenceFactPosition | null = (field === 'actions' || field === 'results') &&
            values.filter(value => value === binding.value).length === 1
            ? {field, index: values.indexOf(binding.value), value: binding.value} : null;
          return <div className="space-y-1" key={index}>
            <p className="break-words text-xs text-text-secondary">{t('pages.evidence.fields.' + labels[field])}：{binding.value}<br/>{bound?.label}</p>
            {position && bound && <button type="button" disabled={disabled} className="text-xs text-accent disabled:opacity-40" onClick={() => {
              if (!isCurrent()) return;
              invalidate();
              setReview({...emptyReview, extension: {position, binding}, field: position.field, material: binding.material_id, quote: binding.quote});
            }}>{t('sourceMerge.extend')}</button>}
          </div>;
        })}
      </div>}
    </div>
  </details>;
}
