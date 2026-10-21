(() => {
  // 只读页面快照：用于诊断沟通入口缺失的真实页面状态；不点击、不导航、不写任何业务控件。
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const visible=e=>Boolean(e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');
  const clean=value=>{try{const u=new URL(value,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const brief=(value,limit)=>String(value==null?'':value).replace(/\s+/g,' ').slice(0,limit);
  const page_text=document.body?document.body.innerText||'':'';
  const hits=[];
  for(const keyword of ['聊一聊','立即沟通','继续沟通','登录','我的沟通','发简历','投递','该职位','附件简历']){
    const index=page_text.indexOf(keyword);
    if(index>=0)hits.push({keyword,context:brief(page_text.slice(Math.max(0,index-120),index+180),300)});
    if(hits.length>=8)break;
  }
  const controls=Array.from(document.querySelectorAll('a,button,[role="button"],div,span')).filter(visible)
    .filter(e=>{const t=e.textContent.trim();return t.length>0&&t.length<40&&!Array.from(e.children).some(c=>c.textContent.trim()===t);})
    .slice(0,120).map(e=>({tag:e.tagName,text:brief(e.textContent,40),class_name:brief(e.className,160)}));
  const auth={
    nav_user:Boolean(document.querySelector('.nav-user-item')),
    logout:Boolean(document.querySelector('[data-selector="c-logout"]')),
    password_inputs:Array.from(document.querySelectorAll('input[type="password"]')).filter(visible).length,
    header_login:Array.from(document.querySelectorAll('#header-quick-menu-login,.inline-login-container')).filter(visible).length,
    login_labels:Array.from(document.querySelectorAll('a,button')).filter(e=>visible(e)&&/^(登录|登录\/注册)$/.test(e.textContent.trim())).slice(0,5)
      .map(e=>({tag:e.tagName,text:brief(e.textContent,20),class_name:brief(e.className,120)}))
  };
  const detail={probe:'page_snapshot',url:clean(location.href),title:document.title,
    body_excerpt:brief(page_text,2600),keyword_hits:hits,auth,
    btn_main:Array.from(document.querySelectorAll('a.btn-main,a.btn-chat')).filter(visible).slice(0,10)
      .map(e=>({tag:e.tagName,text:brief(e.textContent,40),class_name:brief(e.className,160)})),
    im_panels:Array.from(document.querySelectorAll('[class*="im-ui"]')).filter(visible).slice(0,8)
      .map(e=>({tag:e.tagName,class_name:brief(e.className,160),text:brief(e.innerText,300)})),
    frames:Array.from(document.querySelectorAll('iframe')).slice(0,8).map(f=>({src:clean(f.src).slice(0,200),visible:visible(f)})),
    controls:controls};
  let raw=JSON.stringify(detail);
  if(raw.length>10000){detail.controls=detail.controls.slice(0,40);detail.im_panels=detail.im_panels.slice(0,4);
    detail.body_excerpt=brief(detail.body_excerpt,1600);raw=JSON.stringify(detail);}
  if(raw.length>11000){detail.controls=detail.controls.slice(0,20);detail.keyword_hits=detail.keyword_hits.slice(0,4);raw=JSON.stringify(detail);}
  const result={status:'unknown',filename:String(payload.filename||'probe').slice(0,180),
    hints:['probe:page_snapshot','controls:'+detail.controls.length,'auth:'+(auth.nav_user||auth.logout)],
    responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:raw}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
