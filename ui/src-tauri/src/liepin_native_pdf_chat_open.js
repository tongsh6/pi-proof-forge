(() => {
  const payload=CHAT_PAYLOAD;
  window.__ppfPdfChatAction={click_issued:false,reason:'target_not_verified'};
  const normalize=s=>String(s).normalize('NFKC').replace(/\s/g,'').toLowerCase();
  const current=new URL(location.href),expected=new URL(payload.job_url);current.search='';expected.search='';current.hash='';expected.hash='';
  const body=document.body?.innerText||'';
  if(current.href!==expected.href || !normalize(body).includes(normalize(payload.company)) || !normalize(body).includes(normalize(payload.position)) || /安全验证|人机验证|滑动验证|该职位已下线/.test(body))return;
  const visible=e=>Boolean(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  if(Array.from(document.querySelectorAll('input[type="password"],#header-quick-menu-login')).some(visible))return;
  const controls=Array.from(document.querySelectorAll('a.btn-main')).filter(e=>visible(e) && e.textContent.trim()==='聊一聊');
  if(controls.length!==1){window.__ppfPdfChatAction.reason='chat_entry_not_unique';return;}
  window.__ppfPdfChatAction={click_issued:true,reason:'approved_target_chat_entry'};
  if(payload.write_deadline_ms && (Date.now()>=payload.write_deadline_ms || (payload.daily_cycle && window.__ppfCancelledDailyCycle===payload.daily_cycle))){window.__ppfPdfChatAction={click_issued:false,reason:'daily_write_cancelled'};return;}
  controls[0].click();
})();
