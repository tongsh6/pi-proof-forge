(() => {
  // 独立探测 1/2：只点击目标岗位的「聊一聊」入口，先回传点击意图再触发跳转。
  // 页面跳转会销毁本脚本，因此结果必须在 click 之前送达；跳转后的页面状态由独立就绪探测回传。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const normalize=s=>String(s==null?'':s).normalize('NFKC').replace(/\s/g,'').toLowerCase();
  const body=()=>document.body?document.body.innerText||'':'';
  const info={probe:'open_chat',url:clean(location.href),url_match:false,position_present:false,company_present:false,
    company_anonymized:String(payload.company||'').trim().startsWith('某'),challenge:false,login_form:false,frames:[],candidates:[],
    clicked:false,click_target:null,reason:''};
  let sent=false,target=null;
  const finish=()=>{
    if(sent)return;sent=true;
    const hints=['probe:open_chat',info.reason||'observed'].filter(Boolean).map(s=>Array.from(String(s)).slice(0,180).join(''));
    const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),hints,
      responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:JSON.stringify(info)}]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
  };
  try{
    const page_text=body();
    info.url_match=info.url===clean(payload.job_url);
    info.position_present=normalize(page_text).includes(normalize(payload.position));
    // 匿名岗位页面只展示「某…公司」，不能用公司全名做点击前置条件；改由精确 URL + 岗位名约束。
    info.company_present=normalize(page_text).includes(normalize(payload.company));
    info.challenge=/安全验证|人机验证|滑动验证/.test(page_text);
    // 该页登录后仍会渲染隐藏的登录容器；以是否出现已登录用户名/沟通入口作为登录判据。
    const logged_in=Boolean(document.querySelector('.header-quick-menu-username,.nav-user-item,[data-selector="c-logout"],.im-ui-basic-entry-title'));
    info.login_form=!logged_in && (Array.from(document.querySelectorAll('input[type="password"]')).some(visible)
      || Array.from(document.querySelectorAll('a,button')).some(e=>visible(e)&&/^(登录|登录\/注册)$/.test(e.textContent.trim())));
    info.frames=Array.from(document.querySelectorAll('iframe')).slice(0,5).map(f=>({src:clean(f.src).slice(0,200),visible:visible(f)}));
    info.candidates=Array.from(document.querySelectorAll('a,button,div,span')).filter(visible)
      .filter(e=>/^(聊一聊|继续聊|立即沟通|继续沟通|发简历|发送简历)$/.test(e.textContent.trim()))
      .slice(0,10).map(e=>({tag:e.tagName,label:e.textContent.trim(),class_name:String(e.className||'').slice(0,160)}));
    const entries=Array.from(document.querySelectorAll('a.btn-main,a.btn-chat')).filter(visible)
      .filter(e=>/^(聊一聊|继续聊)$/.test(e.textContent.trim()));
    // 同一入口在页面里同时以 btn-main / btn-chat 两份渲染；优先唯一的 btn-main，不点击不确定的入口。
    const primary=entries.filter(e=>String(e.className||'').split(/\s+/).includes('btn-main'));
    const chosen=primary.length===1?primary:(entries.length===1?entries:[]);
    if(info.challenge){info.reason='security_challenge';}
    else if(info.login_form){info.reason='login_required';}
    else if(!info.url_match){info.reason='target_url_mismatch';}
    else if(!entries.length){info.reason='chat_entry_missing';}
    else if(chosen.length!==1){info.reason='chat_entry_not_unique:'+entries.length;}
    else{
      target=chosen[0];
      info.clicked=true;
      info.reason='approved_target_chat_entry';
      info.click_target={tag:target.tagName,label:target.textContent.trim(),class_name:String(target.className||'').slice(0,160)};
    }
  }catch(error){info.error=String(error).slice(0,300);info.reason='probe_error';}
  finish();
  if(target){setTimeout(()=>{try{target.click();}catch(error){}},120);}
})();
