(async () => {
  const payload=UPLOAD_PAYLOAD,nonce=UPLOAD_NONCE;
  let writeGateClosed=false;
  const canWrite=()=>!payload.write_deadline_ms || (!writeGateClosed && Date.now()<payload.write_deadline_ms && (!payload.daily_cycle || window.__ppfCancelledDailyCycle!==payload.daily_cycle));
  let restore=()=>{};
  const normalize=s=>String(s).normalize('NFKC').replace(/[\s·•]/g,'').toLowerCase();
  const visible=e=>Boolean(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const leaves=()=>Array.from(document.querySelectorAll('*')).filter(e=>visible(e) && e.textContent.trim().length<180 && !Array.from(e.children).some(c=>c.textContent.trim()===e.textContent.trim()));
  const resumeButtons=()=>leaves().filter(e=>e.textContent.trim()==='发简历');
  const inIm=e=>{for(let p=e,i=0;p && i<10;p=p.parentElement,i++)if(typeof p.className==='string' && p.className.includes('im-ui'))return true;return false;};
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const action={click_issued:false,reason:'inspection_only'};
  if(!resumeButtons().length){
    if(!Array.from(document.querySelectorAll('.im-ui-contact-list-item')).some(visible)){
      const openers=Array.from(document.querySelectorAll('.im-ui-basic-entry.im-ui-basic-entry-c')).filter(visible);
      if(openers.length===1){openers[0].click();await wait(700);}
    }
    const entries=Array.from(document.querySelectorAll('.im-ui-contact-list-item')).filter(e=>visible(e)
      && normalize(e.querySelector('.im-ui-contact-title-sub')?.textContent||'').endsWith(normalize(payload.company)));
    if(entries.length===1){entries[0].click();await wait(700);}
  }
  const buttons=resumeButtons();
  let context=null;
  if(buttons.length===1){
    let parent=buttons[0].parentElement;
    for(let i=0;parent && i<12;i++,parent=parent.parentElement){
      const text=parent.innerText||'';
      if(text.length<3000 && normalize(text).includes(normalize(payload.company)) && normalize(text).includes(normalize(payload.position))){
        context={class_name:parent.className,text:text.slice(0,600)};break;
      }
    }
  }
  if(payload.action==='prepare'){
    if(context && buttons.length===1){action.click_issued=true;action.reason='approved_recipient_resume_entry';buttons[0].click();await wait(1200);}
    else action.reason='active_recipient_not_verified';
    if(action.click_issued){
      const modals=Array.from(document.querySelectorAll('.ant-im-modal-content')).filter(e=>visible(e)
        && (e.innerText||'').includes('选择附件简历') && (e.innerText||'').includes(payload.filename.replace(/\.pdf$/i,'')));
      const targets=modals.length===1?Array.from(modals[0].querySelectorAll('input[type="radio"]')).filter(e=>e.value===payload.file_id):[];
      // 只切换至本次批准的附件；最终发送仍由独立动作重新核验。
      if(targets.length===1 && !targets[0].disabled){if(!targets[0].checked){targets[0].click();await wait(300);}}
      else action.reason='approved_attachment_not_unique';
    }
  }
  if(payload.action==='send' && canWrite()){
    action.reason='confirmation_not_verified';
    const modals=Array.from(document.querySelectorAll('.ant-im-modal-content')).filter(e=>visible(e)
      && (e.innerText||'').includes('选择附件简历') && (e.innerText||'').includes(payload.filename.replace(/\.pdf$/i,'')));
    if(context && modals.length===1){
      const radios=Array.from(modals[0].querySelectorAll('input[type="radio"]'));
      const targets=radios.filter(e=>e.value===payload.file_id);
      const selected=radios.filter(e=>e.checked);
      const submit=Array.from(modals[0].querySelectorAll('button')).filter(e=>e.textContent.trim()==='立即投递' && !e.disabled);
      if(targets.length===1 && !targets[0].disabled && selected.length===1 && selected[0].value===payload.file_id && submit.length===1){
        window.__ppfPdfFinalEvidence=[];
        const safe=(value,depth=0)=>{
          if(depth>5)return null;
          if(Array.isArray(value))return value.slice(0,8).map(v=>safe(v,depth+1));
          if(value && typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>!/token|cookie|secret|password|authorization|signature|csrf|credential|accesskey|^tk$/i.test(k)).slice(0,35).map(([k,v])=>[k,safe(v,depth+1)]));
          return typeof value==='string'?value.slice(0,1200):typeof value==='number'||typeof value==='boolean'||value===null?value:null;
        };
        const decode=value=>{if(typeof value!=='string')return value;try{return JSON.parse(value);}catch{return Object.fromEntries(new URLSearchParams(value));}};
        const capture=(method,target,request,status,response)=>{
          try{
            const url=new URL(target,location.href);url.search='';url.hash='';
            if(String(method).toUpperCase()!=='POST' || !/send|resume|apply|deliver/i.test(url.pathname) || window.__ppfPdfFinalEvidence.length>=4)return;
            window.__ppfPdfFinalEvidence.push({method:'POST',url:url.href,http_status:status,
              request:JSON.stringify(safe(decode(request))).slice(0,2200),response:JSON.stringify(safe(response)).slice(0,2200)});
          }catch{}
        };
        const oldFetch=window.fetch,proto=XMLHttpRequest.prototype,oldOpen=proto.open,oldSend=proto.send;
        window.fetch=async function(input,init){if(!canWrite() && String(init?.method||input?.method||'GET').toUpperCase()!=='GET')throw Error('daily_write_cancelled');const response=await oldFetch.apply(this,arguments);response.clone().json().then(data=>capture(init?.method||'GET',typeof input==='string'?input:input.url,init?.body,response.status,data)).catch(()=>{});return response;};
        proto.open=function(method,url){this.__ppfPdfFinalRequest={method,url};return oldOpen.apply(this,arguments);};
        proto.send=function(body){if(!canWrite() && String(this.__ppfPdfFinalRequest?.method||'GET').toUpperCase()!=='GET')throw Error('daily_write_cancelled');this.addEventListener('load',()=>{try{const r=this.__ppfPdfFinalRequest;if(r)capture(r.method,r.url,body,this.status,this.responseType==='json'?this.response:JSON.parse(this.responseText));}catch{}});return oldSend.apply(this,arguments);};
        let restoreTimer;restore=()=>{if(restoreTimer!==undefined && typeof clearTimeout==='function')clearTimeout(restoreTimer);window.fetch=oldFetch;proto.open=oldOpen;proto.send=oldSend;};
        if(!payload.write_deadline_ms)restoreTimer=setTimeout(restore,10000);
        action.click_issued=true;action.reason='approved_attachment_confirmation';
        submit[0].click();await wait(1800);
      }
    }
  }
  const controls=leaves().filter(e=>/^(发简历|发送|发送简历|附件简历|在线简历|确认发送|确定|取消|选择附件简历|我的沟通)$/.test(e.textContent.trim()))
    .slice(0,25).map(e=>({label:e.textContent.trim(),tag:e.tagName,class_name:e.className,parent_class:e.parentElement?.className}));
  const candidates=leaves().filter(e=>inIm(e) && normalize(e.textContent).includes(normalize(payload.company))).slice(0,4)
    .map(e=>({text:e.textContent.trim(),class_name:e.className,parent_class:e.parentElement?.className}));
  const dialogs=Array.from(document.querySelectorAll('[role="dialog"],.ant-modal-content,.ant-im-modal-content')).filter(e=>visible(e) && !String(e.className).includes('drawer') && /选择附件简历|简历发送成功/.test(e.innerText||'')).slice(0,2)
    .map(e=>({class_name:e.className,text:(e.innerText||'').slice(0,1800)}));
  const files=leaves().filter(e=>e.textContent.includes(payload.filename)||e.textContent.includes(payload.filename.replace(/\.pdf$/i,''))).slice(0,8)
    .map(e=>({text:e.textContent.trim(),class_name:e.className,parent_class:e.parentElement?.className}));
  const url=new URL(location.href);url.search='';url.hash='';
  const clickable=e=>{const k=Object.keys(e).find(k=>/^__react(?:Props|EventHandlers)\$/.test(k));return Boolean(k && typeof e[k]?.onClick==='function');};
  const entries=leaves().filter(e=>e.textContent.trim()==='我的沟通').map(e=>{const path=[];for(let p=e,i=0;p && i<4;p=p.parentElement,i++)path.push({tag:p.tagName,class_name:p.className,clickable:clickable(p),children:Array.from(p.children).slice(0,5).map(c=>({tag:c.tagName,class_name:c.className,clickable:clickable(c),text:c.textContent.slice(0,50)}))});return path;});
  const confirmation=Array.from(document.querySelectorAll('.ant-im-modal-content')).filter(e=>visible(e) && (e.innerText||'').includes('选择附件简历')).map(e=>({
    text:(e.innerText||'').slice(0,1000),
    inputs:Array.from(e.querySelectorAll('input')).map(i=>({type:i.type,checked:i.checked,value:i.value,disabled:i.disabled,class_name:i.className})),
    buttons:Array.from(e.querySelectorAll('button')).map(b=>({text:b.textContent.trim(),disabled:b.disabled,class_name:b.className})),
    file_rows:Array.from(e.querySelectorAll('._11156dSb6h')).map(r=>({text:r.textContent.trim(),class_name:r.className,children:Array.from(r.children).map(c=>({tag:c.tagName,class_name:c.className,text:c.textContent.slice(0,80)}))}))
  }));
  const detail={url:url.href,context,action,controls,candidates,dialogs,files,confirmation,network:window.__ppfPdfFinalEvidence||[]};
  if(JSON.stringify(detail).length>9000){detail.candidates=[];detail.dialogs=[];detail.controls=detail.controls.slice(0,8);if(detail.context)detail.context.text=detail.context.text.slice(0,200);}
  const result={status:'unknown',filename:payload.filename,hints:controls.slice(0,20).map(c=>c.label),responses:[{method:'OBSERVE',url:url.href,http_status:0,payload:JSON.stringify(detail)}]};
  writeGateClosed=true;
  if(!payload.write_deadline_ms)restore();
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
