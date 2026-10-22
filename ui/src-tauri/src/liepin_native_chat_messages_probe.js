(async () => {
  // 只读探测：打开目标岗位沟通并读取聊天消息/简历发送记录；不点发送、不选附件、不投递。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const brief=(value,limit)=>String(value==null?'':value).replace(/\s+/g,' ').trim().slice(0,limit);
  const detail={probe:'chat_messages',url:clean(location.href),opened:false,action_reason:'',message_count:0,messages:[],resume_evidence:[],controls:[]};
  try{
    // 幂等打开沟通抽屉：仅点击入口，不点击发送/发简历。
    let container=Array.from(document.querySelectorAll('[class*="im-ui-chat-container"]')).filter(visible)[0];
    if(!container){
      const entries=Array.from(document.querySelectorAll('a.btn-main,a.btn-chat,button,a,span')).filter(visible)
        .filter(e=>/^(聊一聊|继续聊|立即沟通)$/.test((e.textContent||'').trim()));
      const entry=entries[0];
      if(entry){entry.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));detail.opened=true;detail.action_reason='chat_entry_clicked';await wait(2500);}
      else detail.action_reason='chat_entry_missing';
    }else{detail.opened=true;detail.action_reason='chat_already_open';}
    container=Array.from(document.querySelectorAll('[class*="im-ui-chat-container"]')).filter(visible)[0]||null;
    if(container){
      // 消息节点：取聊天容器内常见消息/简历卡片文本。
      const nodes=Array.from(container.querySelectorAll('*')).filter(visible);
      const texts=[];const seen=new Set();
      for(const node of nodes){
        const text=brief(node.innerText||node.textContent,300);
        if(!text||text.length<2||seen.has(text))continue;
        if(/简历|附件|在线简历|已发送|投递|发送成功|交换手机号|交换微信/.test(text)||node.matches('[class*="msg"],[class*="message"],[class*="card"]')){seen.add(text);texts.push({tag:node.tagName,class_name:brief(node.className,120),text:brief(text,300)});}
        if(texts.length>=25)break;
      }
      detail.messages=texts;
      detail.message_count=texts.length;
      const full=brief(container.innerText,4000);
      detail.container_excerpt=full;
      // 简历发送痕迹：消息区出现「简历」「附件简历」「在线简历」等。
      for(const keyword of ['童先生的简历','简历','附件简历','在线简历','已发送','继续聊','发简历']){
        const index=full.indexOf(keyword);
        if(index>=0)detail.resume_evidence.push({keyword,context:brief(full.slice(Math.max(0,index-80),index+160),240)});
      }
    }
    detail.controls=Array.from(document.querySelectorAll('[class*="im-ui-action-button"],[class*="im-ui-basic-send-btn"],[class*="im-ui-basic-entry"]')).filter(visible).slice(0,6)
      .map(e=>({text:brief(e.textContent,24),class_name:brief(e.className,120)}));
  }catch(error){detail.error=String(error).slice(0,200);}
  const raw=JSON.stringify(detail);
  const hints=['probe:chat_messages','messages:'+detail.message_count,'resume_evidence:'+detail.resume_evidence.length]
    .map(s=>Array.from(String(s)).slice(0,180).join(''));
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),hints,
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:raw.slice(0,11000)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
