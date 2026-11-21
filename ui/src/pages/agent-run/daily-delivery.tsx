import {useEffect,useRef,useState} from "react";
import {useTranslation} from "react-i18next";
import {useNavigate} from "react-router-dom";
import {getErrorMessage} from "@/lib/errors";
import {buttonClass,confirmAction,notify} from "@/lib/ui";
import {previewDailyPreparation,type PreparationInternalPreview,matchDailyPreparation,type PreparationSemanticMatch,assessDailyPreparation,type PreparationAssessment,type PreparationRecoveryAction,replenishDailyPreparation,type PreparationReplenishment,getDailyPreparation,type DailyPreparation,getDailyStatus,previewDailyPdf,saveDailyDraft,changeDailyAuthorization,runDailyDelivery,closeInterruptedDaily,type DailyStatus} from "@/lib/sidecar/api";

function localInput(date:Date){return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}
type PreviewState={kind:"pending"}|{kind:"error";code:string}|{kind:"result";value:PreparationInternalPreview};
function canRequestInternalPreview(result:PreparationSemanticMatch|null|undefined):boolean{
  return result?.status==="partial"&&result.input_fresh&&result.match_outcome?.usable_current_result!==false;
}
const recoveryLabels={
  resume_assessment:{testId:"resume-assessment",label:"resumeAssessment"},
  start_matching:{testId:"start-matching",label:"startMatching"},
  recheck_matching:{testId:"recheck-matching",label:"recheckMatching"},
  continue_matching:{testId:"continue-matching",label:"continueMatching"},
} as const;
function readRecoveryAction(value:unknown):PreparationRecoveryAction|null{
  if(!value||typeof value!=="object"||Array.isArray(value))return null;
  const data=value as Record<string,unknown>;
  const keys=Object.keys(data);
  if((data.kind==="resume_assessment"||data.kind==="start_matching")&&keys.length===1)return {kind:data.kind};
  if((data.kind==="recheck_matching"||data.kind==="continue_matching")&&keys.length===2&&typeof data.audit_digest==="string"&&/^[0-9a-f]{64}$/.test(data.audit_digest)){
    return {kind:data.kind,audit_digest:data.audit_digest};
  }
  return null;
}
export function DailyDeliveryPanel(){
  const {t}=useTranslation();
  const navigate=useNavigate();
  const [data,setData]=useState<DailyStatus|null>(null),[selected,setSelected]=useState<string[]>([]);
  const [maximum,setMaximum]=useState(3),[time,setTime]=useState("09:00"),[expiry,setExpiry]=useState(()=>localInput(new Date(Date.now()+7*86400000)));
  const [consent,setConsent]=useState(false),[dirty,setDirty]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [preparation,setPreparation]=useState<DailyPreparation|null>(null);
  const currentRecovery=useRef({plan:preparation,busy});
  currentRecovery.current={plan:preparation,busy};
  const [preparationError,setPreparationError]=useState("");
  const [preparationVersion,setPreparationVersion]=useState(0);
  const [refillBusy,setRefillBusy]=useState(false);
  const [refillResult,setRefillResult]=useState<PreparationReplenishment|null>(null);
  const [refillError,setRefillError]=useState("");
  const [assessmentTitle,setAssessmentTitle]=useState("");
  const [assessments,setAssessments]=useState<{job_profile_id:string;company:string;title:string;result?:PreparationAssessment;error?:string}[]>([]);
  const [semanticResults,setSemanticResults]=useState<{job_profile_id:string;result:PreparationSemanticMatch}[]>([]);
  const refillLock=useRef(false),refillVersion=useRef(0),refillMounted=useRef(true);
  const [internalPreviews,setInternalPreviews]=useState<Record<string,PreviewState>>({});
  const previewRequests=useRef(new Map<string,symbol>());
  const resetPreviews=()=>{previewRequests.current.clear();setInternalPreviews({});};
  const refreshPreparation=()=>{
    if(refillLock.current)return;
    currentRecovery.current={...currentRecovery.current,plan:null};
    resetPreviews();
    setSemanticResults([]);
    setPreparation(null);
    setPreparationError("");
    setPreparationVersion(v=>v+1);
  };
  const loadInternalPreview=async(id:string)=>{
    if(!refillMounted.current||previewRequests.current.has(id))return;
    const request=Symbol();
    previewRequests.current.set(id,request);
    const current=()=>refillMounted.current&&previewRequests.current.get(id)===request;
    setInternalPreviews(rows=>({...rows,[id]:{kind:"pending"}}));
    try{
      const value=await previewDailyPreparation(id);
      if(!current())return;
      const valid=value?.job_profile_id===id&&value.scope==="internal_targeted_excerpt"&&value.partial===true&&
        value.deliverable===false&&value.send_ready===false&&value.active_target_eligible===false&&value.model_calls===0&&
        (value.status==="preview"||value.status==="blocked")&&typeof value.input_fresh==="boolean"&&
        typeof value.markdown==="string"&&typeof value.code==="string"&&
        Array.isArray(value.claims)&&value.claims.every(claim=>claim&&typeof claim.fact_id==="string"&&
          typeof claim.source_id==="string"&&typeof claim.quote==="string"&&
          (claim.usage==="supported_excerpt"||claim.usage==="context"))&&
        Array.isArray(value.limitations)&&value.limitations.every(item=>item&&typeof item.requirement_id==="string"&&
          typeof item.text==="string"&&typeof item.status==="string"&&typeof item.reason==="string");
      setInternalPreviews(rows=>({...rows,[id]:valid?{kind:"result",value}:{kind:"error",code:"preview_mismatch"}}));
    }catch{
      if(current())setInternalPreviews(rows=>({...rows,[id]:{kind:"error",code:"preview_unavailable"}}));
    }finally{
      if(current())previewRequests.current.delete(id);
    }
  };
  useEffect(()=>{refillMounted.current=true;return()=>{refillMounted.current=false;previewRequests.current.clear();};},[]);
  useEffect(()=>{
    refillVersion.current++;resetPreviews();
    setRefillResult(null);setRefillError("");setAssessments([]);setSemanticResults([]);setAssessmentTitle("");
    return()=>{refillVersion.current++;};
  },[maximum]);
  const matchSource=async(item:Pick<DailyPreparation["deferred"][number],"job_profile_id"|"company"|"title">,
                          version:number,maximumRounds:number,contractDigest?:string,initialContinuation?:string)=>{
    let lastMatch:PreparationSemanticMatch|undefined;
    let continuationDigest=initialContinuation;
    for(let round=0;round<maximumRounds;round++){
      if(!refillMounted.current||version!==refillVersion.current)return;
      setAssessmentTitle(item.company+' · '+item.title+' · '+t('daily.preparation.semanticProgress',{round:round+1}));
      let matching:PreparationSemanticMatch;
      try{matching=await matchDailyPreparation(item.job_profile_id,round===0&&!contractDigest&&!continuationDigest,contractDigest,continuationDigest);}
      catch(e){matching={status:'blocked',code:getErrorMessage(e),scope:'advisory_partial',input_fresh:false,send_ready:false};}
      if(!refillMounted.current||version!==refillVersion.current)return;
      setSemanticResults(previous=>[...previous.filter(row=>row.job_profile_id!==item.job_profile_id),{job_profile_id:item.job_profile_id,result:matching}]);
      lastMatch=matching;
      if(!matching.continuation_needed||matching.status!=='partial'||!matching.input_fresh||
         typeof matching.continuation_digest!=='string'||!/^[0-9a-f]{64}$/.test(matching.continuation_digest))break;
      continuationDigest=matching.continuation_digest;
    }
    if(canRequestInternalPreview(lastMatch)&&refillMounted.current&&version===refillVersion.current){
      await loadInternalPreview(item.job_profile_id);
    }
  };
  const assessSource=async(item:Pick<DailyPreparation["deferred"][number],"job_profile_id"|"company"|"title">,version:number,resumeSourceOnly=false)=>{
    setAssessmentTitle(item.company+' · '+item.title);
    try{
      const assessment=await assessDailyPreparation(item.job_profile_id,resumeSourceOnly);
      if(!refillMounted.current||version!==refillVersion.current)return;
      setAssessments(previous=>[...previous.filter(row=>row.job_profile_id!==item.job_profile_id),{...item,result:assessment}]);
      if(assessment.status==='prepared'&&assessment.requirements_grounded){
        await matchSource(item,version,3);
      }
    }catch(e){
      if(!refillMounted.current||version!==refillVersion.current)return;
      setAssessments(previous=>[...previous.filter(row=>row.job_profile_id!==item.job_profile_id),{...item,error:getErrorMessage(e)}]);
    }
  };
  const recover=async(id:string,clicked:PreparationRecoveryAction)=>{
    const {plan,busy:currentBusy}=currentRecovery.current;
    if(!refillMounted.current||refillLock.current||currentBusy||!plan)return;
    const rows=plan.deferred.filter(row=>row.job_profile_id===id);
    if(rows.length!==1||plan.selected.some(row=>row.job_profile_id===id))return;
    const item=rows[0], action=readRecoveryAction(item.recovery_action);
    if(!action||action.kind!==clicked.kind||
       ("audit_digest" in action&&(!("audit_digest" in clicked)||action.audit_digest!==clicked.audit_digest)))return;
    refillLock.current=true;setRefillBusy(true);
    // The recovery can replace this job's audit; a pending read belongs to the old one.
    previewRequests.current.delete(id);
    setInternalPreviews(rows=>{
      if(!(id in rows))return rows;
      const retained={...rows};
      delete retained[id];
      return retained;
    });
    const version=refillVersion.current;
    try{
      if(action.kind==="resume_assessment")await assessSource(item,version,true);
      else await matchSource(item,version,1,action.kind==="recheck_matching"?action.audit_digest:undefined,
                             action.kind==="continue_matching"?action.audit_digest:undefined);
    }finally{
      refillLock.current=false;
      if(refillMounted.current){setRefillBusy(false);setAssessmentTitle("");setPreparationVersion(v=>v+1);}
    }
  };
  const replenish=async()=>{
    if(refillLock.current||busy||!preparation||preparation.shortfall<=0)return;
    refillLock.current=true;setRefillBusy(true);resetPreviews();setRefillResult(null);setRefillError("");setAssessments([]);setSemanticResults([]);setAssessmentTitle("");
    const version=refillVersion.current;
    try{
      const result=await replenishDailyPreparation(maximum);
      if(!refillMounted.current||version!==refillVersion.current)return;
      setRefillResult(result);
      const seen=new Set<string>();
      const batch=result.source_prepared.filter(item=>{
        if(!item.job_profile_id||seen.has(item.job_profile_id))return false;
        seen.add(item.job_profile_id);return true;
      }).slice(0,Math.min(maximum,3));
      for(const item of batch){
        if(!refillMounted.current||version!==refillVersion.current)break;
        await assessSource(item,version);
      }
    }catch(e){if(version===refillVersion.current)setRefillError(getErrorMessage(e));}
    finally{
      refillLock.current=false;
      if(refillMounted.current){setRefillBusy(false);setAssessmentTitle("");setPreparationVersion(v=>v+1);}
    }
  };
  useEffect(()=>{
    let alive=true;
    currentRecovery.current={...currentRecovery.current,plan:null};
    setPreparation(null);setPreparationError("");
    void getDailyPreparation(maximum).then(plan=>{if(alive)setPreparation(plan);})
      .catch(e=>{if(alive)setPreparationError(getErrorMessage(e));});
    return()=>{alive=false;};
  },[maximum,preparationVersion]);
  const [preview,setPreview]=useState("");
  useEffect(()=>{
    let alive=true;
    const load=async(initial=false)=>{try{const next=await getDailyStatus();if(!alive)return;setData(next);
      if(initial&&next.authorization){const a=next.authorization;setSelected(a.scope.map(i=>i.run_id));setMaximum(a.maximum);setTime(a.time);setExpiry(localInput(new Date(a.expires_at)));setDirty(false);}
    }catch(e){if(alive)setError(getErrorMessage(e));}};
    void load(true);const timer=window.setInterval(()=>void load(),15000);
    return()=>{alive=false;window.clearInterval(timer);};
  },[]);
  const internalPreview=(id:string)=>{
    const row=internalPreviews[id];
    if(!row)return null;
    const value=row.kind==="result"?row.value:null;
    const excerpt=value?.status==="preview"&&value.input_fresh&&value.preview_fact_count>0&&value.markdown.trim()?value:null;
    return <section data-testid={'daily-preview-result-'+id} className="space-y-1 text-xs">
      <p>{t('daily.preparation.internalPreview.title')} · {t('daily.preparation.internalPreview.boundary')}</p>
      {row.kind==="pending"?<p role="status">{t('daily.preparation.internalPreview.loading')}</p>:<p>{excerpt?t('daily.preparation.internalPreview.available'):t('daily.preparation.internalPreview.reasons.'+(row.kind==="error"?row.code:row.value.code),{defaultValue:t('daily.preparation.internalPreview.unavailable')})}</p>}
      {excerpt&&<>
        <pre data-testid={'daily-preview-markdown-'+id} className="max-h-64 overflow-y-auto whitespace-pre-wrap break-words font-sans">{excerpt.markdown}</pre>
        {!!excerpt.claims.length&&<details><summary>{t('daily.preparation.internalPreview.sources')}</summary>{excerpt.claims.map((claim,index)=><p key={claim.fact_id+':'+index}>{t('daily.preparation.internalPreview.'+claim.usage)} · {claim.source_id} · {claim.quote}</p>)}</details>}
      </>}
      {value?.input_fresh&&!!value.limitations.length&&<details><summary>{t('daily.preparation.internalPreview.limitations')}</summary>{value.limitations.map((item,index)=><p key={item.requirement_id+':'+index}>{item.text||item.requirement_id} · {t('daily.preparation.supportStates.'+item.status,{defaultValue:item.status})} · {item.reason}</p>)}</details>}
    </section>;
  };
  const semanticSummary=(result:PreparationSemanticMatch,id:string)=><div data-testid={'daily-semantic-'+id} className="space-y-1 text-xs">
    <p>{t(result.status==='partial'&&result.match_outcome?.usable_current_result===false
      ? 'daily.preparation.semanticOutcome.noUsable' : 'daily.preparation.semanticStates.'+
      (result.status==='partial'&&!result.input_fresh?'stale':result.status))} · {t('daily.preparation.semanticLimitation')}</p>
    <p>{t('daily.preparation.reasons.'+result.code,{defaultValue:result.code})}</p>
    {result.match_outcome&&<div data-testid={'daily-semantic-outcome-'+id}>
      <p>{t('daily.preparation.semanticOutcome.engines.'+result.match_outcome.engine)}
        {result.match_outcome.reason&&result.match_outcome.reason!==result.code?' · '+t('daily.preparation.reasons.'+result.match_outcome.reason):''}</p>
      {result.match_outcome.stop_causes.map(cause=><p key={cause}>{t('daily.preparation.semanticOutcome.stops.'+cause)}</p>)}
      {result.input_fresh&&<p>{t('daily.preparation.semanticOutcome.checks',{count:result.match_outcome.completed_check_count})}</p>}
    </div>}
    {result.status==='partial'&&result.input_fresh&&<>
      {!result.match_outcome&&<p>{t('daily.preparation.semanticOutcome.notRecorded')}</p>}
      {typeof result.cache_progress_count==='number'&&<p>{t('daily.preparation.semanticCacheProgress',{count:result.cache_progress_count})}</p>}
      {result.assessment_schedule?.policy==='pending_source_requirements_v1'&&<p>{t('daily.preparation.semanticSchedule')}</p>}
      {result.assessment_schedule?.section_policy==='explicit_numbered_section_v1'&&<p>{t('daily.preparation.semanticSectionSchedule')}</p>}
      {result.coverage_known===false?<p>{t('daily.preparation.semanticCoverageUnknown')}</p>:<p>{t('daily.preparation.semanticCoverage',{reviewed:result.reviewed_card_count??0,total:result.eligible_card_count??0,cards:result.degraded_card_count??0,checks:result.degraded_check_count??0})}</p>}
      {result.coverage_known!==false&&((result.deferred_card_count??0)>0||(result.deferred_check_count??0)>0)&&<p>{t('daily.preparation.semanticDeferred',{cards:result.deferred_card_count??0,checks:result.deferred_check_count??0})}</p>}
      {!!result.assessments?.length&&<details><summary>{t('daily.preparation.semanticFindings')}</summary>{result.assessments.map(row=><div key={row.requirement_id} className="mt-2">
        <p>{row.requirement_text||row.requirement_id} · {t('daily.preparation.supportStates.'+row.status,{defaultValue:row.status})}</p><p>{row.reason}</p>
        {row.citations?.map((citation,index)=><p key={citation.fact_id+':'+index}>{citation.fact_id}：{citation.text||citation.quote}{citation.candidate_support===false&&<> · {t('daily.preparation.semanticCandidateLimitation')}</>}</p>)}
      </div>)}</details>}
      {result.continuation_needed&&<p>{t('daily.preparation.semanticPending')}</p>}
    </>}
  </div>;
  const a=data?.authorization,editable=!a||["draft","revoked"].includes(a.state),running=data?.history.find(h=>h.state==="running");
  const recoveryIds=new Set(data?.history.flatMap(h=>(h.items||[]).filter(item=>item.recovery_required).map(item=>item.run_id))||[]);
  const recoveryBlocked=Boolean(data?.recovery_required)||Boolean(data?.today.unresolved)||Boolean(a?.scope.some(item=>recoveryIds.has(item.run_id)));
  const errorText=(error:unknown)=>{const message=getErrorMessage(error);const code=message.match(/\b(?:daily_[a-z_]+|quick_official_target_changed|NATIVE_OPERATION_BUSY)\b/)?.[0];return code?t('daily.reasons.'+code,{defaultValue:message}):message;};
  const edit=()=>{setDirty(true);setConsent(false);};
  // confirmKey 对应 confirmations.daily.*，有值时先弹确认框；successKey 对应 toasts.daily.*。
  const act=async(fn:()=>Promise<unknown>,options:{confirmKey?:string;successKey?:string}={})=>{
    if(options.confirmKey&&!(await confirmAction({title:t(`confirmations.daily.${options.confirmKey}.title`),description:t(`confirmations.daily.${options.confirmKey}.description`),confirmLabel:t(`confirmations.daily.${options.confirmKey}.confirm`),tone:'danger'})))return;
    setBusy(true);setError("");setNotice("");try{const result=await fn();if(result&&typeof result==='object'&&'reason'in result)setNotice(String(result.reason));setData(await getDailyStatus());setConsent(false);if(options.successKey)notify('success',t(`toasts.daily.${options.successKey}`));}catch(e){setError(errorText(e));}finally{setBusy(false);}};
  const inputClass="rounded-card border border-border bg-bg-primary p-2 text-sm disabled:opacity-50";
  const secondary=buttonClass.secondary;
  // 每个按钮的禁用原因，用于 title 提示。
  const reason=(key:string)=>t(`reasons.daily.${key}`);
  const saveReason=!editable?reason('notEditable'):!dirty?reason('nothingToSave'):'';
  const activateReason=dirty?reason('dirty'):!a||!['draft','paused'].includes(a.state)?reason('notActivatable'):!a.scope.length?reason('noScope'):recoveryBlocked?reason('recovery'):!consent?reason('consent'):'';
  const runReason=a?.state!=='active'?reason('notActive'):running?reason('running'):recoveryBlocked?reason('recovery'):'';
  // 按授权状态只突出一个主按钮：已启用 → 执行今日批次；有未保存修改 → 保存草稿；否则 → 确认并启用。
  const primaryAction=a?.state==='active'?'run':(editable&&dirty)?'save':'activate';
  return <section data-testid="daily-panel" className="space-y-4 rounded-panel border border-border bg-bg-panel p-5">
    <section data-testid="daily-preparation-plan" className="space-y-2 rounded-card border border-border p-3">
      <div className="flex justify-between gap-2"><h3>{t('daily.preparation.title')}</h3>
        <button type="button" className={buttonClass.ghost} disabled={refillBusy} onClick={refreshPreparation}>{t('daily.preparation.refresh')}</button></div>
      <p className="text-xs text-text-secondary">{t('daily.preparation.limitation')}</p>
      <button type="button" data-testid="daily-replenish" className={buttonClass.ghost}
        disabled={refillBusy||busy||!preparation||preparation.shortfall<=0}
        onClick={()=>void replenish()}>{t(refillBusy?'daily.preparation.refilling':'daily.preparation.refill')}</button>
      <p className="text-xs text-text-secondary">{t('daily.preparation.refillLimitation')}</p>
      {refillError&&<p role="alert">{refillError}</p>}
      {assessmentTitle&&<p data-testid="daily-assessing" role="status">{t('daily.preparation.assessing')} · {assessmentTitle}</p>}
      {assessments.map(item=><div key={item.job_profile_id} data-testid={'daily-assessment-'+item.job_profile_id} className="space-y-1 rounded-card border border-border p-2 text-sm">
        <p>{item.company} · {item.title}</p>
        <p>{t('daily.preparation.unapproved')}</p>
        {item.error?<p role="alert">{item.error}</p>:item.result&&<>
          <p>{t('daily.preparation.assessmentStates.'+item.result.status)}</p>
          <p>{t('daily.preparation.reasons.'+item.result.code,{defaultValue:item.result.code})}</p>
          <p>{t('daily.preparation.directionLabel')}：{t('daily.preparation.directions.'+(item.result.direction?.status||'unavailable'))}</p>
          {item.result.direction&&<><p>{item.result.direction.reason}</p><blockquote>{item.result.direction.jd_quote}</blockquote></>}
          <p>{t(item.result.status==='deferred'?'daily.preparation.groundingDeferred':item.result.requirements_grounded?'daily.preparation.grounded':'daily.preparation.notGrounded',{count:item.result.requirement_count})}</p>
        </>}
      </div>)}
      {semanticResults.map(row=><div key={row.job_profile_id}>{semanticSummary(row.result,row.job_profile_id)}{canRequestInternalPreview(row.result)&&internalPreview(row.job_profile_id)}</div>)}
      {refillResult&&<div data-testid="daily-replenish-result" role="status" className="space-y-1 text-sm">
        <p>{t('daily.preparation.refillSummary',{received:refillResult.received_count,prepared:refillResult.source_prepared_count})} · {t('daily.preparation.refillStates.'+refillResult.status)}</p>
        {refillResult.code&&<p>{t('daily.preparation.reasons.'+refillResult.code,{defaultValue:refillResult.code})}</p>}
        {refillResult.source_prepared.map(item=><p key={item.job_lead_id}>{item.company} · {item.title}</p>)}
        {refillResult.deferred.map((item,i)=><p key={'defer-'+i}>{item.job_lead_id}：{t('daily.preparation.reasons.'+item.reason,{defaultValue:item.reason})}</p>)}
        {refillResult.errors.map((item,i)=>{
          const fallback=t('daily.preparation.reasons.'+item.code,{defaultValue:item.code});
          const label=item.stage==='detail'&&item.code!=='SECURITY_CHALLENGE'
            ? t(item.code==='JOB_DETAIL_UNAVAILABLE'&&item.detail_reason
                ? 'pages.jobs.liepinDetail.reasons.'+item.detail_reason : 'pages.jobs.liepinDetail.codes.'+item.code,
                {defaultValue:fallback}) : fallback;
          return <p key={'error-'+i}>{item.job_lead_id?item.job_lead_id+' · ':''}{item.stage}：{label}</p>;
        })}
      </div>}
      {preparationError?<p role="alert">{preparationError}</p>:!preparation?<p>{t('daily.preparation.loading')}</p>:<>
        <p>{t('daily.preparation.summary',{selected:preparation.selected.length,maximum:preparation.maximum,shortfall:preparation.shortfall})}</p>
        {preparation.selected.map(item=><div key={item.job_profile_id} className="rounded-card border border-border p-2 text-sm">
          <p>{item.company} · {item.title} · {t('daily.preparation.channels.'+item.channel)}</p>
          <p>{t('daily.preparation.reasons.'+item.reason,{defaultValue:item.reason})}</p>
          <button type="button" data-testid={'daily-preparation-'+item.job_profile_id} className={buttonClass.link}
            onClick={()=>navigate('/quick-run?job_profile_id='+encodeURIComponent(item.job_profile_id))}>{t('daily.preparation.open')}</button>
        </div>)}
        <details><summary>{t('daily.preparation.deferred')} ({preparation.deferred.length})</summary>
          {preparation.deferred.map((item,index)=><div key={item.job_profile_id+':'+index} className="space-y-1 rounded-card border border-border p-2 text-xs">
            <p>{item.company} · {item.title}：{t('daily.preparation.reasons.'+item.reason,{defaultValue:item.reason})}</p>
            {(() => {
              const action=readRecoveryAction(item.recovery_action);
              if(!action)return null;
              const {testId,label}=recoveryLabels[action.kind];
              return <button type="button" data-testid={'daily-'+testId+'-'+item.job_profile_id}
                className={buttonClass.link} disabled={refillBusy||busy}
                onClick={()=>void recover(item.job_profile_id,action)}>{t('daily.preparation.'+label)}</button>;
            })()}
            {item.preparation&&item.preparation.state!=='absent'&&<div data-testid={'daily-saved-preparation-'+item.job_profile_id}>
              <p>{t('daily.preparation.savedStates.'+item.preparation.state)} · {t('daily.preparation.savedInputOnly')}</p>
              {item.preparation.state==='fresh'?<>
                {item.preparation.direction&&<p>{t('daily.preparation.directions.'+item.preparation.direction.status)}：{item.preparation.direction.reason}</p>}
                <p>{t(item.preparation.requirements_grounded?'daily.preparation.grounded':item.preparation.direction?.status==='excluded'?'daily.preparation.groundingDeferred':'daily.preparation.notGrounded',{count:item.preparation.requirement_count})}</p>
                {item.preparation.semantic_matching&&semanticSummary(item.preparation.semantic_matching,'saved-'+item.job_profile_id)}
                {canRequestInternalPreview(item.preparation.semantic_matching)&&!semanticResults.some(row=>row.job_profile_id===item.job_profile_id)&&<>
                  <button type="button" data-testid={'daily-preview-open-'+item.job_profile_id} className={buttonClass.link}
                    disabled={refillBusy||internalPreviews[item.job_profile_id]?.kind==='pending'}
                    onClick={()=>void loadInternalPreview(item.job_profile_id)}>{t('daily.preparation.internalPreview.open')}</button>
                  {internalPreview(item.job_profile_id)}
                </>}
                {item.preparation.evidence_precheck&&<>
                  <p>{t('daily.preparation.precheckStates.'+item.preparation.evidence_precheck.state,{defaultValue:item.preparation.evidence_precheck.state})}</p>
                  <p>{t('daily.preparation.evidenceOverlap',{matched:item.preparation.evidence_precheck.matched_requirements??0,total:item.preparation.evidence_precheck.total_requirements??0,hits:item.preparation.evidence_precheck.evidence_hits??0})}</p>
                  <p>{t('daily.preparation.overlapOnly')}</p>
                  {!!item.preparation.evidence_precheck.source_freshness_unverified_count&&<p>{t('daily.preparation.legacySources',{count:item.preparation.evidence_precheck.source_freshness_unverified_count})}</p>}
                </>}
              </>:<p>{t('daily.preparation.savedNeedsRefresh')}</p>}
            </div>}
          </div>)}
        </details>
      </>}
    </section>

    <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{t('daily.title')}</h2><button type="button" className={buttonClass.ghost} disabled={busy} onClick={()=>void act(async()=>getDailyStatus())}>{t('daily.refresh')}</button></div>
    {data&&<p className="text-sm">{t('daily.today')} {data.today.day} · {t('daily.confirmed')} {data.today.confirmed}/3 · {t('daily.occupied')} {data.today.occupied} · {t('daily.state')} {t(`daily.states.${a?.state||'none'}`)}</p>}
    <div className="text-sm text-text-secondary">{t('daily.descriptionShort')}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t('common.learnMore')}</summary><p className="mt-1">{t('daily.description')}</p></details></div>
    <details open={editable} className="rounded-card border border-border">
    <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">{t('daily.settings')}{!editable&&<span className="ml-2 text-xs font-normal text-text-muted">{t('daily.maximum')} {maximum} · {t('daily.time')} {time}</span>}</summary>
    <div className="flex flex-wrap gap-4 px-3 pb-3">
      <label>{t('daily.maximum')} <select aria-label={t('daily.maximum')} className={inputClass} value={maximum} disabled={!editable||busy||refillBusy} onChange={e=>{setMaximum(Number(e.target.value));edit();}}>{[1,2,3].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
      <label>{t('daily.time')} <input aria-label={t('daily.time')} className={inputClass} type="time" value={time} disabled={!editable||busy} onChange={e=>{setTime(e.target.value);edit();}}/></label>
      <label>{t('daily.expiry')} <input aria-label={t('daily.expiry')} className={inputClass} type="datetime-local" value={expiry} disabled={!editable||busy} onChange={e=>{setExpiry(e.target.value);edit();}}/></label>
    </div>
    </details>
    <p className="text-sm text-text-secondary">{t('daily.scope')}</p>
    <div className="max-h-64 space-y-2 overflow-y-auto">{(editable?data?.candidates:a?.scope)?.map(item=><div key={item.run_id} className="rounded-card border border-border p-3 text-sm">
      <label className="flex gap-2"><input data-testid={`daily-candidate-${item.run_id}`} type="checkbox" checked={selected.includes(item.run_id)} disabled={!editable||busy} onChange={e=>{setSelected(v=>e.target.checked?[...v,item.run_id]:v.filter(x=>x!==item.run_id));edit();}}/>{item.company} · {item.position} {item.matching_score!=null?`· ${item.matching_score}/100`:''}</label>
      {item.pdf_filename&&<p className="mt-1 break-all">PDF: {item.pdf_filename}</p>}
      <p className="mt-1 font-mono text-xs text-text-muted" title={item.pdf_sha256}>{t('daily.fingerprint')}: {item.pdf_sha256.slice(0,12)}…</p><button type="button" className={buttonClass.link} disabled={busy} onClick={()=>void act(async()=>{const pdf=await previewDailyPdf(item.run_id);if(pdf.pdf_sha256!==item.pdf_sha256)throw new Error("daily_scope_mismatch");setPreview("data:application/pdf;base64,"+pdf.pdf_base64);})}>{t('daily.preview')}</button>
    </div>)}</div>
    {!data?.candidates.length&&editable&&<div className="space-y-2 text-sm"><p className="text-warning">{t('daily.empty')}</p><button type="button" data-testid="daily-open-jobs" className={secondary} disabled={busy} onClick={()=>navigate('/jobs')}>{t('daily.openJobs')}</button></div>}
    {preview&&<div><button type="button" className={buttonClass.ghost} onClick={()=>setPreview("")}>{t('daily.closePreview')}</button><iframe title={t('daily.preview')} src={preview} className="mt-2 h-[600px] w-full rounded-card border border-border"/></div>}
    <label className="flex items-start gap-2 text-sm"><input data-testid="daily-consent" aria-label={t('daily.consent')} type="checkbox" checked={consent} disabled={busy||dirty||!a||!['draft','paused'].includes(a.state)} onChange={e=>setConsent(e.target.checked)}/><span>{t('daily.consentShort')}<details className="mt-1 text-xs font-normal text-text-muted"><summary className="cursor-pointer select-none text-accent">{t('common.fullTerms')}</summary><p className="mt-1">{t('daily.consent')}</p></details></span></label>
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" data-testid="daily-save" className={primaryAction==='save'?buttonClass.primary:secondary} disabled={busy||!editable||!dirty||!expiry||!time} title={saveReason||undefined} onClick={()=>void act(async()=>{await saveDailyDraft({run_ids:selected,maximum,time,expires_at:new Date(expiry).toISOString()});setDirty(false);},{successKey:'saved'})}>{t('daily.save')}</button>
      <button type="button" data-testid="daily-activate" className={primaryAction==='activate'?buttonClass.primary:secondary} disabled={busy||dirty||!consent||!a||!['draft','paused'].includes(a.state)||!a.scope.length||recoveryBlocked} title={activateReason||undefined} onClick={()=>void act(()=>changeDailyAuthorization(a!.id,'active',true),{successKey:'activated'})}>{t('daily.activate')}</button>
      <button type="button" data-testid="daily-run" className={primaryAction==='run'?buttonClass.primary:secondary} disabled={busy||a?.state!=='active'||!!running||recoveryBlocked} title={runReason||undefined} onClick={()=>void act(()=>runDailyDelivery(true),{confirmKey:'run',successKey:'triggered'})}>{t('daily.run')}</button>
      <details className="relative">
      <summary className={`${buttonClass.ghost} cursor-pointer list-none`}>{t('common.moreActions')}</summary>
      <div className="absolute left-0 z-10 mt-1 flex w-max max-w-[80vw] flex-wrap gap-2 whitespace-nowrap rounded-card border border-border bg-bg-panel p-2 shadow-[var(--shadow-card)]">
      <button type="button" data-testid="daily-pause" className={secondary} disabled={busy||!a||a.state!=='active'} title={!a||a.state!=='active'?reason('notPausable'):undefined} onClick={()=>void act(()=>changeDailyAuthorization(a!.id,'paused'),{successKey:'paused'})}>{t('daily.pause')}</button>
      <button type="button" data-testid="daily-revoke" className={buttonClass.danger} disabled={busy||!a||a.state==='revoked'} title={!a||a.state==='revoked'?reason('alreadyRevoked'):undefined} onClick={()=>void act(()=>changeDailyAuthorization(a!.id,'revoked'),{confirmKey:'revoke',successKey:'revoked'})}>{t('daily.revoke')}</button>
      {running&&<button type="button" data-testid="daily-close-interrupted" className={buttonClass.danger} disabled={busy} onClick={()=>void act(()=>closeInterruptedDaily(running.id),{confirmKey:'closeInterrupted',successKey:'closed'})}>{t('daily.closeInterrupted')}</button>}
      </div>
      </details>
    </div>
    {notice&&<p role="status" className="text-sm text-warning">{t(`daily.reasons.${notice}`,{defaultValue:notice})}</p>}
    {error&&<p role="alert" className="text-sm text-error">{error}</p>}
    {recoveryBlocked&&<p role="status" className="text-sm text-warning">{t('daily.recoveryHint')}</p>}
    {(data?.recovery_items||[]).filter(item=>!data?.history.some(h=>h.items?.some(i=>i.run_id===item.run_id))).map(item=><div key={item.run_id} className="flex flex-wrap justify-between gap-2 rounded-card border border-warning/40 p-3 text-sm">
      <span>{item.company} · {item.position} · {t(`daily.phases.${item.phase}`,{defaultValue:item.phase})}</span>
      {item.quick_run_id&&<button data-testid={`daily-review-recovery-${item.run_id}`} className="text-accent underline" disabled={busy}
        onClick={()=>navigate(`/submissions?quick_run_id=${encodeURIComponent(item.quick_run_id!)}`)}>{t('daily.reviewItem')}</button>}
    </div>)}
    <details className="rounded-card border border-border">
    <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">{t('daily.history')} ({data?.history.length??0})</summary>
    <ul className="space-y-3 px-3 pb-3 text-sm">{data?.history.map(h=><li key={h.id} className="space-y-2 rounded-card border border-border p-3">
      <p>{h.day} · {t(`daily.states.${h.state}`)} · {t('daily.confirmed')} {h.confirmed??0}/{h.maximum??3} · {t('daily.unresolved')} {h.unresolved??0}</p>
      <p className="text-text-secondary">{h.reason?t('daily.stopReason')+'：'+t(`daily.reasons.${h.reason}`,{defaultValue:h.reason}):t('daily.running')}</p>
      {(h.items||[]).map(item=><div key={item.run_id} className="flex flex-wrap items-center justify-between gap-2 rounded-card bg-bg-primary/40 p-2">
        <span>{item.company} · {item.position} · <span className={item.phase==='success'?'text-success':item.recovery_required?'text-warning':'text-text-secondary'}>{t(`daily.phases.${item.phase}`,{defaultValue:item.phase})}</span></span>
        {item.quick_run_id&&<button data-testid={`daily-review-${h.id}-${item.run_id}`} className="text-accent underline" disabled={busy}
          onClick={()=>navigate(`/submissions?quick_run_id=${encodeURIComponent(item.quick_run_id!)}`)}>{t('daily.reviewItem')}</button>}
      </div>)}
    </li>)}</ul>
    </details>
  </section>;
}
