(async () => {
  const payload = UPLOAD_PAYLOAD;
  const nonce = UPLOAD_NONCE;
  let writeGateClosed=false;
  const canWrite=()=>!payload.write_deadline_ms || (!writeGateClosed && Date.now()<payload.write_deadline_ms && (!payload.daily_cycle || window.__ppfCancelledDailyCycle!==payload.daily_cycle));
  const responses = [];
  let dispatched = false;
  let restore = () => {};
  const finish = (status, hints) => {
    writeGateClosed=true;
    if(!payload.write_deadline_ms)restore();
    const result = {status,filename:payload.filename,hints,responses};
    location.href = 'piproofforge-pdf://result?nonce=' + encodeURIComponent(nonce) + '&payload=' + encodeURIComponent(JSON.stringify(result));
  };
  try {
    if (location.origin !== 'https://c.liepin.com' || location.pathname !== '/resume/edit'
      || /安全验证|人机验证|滑动验证/.test(document.body?.innerText || '')) {
      finish('not_submitted',['上传页面未就绪']); return;
    }
    if(payload.filename.length>24){finish('not_submitted',['附件名称超过平台上限']);return;}
    const stem=payload.filename.replace(/\.pdf$/i,'');
    // 附件区在简历页底部且懒加载；先滚到底部，必要时点击“附件简历”旁的加号创建上传控件。
    const waitInput=(ms)=>new Promise(r=>setTimeout(r,ms));
    const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
    const classOf=e=>String(e.className?.baseVal ?? e.className ?? '');
    // 新版上传弹窗/菜单使用 ant-c-* 设计系统，也不一定给 input 写 accept；兼容旧 antd。
    const findModal=()=>Array.from(document.querySelectorAll('[class*="ant-c-modal-root"],[class*="modal"],[class*="Modal"],[class*="dialog"],[class*="Dialog"],[role="dialog"]'))
      .find(e=>visible(e) && (e.getBoundingClientRect().width||0)>100 && /上传|拖拽|拖入|选择文件|附件/.test(e.innerText||'') && (e.innerText||'').length<900);
    const pdfInputs=()=>Array.from(document.querySelectorAll('input[type="file"]')).filter(e => !e.disabled && (/pdf/i.test(e.accept) || !e.accept || findModal()?.contains(e)));
    const waitForInputs=async(rounds,ms)=>{ for(let i=0;i<rounds;i++){ await waitInput(ms); allInputs=pdfInputs(); if(allInputs.length || findModal()) return; } };
    // 附件区定位：新版每个 section 的 action 区放“添加”图标；附件已达上限时 action 为空。
    const findAttachSection=()=>{
      for(const title of Array.from(document.querySelectorAll('[class*="sectionTitle"]')).filter(visible)){
        if((title.textContent||'').trim()!=='附件简历')continue;
        let section=title.parentElement;
        while(section && !/section--/.test(classOf(section)))section=section.parentElement;
        if(section)return section;
      }
      return null;
    };
    const attachmentSection=findAttachSection();
    const attachmentCount=attachmentSection?attachmentSection.querySelectorAll('[class*="attachmentCard--"], .attachment-view-box .resume-card-container').length:0;
    const addEntry=attachmentSection?attachmentSection.querySelector('[data-nick="resume-add-icon"],[class*="addIcon"]'):null;
    const sectionNote=(extra=[])=>['附件区:'+(attachmentSection?'已找到':'未找到'),'已有附件:'+attachmentCount,'添加图标:'+(addEntry?'有':'无')].concat(extra);
    if(!addEntry && attachmentCount>=3){
      // 平台附件简历上限为 3；已达上限时上传入口不会渲染，继续点击旧入口只会空转。
      // 只回传结构化 token，由 App 显示本地化说明并提供清理入口；内部诊断行不进入面向用户的提示。
      finish('not_submitted',['attachment_quota_reached']);
      return;
    }
    window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'});
    // 简历编辑页可能使用内层滚动容器，不能只滚 window。
    for (const el of Array.from(document.querySelectorAll('div,main,section')).slice(0,400)) {
      try { if (el.scrollHeight > el.clientHeight + 200) el.scrollTop = el.scrollHeight; } catch {}
    }
    let allInputs = [];
    const pointerClick=(el)=>{
      const rect=typeof el.getBoundingClientRect==='function'?el.getBoundingClientRect():{x:0,y:0,width:0,height:0};
      const opts={bubbles:true,cancelable:true,view:window,clientX:rect.x+Math.max(1,Math.min(rect.width/2,10)),clientY:rect.y+Math.max(1,Math.min(rect.height/2,10)),button:0};
      for(const type of ['pointerover','mouseover','mousemove','pointerdown','mousedown','pointerup','mouseup','click']){
        try{el.dispatchEvent(new MouseEvent(type,opts));}catch{}
      }
    };
    let entryAttempted=false;
    if(addEntry){
      entryAttempted=true;
      pointerClick(addEntry);
      await waitInput(900);
      allInputs=pdfInputs();
      if(!allInputs.length && !findModal()) await waitForInputs(6,400);
      if(!allInputs.length && !findModal()){
        // 「+」也可能先展开“从本地上传/从在线简历选择”的菜单，再点其中一项才出现 file 控件。
        const entries=Array.from(document.querySelectorAll('[class*="dropdown-menu-item"],[role="menuitem"],[class*="menu-item"]'))
          .filter(visible).filter(e=>/上传|本地|选择文件/.test(e.innerText||''));
        if(entries.length===1){
          pointerClick(entries[0]);
          await waitInput(900);
          allInputs=pdfInputs();
          if(!allInputs.length && !findModal()) await waitForInputs(4,400);
        }
      }
      if(!allInputs.length && !findModal()){
        finish('not_submitted',['点击附件添加入口后未出现上传弹窗或文件控件'].concat(sectionNote()));
        return;
      }
    } else {
      await waitForInputs(4,350);
    }
    if (!entryAttempted && !allInputs.length && !findModal()) {
      const titles=Array.from(document.querySelectorAll('body *')).filter(e=>visible(e) && (e.textContent||'').includes('附件简历') && (e.textContent||'').trim().length<=20);
      // 标题容器（sectionHeader）通常只有「标题 + 加号」两个控件；先点最后一个可交互子元素。
      for (const title of titles.slice(0,4)) {
        const header=title.parentElement;
        if(!header) continue;
        const controls=Array.from(header.querySelectorAll('button,a,span,i,svg,[role="button"],[class*="addIcon"]')).filter(visible).reverse();
        for (const el of controls) {
          el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
          await waitInput(500);
          allInputs=pdfInputs();
          if(allInputs.length || findModal()) break;
        }
        if(allInputs.length || findModal()) break;
      }
      // 再按“标题行右侧”几何位置找加号，避免依赖平台不稳定的 class。
      for (const title of titles.slice(0,4)) {
        const rect=title.getBoundingClientRect();
        const row=title.parentElement;
        if(!row) continue;
        const rrect=row.getBoundingClientRect();
        const points=[];
        for(let x=rrect.right-8; x>rect.right+24; x-=8) points.push([x, rect.top+rect.height/2]);
        for(const [x,y] of points){
          const el=document.elementFromPoint(x,y);
          if(!el || !visible(el) || el===title || title.contains(el)) continue;
          el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
          await waitInput(500);
          allInputs=pdfInputs();
          if(allInputs.length || findModal()) break;
        }
        if(allInputs.length || findModal()) break;
      }
      const candidates=[];
      if (!allInputs.length && !findModal()) for (const title of titles.slice(0,4)) {
        let node=title;
        for (let depth=0;node && depth<6;depth++,node=node.parentElement) {
          for (const el of node.querySelectorAll('button,[role="button"],span,i,svg,a')) {
            if (!visible(el)) continue;
            const text=(el.textContent||'').trim();
            const cls=classOf(el);
            if (text==='+' || text==='添加' || /plus|add|upload|attach/i.test(cls) || /添加|上传/.test(el.getAttribute('aria-label')||'')) candidates.push(el);
          }
          if (candidates.length) break;
        }
      }
      const ordered=candidates.filter((el,i)=>candidates.indexOf(el)===i).slice(0,8);
      for (const el of ordered) {
        el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
        await waitInput(600);
        allInputs=pdfInputs();
        if (allInputs.length || findModal()) break;
      }
      if (!allInputs.length && !findModal()) await waitForInputs(12,400);
    }
    // 弹窗出现后其内部 file 控件可能延迟挂载，再等一轮。
    if (!allInputs.length && findModal()) await waitForInputs(6,300);
    let modalDropzone = null;
    if (!allInputs.length) {
      const modal = findModal();
      if (modal) {
        const zones = Array.from(modal.querySelectorAll('*')).filter(e=>visible(e) && /拖拽|拖入|点击上传|选择文件/.test(e.textContent||'') && e.children.length<=4);
        modalDropzone = zones[zones.length-1] || modal;
      }
    }
    let best = [];
    let candidates = [];
    if (!modalDropzone) {
      candidates = allInputs.map(e => {
        let text='', node=e;
        for(let i=0;node && i<6;i++,node=node.parentElement) text += ' ' + (node.innerText || '');
        const score = /附件简历|上传附件/.test(text) ? 3 : /附件/.test(text) ? 2 : 1;
        const visibleInput = Boolean(e.getClientRects().length);
        return {input:e, score, visible:visibleInput, text:text.replace(/\s+/g,' ').slice(0,120)};
      });
      const bestScore = candidates.length ? Math.max(...candidates.map(c=>c.score)) : 0;
      best = candidates.filter(c=>c.score===bestScore && (bestScore>1 || c.visible));
      if (best.length !== 1) { finish('not_submitted',['附件控件不唯一:共'+allInputs.length+'个，候选:'+candidates.map(c=>c.score).join(','), '弹窗:'+(findModal()?'已出现':'未出现')+'，file控件总数:'+document.querySelectorAll('input[type="file"]').length].concat(sectionNote())); return; }
    }
    const inputs = modalDropzone ? [] : [best[0].input];
    const bytes = new Uint8Array(payload.pdf_bytes);
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(b=>b.toString(16).padStart(2,'0')).join('');
    if (digest !== payload.pdf_sha256) { finish('not_submitted',['PDF 指纹不一致']); return; }
    // 只保留上传相关响应的受限业务字段，不收集请求头、Cookie 或签名凭据。
    const safe = (value,depth=0) => {
      if(depth>5) return null;
      if(Array.isArray(value)) return value.slice(0,10).map(v=>safe(v,depth+1));
      if(value && typeof value==='object') return Object.fromEntries(Object.entries(value)
        .filter(([k])=>/^(data|list|result|code|errCode|flag|msg|message|success|id|name|url|path|size|encryAttachmentId|originalFileId|accessPath|auditStatus|originalExtension|file\w*|attach\w*|resAttach\w*)$/i.test(k)
          && !/token|cookie|secret|accessKey|signature|credential|policy|authorization/i.test(k))
        .slice(0,30).map(([k,v])=>[k,safe(v,depth+1)]));
      if(typeof value==='string')return (/^(https?:\/\/|\/)/i.test(value)?value.split(/[?#]/,1)[0]:value).slice(0,2000);
      return typeof value==='number'||typeof value==='boolean'||value===null?value:null;
    };
    const capture = (method,url,status,value) => {
      try {
        const parsed = new URL(url,location.origin);
        if(!/upload|attach/i.test(parsed.pathname) || responses.length>=8) return;
        parsed.search='';parsed.hash='';
        const filtered = JSON.stringify(safe(value));
        responses.push({method:String(method).slice(0,8),url:parsed.href,http_status:status,payload:filtered.length<=5000?filtered:'[response-too-large]'});
      } catch {}
    };
    const oldFetch=window.fetch, proto=XMLHttpRequest.prototype,oldOpen=proto.open,oldSend=proto.send;
    window.fetch=async function(input,init){if(!canWrite() && String(init?.method||input?.method||'GET').toUpperCase()!=='GET')throw Error('daily_write_cancelled');const response=await oldFetch.apply(this,arguments);
      response.clone().json().then(data=>capture(init?.method||'GET',typeof input==='string'?input:input.url,response.status,data)).catch(()=>{});return response;};
    proto.open=function(method,url){this.__ppfUploadRequest={method,url};return oldOpen.apply(this,arguments);};
    proto.send=function(){if(!canWrite() && String(this.__ppfUploadRequest?.method||'GET').toUpperCase()!=='GET')throw Error('daily_write_cancelled');this.addEventListener('load',()=>{try{const r=this.__ppfUploadRequest;if(r)capture(r.method,r.url,this.status,this.responseType==='json'?this.response:JSON.parse(this.responseText));}catch{}});return oldSend.apply(this,arguments);};
    restore=()=>{window.fetch=oldFetch;proto.open=oldOpen;proto.send=oldSend;};
    if(!canWrite()){finish('not_submitted',['授权已暂停或到期']);return;}
    const transfer=new DataTransfer();transfer.items.add(new File([bytes],payload.filename,{type:'application/pdf'}));
    if (modalDropzone) {
      // 新版猎聘先把附件上传放进弹窗；用 drop 事件触发，不打开系统文件选择器。
      for (const type of ['dragenter','dragover','drop']) {
        modalDropzone.dispatchEvent(new DragEvent(type,{bubbles:true,cancelable:true,dataTransfer:transfer}));
        await new Promise(r=>setTimeout(r,300));
      }
      dispatched=true;
    } else {
      inputs[0].files=transfer.files;
      dispatched=true;
      inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
    }
    // 若选择文件后弹窗仍停留且没有上传中/成功提示，点一次弹窗内唯一的上传/确定按钮（不改其它控件）。
    setTimeout(()=>{
      const modal=findModal();
      if(!modal) return;
      const text=(modal.innerText||'').replace(/\s+/g,'');
      if(/上传中|解析中|上传成功|上传失败/.test(text)) return;
      const buttons=Array.from(modal.querySelectorAll('button')).filter(b=>visible(b)&&!b.disabled&&/^(上传|确定|确认|开始上传|上传附件)$/.test((b.innerText||'').replace(/\s+/g,'')));
      if(buttons.length===1){try{buttons[0].click();}catch{}}
    },1200);
    let rounds=0;
    const observe=()=>{
      const text=document.body?.innerText||'';
      const hints=text.split('\n').map(s=>s.trim()).filter(s=>s.includes(stem)||/上传成功|上传失败|上传完成|上传中|解析中|解析完成|文件大小|附件名称|暂不支持|最多.*附件/.test(s)).slice(0,15).map(s=>s.slice(0,180));
      if (text.includes(stem) && !/上传中|正在上传/.test(text)) {finish('uploaded',hints);return;}
      if (/上传失败/.test(text) || ++rounds>=30) {finish('unknown',hints);return;}
      setTimeout(observe,500);
    };
    setTimeout(observe,500);
  } catch { finish(dispatched?'unknown':'not_submitted',['未获得可确认的上传结果']); }
})();
