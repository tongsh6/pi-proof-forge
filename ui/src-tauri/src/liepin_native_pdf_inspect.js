(async () => {
  const payload=UPLOAD_PAYLOAD;
  const nonce=UPLOAD_NONCE;
  const stem=payload.filename.replace(/\.pdf$/i,'');
  const cleanUrl=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const inputs=Array.from(document.querySelectorAll('input[type="file"]')).slice(0,10).map(e=>({
    accept:e.accept,
    selected_files:Array.from(e.files||[]).map(f=>({name:f.name,size:f.size,type:f.type})),
    form:e.form?{action:cleanUrl(e.form.action),method:e.form.method,target:e.form.target}:null
  }));
  const requests=performance.getEntriesByType('resource').filter(e=>['fetch','xmlhttprequest'].includes(e.initiatorType)).slice(-30)
    .map(e=>({url:cleanUrl(e.name),initiator:e.initiatorType,start_ms:Math.round(e.startTime),duration_ms:Math.round(e.duration)}));
  const text=document.body?.innerText||'';
  const hints=text.split('\n').map(s=>s.trim()).filter(s=>s.includes(payload.filename)||/上传成功|上传失败|上传完成|上传中|解析中|解析完成/.test(s)).slice(0,15).map(s=>s.slice(0,180));
  const links=Array.from(document.querySelectorAll('a')).filter(e=>e.textContent.includes(payload.filename)).slice(0,5)
    .map(e=>({label:e.textContent.trim().slice(0,180),url:cleanUrl(e.href)}));
  // 新版简历页附件卡片懒加载：先等待卡片出现，避免把“页面未加载”误判成“附件已不在”而清除绑定。
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const cardSelector='.attachment-view-box .resume-card-container, [class*="attachmentView--"] [class*="attachmentCard--"]';
  for(let round=0;round<16 && !document.querySelectorAll(cardSelector).length;round++){
    window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
    for(const el of Array.from(document.querySelectorAll('div,main,section')).slice(0,400)){
      try{if(el.scrollHeight>el.clientHeight+200)el.scrollTop=el.scrollHeight;}catch{}
    }
    await wait(500);
  }
  const cards=Array.from(document.querySelectorAll(cardSelector));
  const attachments=[];
  for(const card of cards.filter(e=>e.textContent.includes(stem))) {
    const key=Object.keys(card).find(k=>/^__react(?:Fiber|InternalInstance)\$/.test(k));
    let fiber=key?card[key]:null;
    for(let i=0;fiber && i<8;i++,fiber=fiber.return){
      const record=fiber.memoizedProps?.attachmentResume;
      if(record && record.fileName===stem && String(record.originalExtension).toLowerCase()==='pdf'){
        const fields=['fileName','fileId','originalFileId','originalExtension','fileSize','encryAttachmentId','accessPath','auditStatus','fileUploadTime'];
        attachments.push(Object.fromEntries(fields.filter(k=>['string','number'].includes(typeof record[k])).map(k=>[k,record[k]])));break;
      }
    }
  }
  for(const attachment of attachments){
    try {
      if(!attachment.accessPath?.startsWith('/recruit-auth/resume/attachment-res/c/') || attachment.accessPath.includes('..'))throw Error('invalid path');
      const response=await fetch('https://tdoss.liepin.com/o'+attachment.accessPath,{credentials:'include'});
      const bytes=await response.arrayBuffer();
      if(bytes.byteLength>10000000)throw Error('file too large');
      const sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
      attachment.download={http_status:response.status,byte_length:bytes.byteLength,sha256};
    }catch{attachment.download={http_status:0,byte_length:0,sha256:''};}
    // 仅清理观测副本；React 中的原记录保留给网站自身使用。
    if(typeof attachment.accessPath==='string')attachment.accessPath=attachment.accessPath.split(/[?#]/,1)[0];
  }
  const scripts=Array.from(document.scripts).filter(e=>e.src).slice(-20).map(e=>cleanUrl(e.src));
  const script_resources=performance.getEntriesByType('resource').filter(e=>/\/view-resume-edit\.[a-z0-9]+\.js/.test(e.name)).map(e=>cleanUrl(e.name));
  const info=JSON.stringify({inputs,requests,links,scripts,script_resources,attachment_count:cards.length,attachments});
  const result={status:'unknown',filename:payload.filename,hints,responses:[{method:'OBSERVE',url:cleanUrl(location.href),http_status:0,payload:info.slice(0,11000)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
