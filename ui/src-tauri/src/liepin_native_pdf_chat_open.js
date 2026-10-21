(() => {
  // 生产步骤 A：打开目标岗位的沟通面板。
  // 猎聘新版在职位页内以抽屉/弹层打开沟通，不再整页跳转；本脚本只做幂等的入口点击，
  // 「发简历」及后续确认弹窗由独立脚本执行，避免入口跳转销毁后续步骤的脚本。
  const payload=CHAT_PAYLOAD;
  window.__ppfPdfChatAction={click_issued:false,reason:'target_not_verified'};
  const setReason=reason=>{window.__ppfPdfChatAction={click_issued:false,reason};};
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const body=document.body?document.body.innerText||'':'';
  if(!payload.job_url){setReason('missing_target');return;}
  if(clean(location.href)!==clean(payload.job_url)){setReason('target_not_verified');return;}
  if(/安全验证|人机验证|滑动验证/.test(body)){setReason('security_challenge');return;}
  // 已处于目标沟通态（可见「发简历」操作）时不再点击入口，避免把已打开的抽屉切换掉。
  const has_resume_entry=Array.from(document.querySelectorAll('*')).some(e=>visible(e)
    && e.children.length===0 && e.textContent.trim()==='发简历');
  if(has_resume_entry){setReason('chat_already_open');return;}
  const entries=Array.from(document.querySelectorAll('a.btn-main,a.btn-chat')).filter(visible)
    .filter(e=>/^(聊一聊|继续聊)$/.test(e.textContent.trim()));
  const primary=entries.filter(e=>String(e.className||'').split(/\s+/).includes('btn-main'));
  const entry=primary.length===1?primary[0]:(entries.length===1?entries[0]:null);
  if(!entry){setReason(entries.length?'chat_entry_not_unique':'chat_entry_missing');return;}
  if(payload.write_deadline_ms && (Date.now()>=payload.write_deadline_ms
    || (payload.daily_cycle && window.__ppfCancelledDailyCycle===payload.daily_cycle))){setReason('daily_write_cancelled');return;}
  window.__ppfPdfChatAction={click_issued:true,reason:'approved_target_chat_entry'};
  entry.click();
})();
