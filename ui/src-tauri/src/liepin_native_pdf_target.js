(() => {
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const visible=e=>Boolean(e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const normalize=s=>String(s).normalize('NFKC').replace(/\s/g,'').toLowerCase();
  const body=document.body?.innerText||'';
  const url=new URL(location.href);url.search='';url.hash='';
  const expected=new URL(payload.job_url);expected.search='';expected.hash='';
  const company_anonymized=String(payload.company||'').trim().startsWith('某');
  const position_present=normalize(body).includes(normalize(payload.position));
  const target={url:url.href,url_match:url.href===expected.href,company_anonymized,
    // 猎聘官方匿名岗位只展示“某上海…公司”，公司名不可能出现在页面；以精确 URL + 岗位名 + 未下线作为目标核验，并记录匿名标记供审计。
    company_present:company_anonymized?position_present:normalize(body).includes(normalize(payload.company)),position_present,
    challenge:/安全验证|人机验证|滑动验证/.test(body),
    controls:Array.from(document.querySelectorAll('a,button,span,div')).filter(e=>visible(e) && /^(投递简历|立即投递|立即应聘|应聘职位|申请职位|聊一聊|立即沟通|继续沟通|已投递|已申请|发简历|发送简历|投个简历)$/.test(e.textContent.trim()) && !Array.from(e.children).some(c=>c.textContent.trim()===e.textContent.trim()))
      .slice(0,20).map(e=>({label:e.textContent.trim(),tag:e.tagName,class_name:e.className})),
    unavailable:/该职位已下线|该职位已停止招聘|职位已关闭/.test(body)};
  const result={status:'unknown',filename:payload.filename,hints:target.controls.map(c=>c.label),responses:[{method:'OBSERVE',url:url.href,http_status:0,payload:JSON.stringify(target)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
