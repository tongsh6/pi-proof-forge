(() => {
  const payload=UPLOAD_PAYLOAD,nonce=UPLOAD_NONCE;
  const visible=e=>Boolean(e.getClientRects().length && e.ownerDocument.defaultView.getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const docs=[document],frames=[];
  for(const frame of Array.from(document.querySelectorAll('iframe')).slice(0,8)){
    frames.push({src:clean(frame.src),visible:visible(frame)});
    try{if(frame.contentDocument?.body)docs.push(frame.contentDocument);}catch{}
  }
  const controls=[],fileHints=[];
  for(let index=0;index<docs.length;index++){
    for(const e of Array.from(docs[index].querySelectorAll('a,button,span,div')).filter(visible)){
      const label=e.textContent.trim();
      if(label.length>180 || Array.from(e.children).some(c=>c.textContent.trim()===label))continue;
      if(/^(发简历|发送|发送简历|附件简历|在线简历|确认发送|确定|取消|聊一聊|立即沟通|继续沟通|选择附件简历)$/.test(label))controls.push({document:index,label,tag:e.tagName,class_name:e.className});
      if(label.includes(payload.filename)||label.includes(payload.filename.replace(/\.pdf$/i,'')))fileHints.push({document:index,label,class_name:e.className});
    }
  }
  const detail={url:clean(location.href),frames,controls:controls.slice(0,30),files:fileHints.slice(0,10),action:window.__ppfPdfChatAction||null};
  const result={status:'unknown',filename:payload.filename,hints:controls.slice(0,20).map(c=>c.label),responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:JSON.stringify(detail)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
