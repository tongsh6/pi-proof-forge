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
    const pdfInputs=()=>Array.from(document.querySelectorAll('input[type="file"]')).filter(e => !e.disabled && /pdf/i.test(e.accept));
    const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
    window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'});
    let allInputs = [];
    for (let i=0;i<4;i++) { await waitInput(350); allInputs=pdfInputs(); if(allInputs.length) break; }
    if (!allInputs.length) {
      const titles=Array.from(document.querySelectorAll('body *')).filter(e=>visible(e) && (e.textContent||'').includes('附件简历') && (e.textContent||'').trim().length<=20);
      // 先按“标题行右侧”几何位置找加号，避免依赖平台不稳定的 class。
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
          if(allInputs.length) break;
        }
        if(allInputs.length) break;
      }
      if (allInputs.length) { /* 已通过标题行右侧加号取得控件 */ }
      const candidates=[];
      for (const title of titles.slice(0,4)) {
        let node=title;
        for (let depth=0;node && depth<6;depth++,node=node.parentElement) {
          for (const el of node.querySelectorAll('button,[role="button"],span,i')) {
            if (!visible(el)) continue;
            const text=(el.textContent||'').trim();
            const cls=String(el.className||'');
            if (text==='+' || /plus|add/i.test(cls) || el.getAttribute('aria-label')?.includes('添加')) candidates.push(el);
          }
          if (candidates.length) break;
        }
      }
      const ordered=candidates.filter((el,i)=>candidates.indexOf(el)===i).slice(0,8);
      for (const el of ordered) {
        el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
        await waitInput(600);
        allInputs=pdfInputs();
        if (allInputs.length) break;
      }
      if (!allInputs.length) {
        for (let i=0;i<12;i++) { await waitInput(400); allInputs=pdfInputs(); if(allInputs.length) break; }
      }
    }
    let modalDropzone = null;
    if (!allInputs.length) {
      const modal = Array.from(document.querySelectorAll('.ant-modal-content')).find(e=>visible(e) && /上传附件简历/.test(e.innerText||''));
      if (modal) {
        const zones = Array.from(modal.querySelectorAll('*')).filter(e=>visible(e) && /拖拽|点击上传/.test(e.textContent||'') && e.children.length<=4);
        modalDropzone = zones[zones.length-1] || modal;
      }
    }
    let best = [];
    let candidates = [];
    if (!modalDropzone) {
      candidates = allInputs.map(e => {
        let text='', node=e;
        for(let i=0;node && i<6;i++,node=node.parentElement) text += ' ' + (node.innerText || '');
        const score = /附件简历|上传附件|附件简历/.test(text) ? 3 : /附件/.test(text) ? 2 : 1;
        const visible = Boolean(e.getClientRects().length);
        return {input:e, score, visible, text:text.replace(/\s+/g,' ').slice(0,120)};
      });
      const bestScore = candidates.length ? Math.max(...candidates.map(c=>c.score)) : 0;
      best = candidates.filter(c=>c.score===bestScore && (bestScore>1 || c.visible));
      if (best.length !== 1) { finish('not_submitted',['附件控件不唯一:共'+allInputs.length+'个，候选:'+candidates.map(c=>c.score).join(',')]); return; }
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
