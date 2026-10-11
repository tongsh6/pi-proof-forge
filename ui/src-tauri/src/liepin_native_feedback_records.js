(() => {
  // 只读读取投递记录页：按岗位链接定位卡片，回传卡片各行文本与页面标签词，不点击任何控件。
  const nonce=UPLOAD_NONCE;
  const clean=v=>{try{const u=new URL(v,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const rows=[],seen=new Set();
  for(const a of Array.from(document.querySelectorAll('a[href*="/job/"]'))){
    const url=clean(a.href);const m=url.match(/\/job\/(\d+)/);if(!m||seen.has(m[1]))continue;
    let card=a;for(let i=0;i<6&&card.parentElement;i++){card=card.parentElement;if(norm(card.innerText||'').length>=40)break;}
    const lines=(card.innerText||'').split('\n').map(norm).filter(Boolean).slice(0,16).map(s=>s.slice(0,60));
    rows.push({job_url:url,job_id:m[1],position:norm(a.textContent).slice(0,120),lines});
    seen.add(m[1]);if(rows.length>=48)break;
  }
  // 页面级状态词汇（标签页、筛选项、状态徽标）只用于让后端了解真实用词。
  const hints=[],hseen=new Set();
  for(const e of Array.from(document.querySelectorAll('[role="tab"],[class*="tab"],[class*="Tab"],[class*="filter"],[class*="status"],[class*="Status"],[class*="tag"]'))){
    const s=norm(e.textContent).slice(0,60);
    if(!s||hseen.has(s)||Array.from(e.children).some(c=>norm(c.textContent)===s))continue;
    hseen.add(s);hints.push(s);if(hints.length>=20)break;
  }
  const url=clean(location.href);const responses=[];let chunk=[];
  const flush=()=>{responses.push({method:'OBSERVE',url,http_status:0,payload:JSON.stringify({status:'records',discovery:{links:[]},rows:chunk})});chunk=[];};
  for(const row of rows){chunk.push(row);if(JSON.stringify(chunk).length>2400){flush();if(responses.length>=6)break;}}
  if(chunk.length&&responses.length<6)flush();
  if(!responses.length)responses.push({method:'OBSERVE',url,http_status:0,payload:JSON.stringify({status:'records',discovery:{links:[]},rows:[]})});
  const result={status:'unknown',filename:'feedback',hints,responses};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
