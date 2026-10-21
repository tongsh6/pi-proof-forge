(async () => {
  // 开发探测：在真实沟通页向输入框填入 AI 声明文案并确认「发送」按钮可用，随后清空，绝不点击发送。
  // 用途是在没有新投递授权的条件下验证新版输入框/发送按钮选择器；不产生任何平台写入。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const text=String((payload.ai_disclosure&&payload.ai_disclosure.text)||'');
  const normalize=s=>String(s==null?'':s).normalize('NFKC').replace(/[\s·•]/g,'').toLowerCase();
  const detail={probe:'ai_disclosure_dry_run',url:clean(location.href),reason:'',composer:null,context:null,
    value_len_after_fill:0,button_enabled_after_fill:false,cleared:false,send_clicked:false};
  try{
    if(!text){detail.reason='disclosure_text_missing';}
    else{
      // 同时验证声明脚本的目标会话上下文选择器：必须找到类名含 im-ui-chat 且文本含公司/岗位的聊天容器。
      const contexts=Array.from(document.querySelectorAll('[class*="im-ui"]')).filter(visible).filter(e=>{
        if(!String(e.className||'').includes('im-ui-chat'))return false;
        const inner=e.innerText||'';
        return normalize(inner).includes(normalize(payload.company))&&normalize(inner).includes(normalize(payload.position));
      });
      const context=contexts.find(e=>String(e.className||'').includes('im-ui-chat-container'))||contexts[0]||null;
      detail.context=context?{class_name:String(context.className||'').slice(0,200),
        contains_company:true,contains_position:true}:null;
      const input=Array.from(document.querySelectorAll('textarea.im-ui-textarea,textarea')).filter(visible)[0]||null;
      const button=Array.from(document.querySelectorAll('.im-ui-basic-send-btn,button')).filter(visible)
        .filter(e=>e.textContent.trim()==='发送')[0]||null;
      if(!context){detail.reason='active_recipient_not_verified';}
      else if(!input){detail.reason='composer_missing';}
      else{
        detail.composer={tag:input.tagName,class_name:String(input.className||'').slice(0,160),
          placeholder:String(input.getAttribute('placeholder')||'').slice(0,80),
          parent_class:String(input.parentElement?input.parentElement.className:'').slice(0,160)};
        const setValue=(el,value)=>{
          try{
            const descriptor=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el),'value');
            if(descriptor&&descriptor.set)descriptor.set.call(el,value);else el.value=value;
          }catch(error){el.value=value;}
        };
        setValue(input,text);
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));
        try{if(typeof input.focus==='function')input.focus();}catch(error){}
        await wait(400);
        const button_now=Array.from(document.querySelectorAll('.im-ui-basic-send-btn,button')).filter(visible)
          .filter(e=>e.textContent.trim()==='发送')[0]||null;
        detail.value_len_after_fill=String(input.value||'').length;
        detail.button_enabled_after_fill=Boolean(button_now&&!button_now.disabled);
        detail.reason=detail.value_len_after_fill===text.length&&detail.button_enabled_after_fill&&Boolean(detail.context)
          ?'composer_and_context_ready':'composer_not_ready';
        // 清空草稿，避免留下未发送文本；仍然不点击发送。
        setValue(input,'');
        input.dispatchEvent(new Event('input',{bubbles:true}));
        input.dispatchEvent(new Event('change',{bubbles:true}));
        await wait(120);
        detail.cleared=String(input.value||'')==='';
      }
    }
  }catch(error){detail.error=String(error).slice(0,300);}
  const hints=['probe:ai_disclosure_dry_run',detail.reason||'observed','send_clicked:false']
    .map(s=>Array.from(String(s)).slice(0,180).join(''));
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),hints:hints,
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:JSON.stringify(detail)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
