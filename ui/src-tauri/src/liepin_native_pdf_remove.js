(async () => {
  const payload=UPLOAD_PAYLOAD,nonce=UPLOAD_NONCE;
  const endpoint='https://api-c.liepin.com/api/com.liepin.cresume.attachment.remove-attachment-resume';
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const detail={target:{file_id:payload.file_id,attachment_id:payload.attachment_id},action:{click_issued:false,reason:'target_unverified'},before_ids:[],after_ids:[],network:[]};
  const finish=()=>{const url=new URL(location.href);url.search='';url.hash='';
    const result={filename:payload.filename,status:detail.action.click_issued?'unknown':'not_submitted',hints:[detail.action.reason],responses:[{method:'OBSERVE',url:url.href,http_status:0,payload:JSON.stringify(detail)}]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));};
  const readCards=()=>Array.from(document.querySelectorAll('.attachment-view-box .resume-card-container')).map(card=>{
    const key=Object.keys(card).find(k=>/^__react(?:Fiber|InternalInstance)\$/.test(k));let fiber=key?card[key]:null;
    for(let i=0;fiber && i<8;i++,fiber=fiber.return){const record=fiber.memoizedProps?.attachmentResume;if(record)return{card,record};}
    return{card,record:null};
  });
  const matches=r=>r && r.fileId===payload.file_id && r.encryAttachmentId===payload.attachment_id && r.fileName===payload.filename.replace(/\.pdf$/i,'') && String(r.originalExtension).toLowerCase()==='pdf';
  let restore=()=>{},restoreTimer=null;
  try {
    const url=new URL(location.href);
    if(url.origin!=='https://c.liepin.com' || url.pathname!=='/resume/edit' || /安全验证|人机验证|滑动验证/.test(document.body?.innerText||'')){finish();return;}
    const previews=Array.from(document.querySelectorAll('.ant-modal-content')).filter(visible);
    detail.overlay_diagnostics=previews.slice(0,4).map(e=>({class_name:String(e.className||''),
      sync_notice:(e.innerText||'').replace(/\s/g,'').includes('经历可同步至在线简历中'),
      sync_explanation:(e.innerText||'').replace(/\s/g,'').includes('无需手动填写，可直接添加到在线简历中'),
      input_count:e.querySelectorAll('input,textarea,select').length,
      buttons:Array.from(e.querySelectorAll('button')).slice(0,8).map(b=>({text:(b.textContent||'').trim().slice(0,80),label:b.getAttribute?.('aria-label')||'',class_name:String(b.className||'')})),
      close_count:Array.from(e.querySelectorAll('button.ant-modal-close')).filter(e=>visible(e) && !e.disabled).length}));
    if(previews.length===1){
      const text=(previews[0].innerText||'').replace(/\s/g,'');
      const closers=Array.from(previews[0].querySelectorAll('button.ant-modal-close')).filter(e=>visible(e) && !e.disabled);
      if(text.includes('经历可同步至在线简历中') && text.includes('无需手动填写，可直接添加到在线简历中')
        && previews[0].querySelectorAll('input,textarea,select').length===0 && closers.length===1){
        // 关闭已核实的只读解析预览提示；不点击查看、同步或保存经历。
        closers[0].click();await wait(300);
      }
    }
    if(Array.from(document.querySelectorAll('.ant-modal-content')).some(visible) || Array.from(document.querySelectorAll('.ant-dropdown-menu-item')).some(visible)){detail.action.reason='existing_overlay_blocks_removal';finish();return;}
    const before=readCards(),targets=before.filter(x=>matches(x.record));
    if(before.length!==payload.attachment_count || before.some(x=>!x.record?.fileId) || new Set(before.map(x=>x.record.fileId)).size!==before.length || targets.length!==1){finish();return;}
    detail.before_ids=before.map(x=>x.record.fileId);
    const more=Array.from(targets[0].card.querySelectorAll('.more-icon')).filter(visible);
    if(more.length!==1){finish();return;}
    // 只展开已核实卡片的菜单；不使用无范围的“删除”按钮。
    const requestId=body=>{
      if(body instanceof FormData){const values=body.getAll('encryAttachmentId');return values.length===1 && typeof values[0]==='string'?values[0]:null;}
      if(typeof body==='string'){
        try{
          const value=JSON.parse(body),wrapped=value && Object.prototype.hasOwnProperty.call(value,'data');
          if(wrapped && (Object.keys(value).length!==1 || (body.match(/"data"\s*:/g)||[]).length!==1))return null;
          const data=wrapped?value.data:value;
          return data && Object.keys(data).length===1 && (body.match(/"encryAttachmentId"\s*:/g)||[]).length===1 && typeof data.encryAttachmentId==='string'?data.encryAttachmentId:null;
        }
        catch{const values=new URLSearchParams(body).getAll('encryAttachmentId');return values.length===1?values[0]:null;}
      }
      return null;
    };
    detail.allowed_requests=0;detail.blocked_requests=0;
    const allow=(method,target,body)=>{
      try{
        const u=new URL(target,location.href);u.search='';u.hash='';
        const protectedMutation=u.origin==='https://api-c.liepin.com' && u.pathname.startsWith('/api/com.liepin.cresume.') && /(?:remove|delete|save|set|update|create)-/.test(u.pathname);
        if(!protectedMutation)return true;
        if(u.href!==endpoint || String(method).toUpperCase()!=='POST' || !detail.action.click_issued || detail.allowed_requests!==0 || requestId(body)!==payload.attachment_id){detail.blocked_requests++;return false;}
        detail.allowed_requests++;return true;
      }catch{detail.blocked_requests++;return false;}
    };
    const capture=(method,target,body,status,response)=>{
      try{
        const u=new URL(target,location.href);u.search='';u.hash='';if(String(method).toUpperCase()!=='POST' || u.href!==endpoint || detail.network.length>=3)return;
        detail.network.push({method:'POST',url:endpoint,http_status:status,request:JSON.stringify({encryAttachmentId:requestId(body)?.slice(0,180)||''}),response:JSON.stringify({flag:typeof response?.flag==='number'?response.flag:null})});
      }catch{}
    };
    const oldFetch=window.fetch,proto=XMLHttpRequest.prototype,oldOpen=proto.open,oldSend=proto.send;
    window.fetch=async function(input,init){const target=typeof input==='string'?input:input.url;if(!allow(init?.method||'GET',target,init?.body))throw Error('ATTACHMENT_REMOVAL_REQUEST_BLOCKED');const response=await oldFetch.apply(this,arguments);response.clone().json().then(data=>capture(init?.method||'GET',typeof input==='string'?input:input.url,init?.body,response.status,data)).catch(()=>{});return response;};
    proto.open=function(method,url){this.__ppfRemoval={method,url};return oldOpen.apply(this,arguments);};
    proto.send=function(body){const request=this.__ppfRemoval;if(!request || !allow(request.method,request.url,body))return;this.addEventListener('load',()=>{try{const r=this.__ppfRemoval;if(r)capture(r.method,r.url,body,this.status,this.responseType==='json'?this.response:JSON.parse(this.responseText));}catch{}});return oldSend.apply(this,arguments);};
    restore=()=>{window.fetch=oldFetch;proto.open=oldOpen;proto.send=oldSend;};restoreTimer=setTimeout(restore,30000);
    more[0].dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));await wait(500);
    const menus=Array.from(document.querySelectorAll('.ant-dropdown-menu-item')).filter(e=>visible(e) && e.textContent.trim()==='删除');
    if(menus.length!==1){detail.action.reason='removal_menu_not_unique';finish();return;}
    menus[0].click();await wait(600);
    const modals=Array.from(document.querySelectorAll('.ant-modal-content')).filter(e=>visible(e) && (e.innerText||'').replace(/\s/g,'').includes('注意：此操作不可恢复，您确定要删除吗？'));
    const current=readCards(),currentTargets=current.filter(x=>matches(x.record));
    const currentIds=current.map(x=>x.record?.fileId);
    if(modals.length!==1 || currentTargets.length!==1 || JSON.stringify([...currentIds].sort())!==JSON.stringify([...detail.before_ids].sort())){detail.action.reason='removal_confirmation_not_verified';finish();return;}
    const buttons=Array.from(modals[0].querySelectorAll('button.ant-btn-primary')).filter(e=>visible(e) && !e.disabled && /^(确定|确认|删除|确认删除)$/.test(e.textContent.replace(/\s/g,'')));
    if(buttons.length!==1){detail.action.reason='removal_confirmation_not_unique';finish();return;}
    detail.action={click_issued:true,reason:'confirmed_bound_attachment_removal'};buttons[0].click();
    for(let i=0;i<20;i++){
      await wait(300);const cards=readCards();
      if(cards.every(x=>x.record?.fileId)){detail.after_ids=cards.map(x=>x.record.fileId);if(detail.network.length && !detail.after_ids.includes(payload.file_id))break;}
    }
  }catch{detail.action.reason=detail.action.click_issued?'removal_receipt_unknown':'removal_not_started';}
  finally{if(restoreTimer!==null)clearTimeout(restoreTimer);restore();}
  finish();
})();
