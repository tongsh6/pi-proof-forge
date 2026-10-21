(async () => {
  // 独立探测 2/2：在已打开的沟通页面点击「发简历」，只抓确认弹窗真实字段，不选择附件、不点击发送。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const normalize=s=>String(s==null?'':s).normalize('NFKC').replace(/[\s·•]/g,'').toLowerCase();
  const brief=(value,limit)=>String(value==null?'':value).replace(/\s+/g,' ').slice(0,limit);
  const stem=String(payload.filename||'').replace(/\.pdf$/i,'');
  const leaves=()=>Array.from(document.querySelectorAll('*')).filter(e=>visible(e)
    && e.textContent.trim().length<180 && !Array.from(e.children).some(c=>c.textContent.trim()===e.textContent.trim()));
  const inIm=e=>{for(let p=e,i=0;p&&i<10;p=p.parentElement,i++){if(typeof p.className==='string'&&p.className.includes('im-ui'))return true;}return false;};
  const text=()=>document.body?document.body.innerText||'':'';

  const collect=()=>{
    const detail={probe:'resume_dialog',url:clean(location.href),reason:'',
      company_present:normalize(text()).includes(normalize(payload.company)),
      position_present:normalize(text()).includes(normalize(payload.position)),
      click_target:null,click_dispatched:false,
      chat_present:Boolean(document.querySelector('.im-ui-chat-container')||document.querySelector('[class*="im-ui-chat"]')),
      frames:[],modals:[],radios:[],buttons:[],resume_rows:[],text_hits:[],body_excerpt:'',confirmation:null};
    const main_chat=document.querySelector('.im-ui-chat-container')||document.querySelector('[class*="im-ui-chat"]');
    if(main_chat)detail.chat_text=brief(main_chat.innerText,900);
    for(const frame of Array.from(document.querySelectorAll('iframe')).slice(0,6)){
      detail.frames.push({src:clean(frame.src).slice(0,200),visible:visible(frame)});
    }
    const modal_selector='.ant-modal-content,.ant-im-modal-content,.ant-modal-wrap,[role="dialog"],[class*="modal"],[class*="dialog"],[class*="popup"],[class*="confirm"]';
    const modal_nodes=Array.from(new Set(Array.from(document.querySelectorAll(modal_selector)))).filter(visible);
    detail.modals=modal_nodes.slice(0,6).map(e=>({
      tag:e.tagName,class_name:brief(e.className,200),
      text:brief(e.innerText,900),
      radios:Array.from(e.querySelectorAll('input[type="radio"]')).slice(0,10).map(r=>({value:String(r.value).slice(0,300),checked:r.checked,disabled:r.disabled,name:r.name,class_name:brief(r.className,100)})),
      buttons:Array.from(e.querySelectorAll('button')).slice(0,10).map(b=>({text:brief(b.textContent,40),disabled:b.disabled,class_name:brief(b.className,100)})),
      html:/选择附件简历|附件简历|在线简历/.test(e.innerText||'')?brief(e.outerHTML,2600):''}));
    const doc_radios=Array.from(document.querySelectorAll('input[type="radio"]')).filter(visible);
    detail.radios=doc_radios.slice(0,20).map(r=>({value:String(r.value).slice(0,300),checked:r.checked,disabled:r.disabled,name:r.name,
      class_name:brief(r.className,100),label:brief(r.closest('label')?r.closest('label').innerText:'',120)}));
    detail.buttons=Array.from(document.querySelectorAll('button')).filter(visible).slice(0,30)
      .map(b=>({text:brief(b.textContent,40),disabled:b.disabled,class_name:brief(b.className,100)}));
    detail.resume_rows=leaves().filter(e=>stem&&(e.textContent.includes(stem)||e.textContent.includes(stem.slice(0,10))))
      .slice(0,8).map(e=>({text:brief(e.textContent,160),tag:e.tagName,class_name:brief(e.className,160),parent_class:brief(e.parentElement?e.parentElement.className:'',160)}));
    detail.text_hits=leaves().filter(e=>/^(发简历|发送简历|选择附件简历|立即投递|确认发送|发送|确定|取消|附件简历|在线简历|我的沟通)$/.test(e.textContent.trim()))
      .slice(0,20).map(e=>({label:e.textContent.trim(),tag:e.tagName,class_name:brief(e.className,160),parent_class:brief(e.parentElement?e.parentElement.className:'',160),in_im:inIm(e)}));
    const page_text=text();
    const anchor=page_text.replace(/\s+/g,' ').indexOf('选择附件简历');
    detail.body_excerpt=anchor>=0?brief(page_text.replace(/\s+/g,' ').slice(Math.max(0,anchor-500),anchor+1500),1900):'';
    const confirm=modal_nodes.filter(e=>/选择附件简历|附件简历/.test(e.innerText||'')).slice(0,1);
    if(confirm.length===1){
      const modal=confirm[0];
      detail.confirmation={tag:modal.tagName,class_name:brief(modal.className,200),text:brief(modal.innerText,1200),
        radios:Array.from(modal.querySelectorAll('input[type="radio"]')).map(r=>({value:String(r.value).slice(0,300),checked:r.checked,disabled:r.disabled,name:r.name,class_name:brief(r.className,100)})),
        buttons:Array.from(modal.querySelectorAll('button')).map(b=>({text:brief(b.textContent,40),disabled:b.disabled,class_name:brief(b.className,100)})),
        html:brief(modal.outerHTML,3000)};
    }
    let raw=JSON.stringify(detail);
    if(raw.length>10000){
      // 超限时只保留与确认框/匹配规则最相关的部分。
      detail.modals=detail.modals.slice(0,2).map(m=>({tag:m.tag,class_name:m.class_name,text:brief(m.text,400),radios:m.radios,buttons:m.buttons,html:''}));
      detail.resume_rows=detail.resume_rows.slice(0,4);
      detail.text_hits=detail.text_hits.slice(0,10);
      detail.buttons=detail.buttons.slice(0,12);
      detail.body_excerpt=brief(detail.body_excerpt,800);
      if(detail.confirmation)detail.confirmation.html=brief(detail.confirmation.html,1500);
      raw=JSON.stringify(detail);
    }
    return {detail,raw};
  };

  let detail={probe:'resume_dialog',url:clean(location.href),reason:'unexpected_error'};
  try{
    const buttons=leaves().filter(e=>/^(发简历|发送简历)$/.test(e.textContent.trim()));
    const im_buttons=buttons.filter(inIm);
    const candidates=im_buttons.length?im_buttons:buttons;
    const clicked=collect();
    detail=clicked.detail;
    if(candidates.length===1){
      const button=candidates[0];
      detail.click_target={label:button.textContent.trim(),tag:button.tagName,class_name:brief(button.className,160),
        parent_class:brief(button.parentElement?button.parentElement.className:'',160)};
      detail.click_dispatched=true;
      detail.reason='resume_entry_clicked';
      button.click();
      await wait(1600);
      const after=collect();
      after.detail.click_target=detail.click_target;
      after.detail.click_dispatched=true;
      after.detail.reason='resume_entry_clicked';
      detail=after.detail;
    }else{
      detail.reason=candidates.length?'resume_entry_not_unique:'+candidates.length:'resume_entry_missing';
    }
  }catch(error){detail.error=String(error).slice(0,300);}
  let raw=JSON.stringify(detail);
  if(raw.length>11000)raw=raw.slice(0,11000);
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),
    hints:['probe:resume_dialog',detail.reason||'observed','modals:'+((detail.modals||[]).length)],
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:raw}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
