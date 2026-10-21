(async () => {
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const leaves=()=>Array.from(document.querySelectorAll('*')).filter(e=>visible(e)&&e.textContent.trim().length<120&&!Array.from(e.children).some(c=>c.textContent.trim()===e.textContent.trim()));
  const info={url:location.href,job_id:payload.job_id||'',steps:[],frames:[],chat_text:'',job_id_hits:[],dialogs:[],radios:[],buttons:[]};
  const finish=()=>{const result={status:'not_submitted',filename:'probe',hints:['probe'],responses:[{method:'OBSERVE',url:location.href,http_status:0,payload:JSON.stringify(info)}]};location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));};
  try{
    const main=document.querySelector('a.btn-main');
    if(main){main.click();info.steps.push('clicked btn-main');}
    await wait(2500);
    info.frames=Array.from(document.querySelectorAll('iframe')).map(f=>({src:f.src,visible:visible(f)}));
    const chat=document.querySelector('.im-ui-chat-container')||document.querySelector('[class*="im-ui-chat"]');
    info.chat_text=chat?(chat.innerText||'').replace(/\s+/g,' ').slice(0,1500):'';
    const resume=leaves().filter(e=>e.textContent.trim()==='发简历');
    info.steps.push('resume_count:'+resume.length);
    if(resume.length===1){
      let btn=resume[0];
      for(let i=0;i<5 && btn;i++,btn=btn.parentElement){const cls=String(btn.className||'');if(/action-button|im-ui-action|btn/i.test(cls)){btn.click();info.steps.push('clicked_action_parent:'+cls.slice(0,80));break;}}
      await wait(2000);
    }
    const modals=Array.from(document.querySelectorAll('[class*="modal"],[role="dialog"],[class*="dialog"]')).filter(visible);
    info.dialogs=modals.slice(0,10).map(e=>({cls:String(e.className||'').slice(0,120),text:(e.innerText||'').replace(/\s+/g,' ').slice(0,1200)}));
    info.radios=Array.from(document.querySelectorAll('input[type="radio"]')).filter(visible).map(r=>({value:r.value,checked:r.checked,disabled:r.disabled,name:r.name,outer:String(r.outerHTML).slice(0,200)}));
    info.buttons=leaves().filter(e=>/^(发送|立即投递|确认发送|发简历|选择附件简历)$/.test(e.textContent.trim())).slice(0,20).map(e=>({text:e.textContent.trim(),tag:e.tagName,cls:String(e.className||'')}));
    const jid=String(payload.job_id||'');
    if(jid){for(const e of Array.from(document.querySelectorAll('*'))){const attrs=Array.from(e.attributes||[]).map(a=>a.name+'='+a.value).join(' ');if(attrs.includes(jid)) info.job_id_hits.push({tag:e.tagName,cls:String(e.className||'').slice(0,80)});if(info.job_id_hits.length>=8)break;}}
    finish();
  }catch(e){info.error=String(e).slice(0,300);finish();}
})();
