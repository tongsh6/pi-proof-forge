(() => {
  // 独立探测 1/2 的第二步：跳转/抽屉稳定后读取沟通页真实结构；只读，不点击任何业务控件。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const normalize=s=>String(s==null?'':s).normalize('NFKC').replace(/\s/g,'').toLowerCase();
  const brief=(value,limit)=>String(value==null?'':value).replace(/\s+/g,' ').slice(0,limit);
  const docs=[document],frames=[];
  for(const frame of Array.from(document.querySelectorAll('iframe')).slice(0,8)){
    frames.push({src:clean(frame.src).slice(0,200),visible:visible(frame)});
    try{const doc=frame.contentDocument;if(doc&&doc.body)docs.push(doc);}catch(error){}
  }
  const leaves=()=>Array.from(document.querySelectorAll('*')).filter(e=>visible(e)
    && e.textContent.trim().length<180 && !Array.from(e.children).some(c=>c.textContent.trim()===e.textContent.trim()));
  const panels=Array.from(document.querySelectorAll('.im-ui-chat-container,.im-ui-contact-list,[class*="im-ui-chat"],[class*="im-ui-drawer"],[class*="ant-im"]')).filter(visible).slice(0,5);
  const pickComposer=e=>({tag:e.tagName,class_name:brief(e.className,160),placeholder:brief(e.getAttribute&&e.getAttribute('placeholder'),80),
    contenteditable:brief(e.getAttribute&&e.getAttribute('contenteditable'),20),role:brief(e.getAttribute&&e.getAttribute('role'),20),
    disabled:Boolean(e.disabled),text:brief(e.textContent,40),parent_class:brief(e.parentElement?e.parentElement.className:'',160)});
  const composer={
    inputs:Array.from(document.querySelectorAll('textarea,[contenteditable="true"],[role="textbox"]')).filter(visible).slice(0,8).map(pickComposer),
    send_buttons:Array.from(document.querySelectorAll('.im-ui-basic-send-btn,button,[role="button"]')).filter(visible)
      .filter(e=>e.textContent.trim()==='发送').slice(0,6).map(pickComposer)
  };
  const detail={probe:'chat_ready',url:clean(location.href),url_match:clean(location.href)===clean(payload.job_url),
    company_present:normalize(document.body?document.body.innerText:'').includes(normalize(payload.company)),
    position_present:normalize(document.body?document.body.innerText:'').includes(normalize(payload.position)),
    frames,in_iframe:docs.length>1,composer,
    im_panels:panels.map(e=>({class_name:brief(e.className,160),text:brief(e.innerText,700)})),
    resume_entries:leaves().filter(e=>/^(发简历|发送简历)$/.test(e.textContent.trim())).slice(0,6)
      .map(e=>({tag:e.tagName,class_name:brief(e.className,160),parent_class:brief(e.parentElement?e.parentElement.className:'',160),
        text:brief(e.textContent,40),in_im:(()=>{for(let p=e,i=0;p&&i<10;p=p.parentElement,i++){if(typeof p.className==='string'&&p.className.includes('im-ui'))return true;}return false;})()})),
    contact_items:Array.from(document.querySelectorAll('.im-ui-contact-list-item')).filter(visible).slice(0,8)
      .map(e=>({text:brief(e.innerText,200),class_name:brief(e.className,120)})),
    chat_entries:Array.from(document.querySelectorAll('a,button,div,span')).filter(visible)
      .filter(e=>/^(我的沟通|聊一聊|立即沟通|继续沟通)$/.test(e.textContent.trim())).slice(0,8)
      .map(e=>({tag:e.tagName,label:e.textContent.trim(),class_name:brief(e.className,120)})),
    pre_click:window.__ppfChatOpenProbe||null};
  let raw=JSON.stringify(detail);
  if(raw.length>10000){
    // 超限时按字段重要性收缩，优先保留沟通面板与「发简历」入口。
    detail.contact_items=detail.contact_items.slice(0,3);
    detail.chat_entries=detail.chat_entries.slice(0,4);
    detail.frames=frames.slice(0,3);
    detail.im_panels=detail.im_panels.map(p=>({class_name:p.class_name,text:brief(p.text,300)}));
    raw=JSON.stringify(detail);
  }
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),
    hints:['probe:chat_ready','im_panels:'+detail.im_panels.length,'resume_entries:'+detail.resume_entries.length],
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:raw}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
