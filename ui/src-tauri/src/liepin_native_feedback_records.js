(() => {
  // 只读读取投递记录页：从岗位链接向上找到“含状态词且只包含这一条岗位”的行容器，回传各行文本；不点击任何控件。
  const nonce=UPLOAD_NONCE;
  const clean=v=>{try{const u=new URL(v,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const STATUS=/(已投递|已查看|面试邀约|不合适|待查看|已读|感兴趣|已回复|已关闭|未通过|已拒绝)/;
  const jobIds=el=>new Set(Array.from(el.querySelectorAll('a[href*="/job/"]')).map(x=>(clean(x.href).match(/\/job\/(\d+)/)||[])[1]).filter(Boolean));
  const rows=[],seen=new Set();
  for(const a of Array.from(document.querySelectorAll('a[href*="/job/"]'))){
    const url=clean(a.href);const m=url.match(/\/job\/(\d+)/);if(!m||seen.has(m[1]))continue;
    let node=a,chosen=null;
    for(let i=0;i<10&&node.parentElement;i++){
      node=node.parentElement;
      if(jobIds(node).size>1)break;
      chosen=node;
      if(STATUS.test(norm(node.innerText||'')))break;
    }
    const card=chosen||a;
    const lines=(card.innerText||'').split('\n').map(norm).filter(Boolean).slice(0,24).map(s=>s.slice(0,60));
    rows.push({job_url:url,job_id:m[1],position:norm(a.textContent).slice(0,120),lines});
    seen.add(m[1]);if(rows.length>=48)break;
  }
  // 页面级核对信息：状态筛选词，以及页面上短状态元素的计数分布（不绑定到具体行）。
  const hints=[],hseen=new Set();
  const counts={};
  for(const e of Array.from(document.querySelectorAll('span,div,em,i,b,strong,p,a'))){
    if(e.children.length)continue;const s=norm(e.textContent);
    if(s.length<=8&&STATUS.test(s))counts[s]=(counts[s]||0)+1;
  }
  const stat=Object.entries(counts).map(([k,v])=>k+'×'+v).join(' ');if(stat)hints.push(('状态计数 '+stat).slice(0,60));
  for(const e of Array.from(document.querySelectorAll('[role="tab"],[class*="tab"],[class*="Tab"],[class*="filter"],[class*="status"],[class*="Status"]'))){
    const s=norm(e.textContent).slice(0,60);
    if(!s||hseen.has(s)||Array.from(e.children).some(c=>norm(c.textContent)===s))continue;
    hseen.add(s);hints.push(s);if(hints.length>=20)break;
  }
  const url=clean(location.href);const responses=[];let chunk=[];
  const flush=()=>{responses.push({method:'OBSERVE',url,http_status:0,payload:JSON.stringify({status:'records',discovery:{links:[]},rows:chunk})});chunk=[];};
  for(const row of rows){chunk.push(row);if(JSON.stringify(chunk).length>2400){flush();if(responses.length>=6)break;}}
  if(chunk.length&&responses.length<6)flush();
  if(!responses.length)responses.push({method:'OBSERVE',url,http_status:0,payload:JSON.stringify({status:'records',discovery:{links:[]},rows:[]})});
  const result={status:'unknown',filename:'feedback',hints:hints.slice(0,20),responses};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
