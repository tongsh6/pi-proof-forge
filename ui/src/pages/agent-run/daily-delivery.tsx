import {useEffect,useState} from "react";
import {useTranslation} from "react-i18next";
import {useNavigate} from "react-router-dom";
import {getErrorMessage} from "@/lib/errors";
import {buttonClass,confirmAction,notify} from "@/lib/ui";
import {getDailyStatus,previewDailyPdf,saveDailyDraft,changeDailyAuthorization,runDailyDelivery,closeInterruptedDaily,type DailyStatus} from "@/lib/sidecar/api";

function localInput(date:Date){return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);}
export function DailyDeliveryPanel(){
  const {t}=useTranslation();
  const navigate=useNavigate();
  const [data,setData]=useState<DailyStatus|null>(null),[selected,setSelected]=useState<string[]>([]);
  const [maximum,setMaximum]=useState(3),[time,setTime]=useState("09:00"),[expiry,setExpiry]=useState(()=>localInput(new Date(Date.now()+7*86400000)));
  const [consent,setConsent]=useState(false),[dirty,setDirty]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [preview,setPreview]=useState("");
  useEffect(()=>{
    let alive=true;
    const load=async(initial=false)=>{try{const next=await getDailyStatus();if(!alive)return;setData(next);
      if(initial&&next.authorization){const a=next.authorization;setSelected(a.scope.map(i=>i.run_id));setMaximum(a.maximum);setTime(a.time);setExpiry(localInput(new Date(a.expires_at)));setDirty(false);}
    }catch(e){if(alive)setError(getErrorMessage(e));}};
    void load(true);const timer=window.setInterval(()=>void load(),15000);
    return()=>{alive=false;window.clearInterval(timer);};
  },[]);
  const a=data?.authorization,editable=!a||["draft","revoked"].includes(a.state),running=data?.history.find(h=>h.state==="running");
  const recoveryIds=new Set(data?.history.flatMap(h=>(h.items||[]).filter(item=>item.recovery_required).map(item=>item.run_id))||[]);
  const recoveryBlocked=Boolean(data?.recovery_required)||Boolean(data?.today.unresolved)||Boolean(a?.scope.some(item=>recoveryIds.has(item.run_id)));
  const errorText=(error:unknown)=>{const message=getErrorMessage(error);const code=message.match(/\b(?:daily_[a-z_]+|NATIVE_OPERATION_BUSY)\b/)?.[0];return code?t('daily.reasons.'+code,{defaultValue:message}):message;};
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
    <div className="flex items-center justify-between"><h2 className="text-lg font-semibold">{t('daily.title')}</h2><button type="button" className={buttonClass.ghost} disabled={busy} onClick={()=>void act(async()=>getDailyStatus())}>{t('daily.refresh')}</button></div>
    {data&&<p className="text-sm">{t('daily.today')} {data.today.day} · {t('daily.confirmed')} {data.today.confirmed}/3 · {t('daily.occupied')} {data.today.occupied} · {t('daily.state')} {t(`daily.states.${a?.state||'none'}`)}</p>}
    <div className="text-sm text-text-secondary">{t('daily.descriptionShort')}<details className="mt-1 text-xs text-text-muted"><summary className="cursor-pointer select-none text-accent">{t('common.learnMore')}</summary><p className="mt-1">{t('daily.description')}</p></details></div>
    <details open={editable} className="rounded-card border border-border">
    <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">{t('daily.settings')}{!editable&&<span className="ml-2 text-xs font-normal text-text-muted">{t('daily.maximum')} {maximum} · {t('daily.time')} {time}</span>}</summary>
    <div className="flex flex-wrap gap-4 px-3 pb-3">
      <label>{t('daily.maximum')} <select aria-label={t('daily.maximum')} className={inputClass} value={maximum} disabled={!editable||busy} onChange={e=>{setMaximum(Number(e.target.value));edit();}}>{[1,2,3].map(n=><option key={n} value={n}>{n}</option>)}</select></label>
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
