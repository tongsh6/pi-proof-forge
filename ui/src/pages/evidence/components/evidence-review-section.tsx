import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { EvidenceDraftPayload, EvidenceFactAttribution, EvidenceFactPosition, EvidenceFactScopeProjection, EvidenceFactScopeReview, EvidenceFactScopeSource, EvidenceFactImplementation, EvidenceFactRelease, EvidenceFactEnvironment } from "@/lib/sidecar/types";
import { EvidenceStatusBadge } from "./evidence-status-badge";

type EvidenceReviewSectionProps = {
  generatedDraft: EvidenceDraftPayload;
  reviewMissingItems: (string | false)[];
  busy: boolean;
  scopeDraft?: EvidenceDraftPayload;
  sourceError?: string;
  reviewedScopes?: EvidenceFactScopeProjection[];
  onSaveReviewedDraft: (saveMode: "incomplete" | "eligible", factScope?: EvidenceFactScopeReview) => void;
};

function scopeOptions(draft:EvidenceDraftPayload|undefined): (EvidenceFactPosition & {source:EvidenceFactScopeSource})[]{
  if(!draft)return [];
  return (["actions","results"] as const).flatMap(field=>{
    const values=draft[field];
    return values.flatMap((value,index)=>{
      if(values.filter(item=>item===value).length!==1)return [];
      return (draft.field_sources??[]).flatMap(binding=>{
        if(binding.field!==field||binding.value!==value)return [];
        const ref=draft.source_documents?.find(doc=>doc.material_id===binding.material_id&&doc.document_id===binding.document_id);
        if(!ref)return [];
        return [{field,index,value,source:{material_id:ref.material_id,document_id:ref.document_id,sha256:ref.sha256,quote:binding.quote}}];
      });
    });
  });
}

/** 模型草稿/重审区：缺失项提示与「保存不完整/保存合格」两个保存动作。 */
export function EvidenceReviewSection({
  generatedDraft,
  scopeDraft,
  sourceError,
  reviewedScopes,
  reviewMissingItems,
  busy,
  onSaveReviewedDraft,
}: EvidenceReviewSectionProps) {
  const { t } = useTranslation();
  const [key,setKey]=useState(""),[target,setTarget]=useState("");
  const [attribution,setAttribution]=useState<EvidenceFactAttribution>("unknown");
  const [environment,setEnvironment]=useState<EvidenceFactEnvironment>("unknown");
  const [implementation,setImplementation]=useState<EvidenceFactImplementation>("unknown");
  const [release,setRelease]=useState<EvidenceFactRelease>("unknown");
  const options=scopeOptions(scopeDraft);
  const chosen=options.find(item=>JSON.stringify(item)===key);
  const revocable=chosen&&(sourceError==="fact_scope_source_not_unique"||
    reviewedScopes?.some(row=>row.field===chosen.field&&row.index===chosen.index&&row.value===chosen.value));
  const obj=target.trim().replace(/\s+/g," ");
  const invalid=!obj||(attribution==="unknown"&&implementation==="unknown"&&release==="unknown")||
    (environment==="unknown"&&release!=="unknown")||
    (["planned","not_implemented"].includes(implementation)&&release==="released");
  const locked=busy||!!reviewMissingItems.length;

  return (
    <section className="rounded-card border border-success/40 bg-success/10 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">
            {t("pages.evidence.review.title")}
          </p>
          <p className="mt-1 text-xs text-text-secondary">
            {t("pages.evidence.review.source", {
              count: generatedDraft.source_material_ids.length,
            })}
          </p>
        </div>
        <EvidenceStatusBadge
          status={
            reviewMissingItems.length
              ? "draft_incomplete"
              : "draft_ready_for_review"
          }
        />
      </div>
      {reviewMissingItems.length ? (
        <p className="mt-3 text-xs text-warning">
          {t("pages.evidence.review.missing", {
            items: reviewMissingItems.join(", "),
          })}
        </p>
      ) : (
        <p className="mt-3 text-xs text-success">
          {t("pages.evidence.review.eligible")}
        </p>
      )}
      {!!options.length&&<details className="mt-3 space-y-2 text-sm" data-testid="fact-scope-review">
        <summary>{t("factScope.title")}</summary>
        {reviewedScopes?.map((row,index)=><p key={row.fact_id+":"+index}>{row.value} · {t("factScope."+row.attribution)} · {row.target} · {t("factScope."+row.environment)} · {t("factScope."+row.implementation)} · {t("factScope."+row.release)}</p>)}
        <p>{t("factScope.hint")}</p>
        <select aria-label={t("factScope.fact")} value={key} disabled={busy} onChange={e=>{
          setKey(e.target.value);setAttribution("unknown");setTarget("");setEnvironment("unknown");setImplementation("unknown");setRelease("unknown");
        }}>
          <option value="">{t("factScope.choose")}</option>
          {options.map((item,index)=><option key={index} value={JSON.stringify(item)}>{item.value} · {item.source.quote}</option>)}
        </select>
        {chosen&&<>
          <blockquote>{chosen.source.quote}</blockquote>
          <select aria-label={t("factScope.attribution")} value={attribution} disabled={busy} onChange={e=>setAttribution(e.target.value as EvidenceFactAttribution)}>
            {(["unknown","self","team_lead","contributor","teammate"] as const).map(value=><option key={value} value={value}>{t("factScope."+value)}</option>)}
          </select>
          <label>{t("factScope.target")} <input aria-label={t("factScope.target")} maxLength={160} value={target} disabled={busy} onChange={e=>setTarget(e.target.value)}/></label>
          <select aria-label={t("factScope.env")} disabled={busy} value={environment} onChange={e=>setEnvironment(e.target.value as EvidenceFactEnvironment)}>
            {(["unknown","test","staging","production"] as const).map(value=><option key={value} value={value}>{t("factScope."+value)}</option>)}
          </select>
          <select aria-label={t("factScope.implementation")} disabled={busy} value={implementation} onChange={e=>setImplementation(e.target.value as EvidenceFactImplementation)}>
            {(["unknown","implemented","planned","not_implemented"] as const).map(value=><option key={value} value={value}>{t("factScope."+value)}</option>)}
          </select>
          <select aria-label={t("factScope.release")} disabled={busy||environment==="unknown"} value={release} onChange={e=>setRelease(e.target.value as EvidenceFactRelease)}>
            {(["unknown","released","not_released"] as const).map(value=><option key={value} value={value}>{t("factScope."+value)}</option>)}
          </select>
          <button type="button" disabled={locked||invalid} onClick={()=>{
            if(!locked&&!invalid)onSaveReviewedDraft("eligible",{...chosen,kind:"adopt",attribution,target:obj,environment,implementation,release});
          }}>{t("factScope.adopt")}</button>
          {revocable&&<button type="button" disabled={locked} onClick={()=>{
            if(!locked)onSaveReviewedDraft("eligible",{kind:"revoke",field:chosen.field,index:chosen.index,value:chosen.value});
          }}>{t("factScope.revoke")}</button>}
        </>}
      </details>}
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        <button
          className="rounded-card border border-border px-3 py-2 text-sm text-text-primary transition-colors hover:bg-bg-hover disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={() => onSaveReviewedDraft("incomplete")}
          type="button"
        >
          {t("pages.evidence.actions.saveIncomplete")}
        </button>
        <button
          className="rounded-card border border-success bg-success px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          disabled={busy}
          onClick={() => onSaveReviewedDraft("eligible")}
          type="button"
        >
          {t("pages.evidence.actions.saveEligible")}
        </button>
      </div>
    </section>
  );
}
