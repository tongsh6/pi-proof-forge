(() => {
  // 只读发现：收集文本含关键词的站内链接，不点击任何控件。
  const payload=UPLOAD_PAYLOAD,nonce=UPLOAD_NONCE;
  const clean=v=>{try{const u=new URL(v,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const keywords=(payload.discovery&&Array.isArray(payload.discovery.link_keywords)&&payload.discovery.link_keywords.length)?payload.discovery.link_keywords:['投递'];
  const links=[],seen=new Set();
  for(const a of Array.from(document.querySelectorAll('a[href]'))){
    const label=(a.textContent||'').replace(/\s+/g,' ').trim().slice(0,60);const url=clean(a.href);
    if(!url||!label||seen.has(url)||!keywords.some(k=>label.includes(k)))continue;
    seen.add(url);links.push({label,url});if(links.length>=20)break;
  }
  const detail={status:'records_page_not_found',discovery:{links},rows:[]};
  const result={status:'unknown',filename:'feedback',hints:[],responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:JSON.stringify(detail).slice(0,11000)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
