(async () => {
  // 只读诊断：确认「附件简历」区状态与上传入口；需要时点一次「+」打开上传弹窗后关闭，不选择文件。
  const nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const classOf=e=>String(e.className?.baseVal ?? e.className ?? '');
  const rect=e=>{const r=e.getBoundingClientRect();return Math.round(r.x)+','+Math.round(r.y)+','+Math.round(r.width)+'x'+Math.round(r.height);};
  const line=e=>[String(e.tagName||'').slice(0,6),classOf(e).slice(0,40),rect(e),(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim().slice(0,26),(e.getAttribute('aria-label')||'').slice(0,14)].join('|');
  const lines=[];const push=(p,v)=>lines.push(String(p)+'='+String(v).slice(0,168));
  const pointerClick=el=>{
    const r=typeof el.getBoundingClientRect==='function'?el.getBoundingClientRect():{x:0,y:0,width:0,height:0};
    const opts={bubbles:true,cancelable:true,view:window,clientX:r.x+Math.max(1,Math.min(r.width/2,8)),clientY:r.y+Math.max(1,Math.min(r.height/2,8)),button:0};
    for(const type of ['pointerover','mouseover','mousemove','pointerdown','mousedown','pointerup','mouseup','click']){try{el.dispatchEvent(new MouseEvent(type,opts));}catch{}}
  };
  const findSection=()=>{
    for(const title of Array.from(document.querySelectorAll('[class*="sectionTitle"]')).filter(visible)){
      if((title.textContent||'').trim()!=='附件简历')continue;
      let section=title.parentElement;
      while(section && !/section--/.test(classOf(section)))section=section.parentElement;
      if(section)return section;
    }
    return null;
  };
  try{
    window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
    for(const el of Array.from(document.querySelectorAll('div,main,section')).slice(0,400)){
      try{if(el.scrollHeight>el.clientHeight+200)el.scrollTop=el.scrollHeight;}catch{}
    }
    await wait(1200);
    push('URL',location.href);
    const section=findSection();
    push('SECTION',section?'found @y'+Math.round(section.getBoundingClientRect().y):'not_found');
    if(!section){
      const headers=Array.from(document.querySelectorAll('[class*="sectionHeader"]')).filter(visible).slice(0,4).map(line);
      for(const item of headers)push('HDR',item);
    }else{
      const cards=Array.from(section.querySelectorAll('[class*="attachmentCard--"], .attachment-view-box .resume-card-container')).filter(visible);
      const addIcon=Array.from(section.querySelectorAll('[data-nick="resume-add-icon"],[class*="addIcon"]')).filter(visible)[0];
      push('CARDS',cards.length);
      push('ADD_ICON',addIcon?'present':'absent');
      if(!addIcon && cards.length>=3)push('QUOTA','attachment_quota_reached: 已达平台附件上限 3 个，上传入口不会渲染');
      if(addIcon){
        pointerClick(addIcon);
        await wait(900);
        const modal=Array.from(document.querySelectorAll('[class*="ant-c-modal-root"],[class*="modal"],[role="dialog"]')).filter(visible).filter(e=>(e.getBoundingClientRect().width||0)>100&&/上传|拖拽|选择文件|附件/.test(e.innerText||''))[0];
        const inputs=Array.from(document.querySelectorAll('input[type="file"]')).filter(e=>!e.disabled);
        push('UPLOAD_UI',(modal?'modal='+classOf(modal).slice(0,30):'modal=none')+' fileInputs='+inputs.length);
        if(modal){
          const zones=Array.from(modal.querySelectorAll('*')).filter(e=>visible(e)&&/拖拽|拖入|点击上传|选择文件/.test(e.textContent||'')&&e.children.length<=4);
          push('DROPZONE',zones.length?(zones[zones.length-1].textContent||'').replace(/\s+/g,' ').slice(0,80):'modal_itself');
          const closers=Array.from(modal.querySelectorAll('button')).filter(e=>visible(e)&&/取\s*消|关\s*闭|cancel/i.test(e.textContent||''));
          if(closers.length)pointerClick(closers[closers.length-1]);
          else document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true}));
          await wait(300);
        }
      }
      const sample=cards.slice(0,1).map(c=>(c.innerText||'').replace(/\s+/g,' ').trim().slice(0,60));
      for(const item of sample)push('SAMPLE',item);
    }
  }catch(e){push('ERR',String(e).slice(0,160));}
  const result={status:'not_submitted',filename:'diagnostic',hints:lines.slice(0,20),responses:[]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
