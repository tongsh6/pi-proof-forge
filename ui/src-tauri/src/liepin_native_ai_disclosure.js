(async () => {
  // 投递 AI 声明：在目标沟通会话中真实发送一条声明消息，并留下发送证据。
  // 只读取页面状态、只写这一条聊天消息；不选择附件、不点击投递。声明未确认时不得继续发简历。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const normalize=s=>String(s==null?'':s).normalize('NFKC').replace(/[\s·•]/g,'').toLowerCase();
  const brief=(value,limit)=>String(value==null?'':value).replace(/\s+/g,' ').slice(0,limit);
  const text=String((payload.ai_disclosure&&payload.ai_disclosure.text)||'');
  const detail={probe:'ai_disclosure',url:clean(location.href),action:{click_issued:false,reason:''},context:null,
    ai_disclosure:{text:text,confirmed:false,evidence:'',dom_confirmed:false},network:[],controls:[]};
  try{
    if(!text){detail.action.reason='disclosure_text_missing';}
    else if(clean(location.href)!==clean(payload.job_url)){detail.action.reason='target_url_mismatch';}
    else{
      // 只在已含目标公司、岗位的沟通上下文里操作；class 需属于真实聊天容器。
      const contexts=Array.from(document.querySelectorAll('[class*="im-ui"]')).filter(visible).filter(e=>{
        if(!String(e.className||'').includes('im-ui-chat'))return false;
        const inner=e.innerText||'';
        return normalize(inner).includes(normalize(payload.company))&&normalize(inner).includes(normalize(payload.position));
      });
      const context=contexts.find(e=>String(e.className||'').includes('im-ui-chat-container'))||contexts[0]||null;
      if(!context){detail.action.reason='active_recipient_not_verified';}
      else{
        detail.context={class_name:brief(context.className,200),text:brief(context.innerText,600)};
        const already=normalize(context.innerText).includes(normalize(text));
        if(already){
          // 重试幂等：同一会话已能看到声明原文时视为已发送，不重复发一条。
          detail.action={click_issued:true,reason:'approved_ai_disclosure_send'};
          detail.ai_disclosure={text:text,confirmed:true,evidence:'dom',dom_confirmed:true};
        }else{
          const input=Array.from(document.querySelectorAll('textarea.im-ui-textarea,textarea')).filter(visible)[0]||null;
          const findSend=()=>Array.from(document.querySelectorAll('.im-ui-basic-send-btn,button')).filter(visible)
            .filter(e=>e.textContent.trim()==='发送')[0]||null;
          if(!input){detail.action.reason='composer_missing';}
          else if(!findSend()){detail.action.reason='send_button_missing';}
          else if(payload.write_deadline_ms && (Date.now()>=payload.write_deadline_ms
            || (payload.daily_cycle && window.__ppfCancelledDailyCycle===payload.daily_cycle))){detail.action.reason='daily_write_cancelled';}
          else{
            const evidence=[];
            const safe=(value,depth=0)=>{
              if(depth>5)return null;
              if(Array.isArray(value))return value.slice(0,8).map(v=>safe(v,depth+1));
              if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value)
                .filter(([k])=>!/token|cookie|secret|password|authorization|signature|csrf|credential|accesskey|^tk$/i.test(k))
                .slice(0,30).map(([k,v])=>[k,safe(v,depth+1)]));
              return typeof value==='string'?value.slice(0,1200):typeof value==='number'||typeof value==='boolean'||value===null?value:null;
            };
            const decode=value=>{if(typeof value!=='string')return value;try{return JSON.parse(value);}catch{return Object.fromEntries(new URLSearchParams(value));}};
            const capture=(method,target,request,status,response)=>{
              try{
                const url=new URL(target,location.href);url.search='';url.hash='';
                if(String(method).toUpperCase()!=='POST' || !/send|message|chat/i.test(url.pathname) || evidence.length>=4)return;
                evidence.push({method:'POST',url:url.href,http_status:status,
                  request:JSON.stringify(safe(decode(request))).slice(0,1500),
                  response:JSON.stringify(safe(response)).slice(0,1500)});
              }catch(error){}
            };
            const oldFetch=window.fetch,proto=XMLHttpRequest.prototype,oldOpen=proto.open,oldSend=proto.send;
            window.fetch=async function(input,init){
              const response=await oldFetch.apply(this,arguments);
              response.clone().json().then(data=>capture(init?.method||'GET',typeof input==='string'?input:input.url,init?.body,response.status,data)).catch(()=>{});
              return response;
            };
            proto.open=function(method,url){this.__ppfDisclosureRequest={method,url};return oldOpen.apply(this,arguments);};
            proto.send=function(body){
              this.addEventListener('load',()=>{try{const r=this.__ppfDisclosureRequest;if(r)capture(r.method,r.url,body,this.status,this.responseType==='json'?this.response:JSON.parse(this.responseText));}catch(error){}});
              return oldSend.apply(this,arguments);
            };
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
            await wait(300);
            const button=findSend();
            if(!button||button.disabled){detail.action.reason='send_button_disabled';}
            else{
              detail.action={click_issued:true,reason:'approved_ai_disclosure_send'};
              button.click();
              await wait(1600);
              const network_ok=evidence.some(item=>item.http_status===200&&String(item.request||'').includes(text));
              const dom_ok=normalize(context.innerText).includes(normalize(text));
              detail.network=evidence.slice(0,4);
              // 后端契约同时接受 ai_disclosure.network 与顶层 network；两处都写，避免历史形状漂移。
              detail.ai_disclosure={text:text,confirmed:network_ok||dom_ok,evidence:network_ok?'network':dom_ok?'dom':'',dom_confirmed:dom_ok,network:evidence.slice(0,4)};
              if(!(network_ok||dom_ok))detail.action.reason='disclosure_not_confirmed';
            }
            window.fetch=oldFetch;proto.open=oldOpen;proto.send=oldSend;
          }
        }
      }
    }
  }catch(error){detail.error=String(error).slice(0,300);}
  detail.controls=Array.from(document.querySelectorAll('.im-ui-basic-send-btn')).filter(visible).slice(0,2)
    .map(e=>({text:brief(e.textContent,20),disabled:e.disabled,class_name:brief(e.className,120)}));
  let raw=JSON.stringify(detail);
  if(raw.length>10000){
    detail.network=detail.network.slice(0,2).map(item=>({method:item.method,url:item.url,http_status:item.http_status,
      request:item.request.slice(0,800),response:item.response.slice(0,400)}));
    if(detail.context)detail.context.text=detail.context.text.slice(0,300);
    raw=JSON.stringify(detail);
  }
  const hints=['probe:ai_disclosure',detail.action.reason||'observed','confirmed:'+Boolean(detail.ai_disclosure.confirmed)]
    .map(s=>Array.from(String(s)).slice(0,180).join(''));
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),hints:hints,
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:raw}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
