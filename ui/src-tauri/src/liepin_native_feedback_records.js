(() => {
  // 只读读取投递记录页：按岗位链接定位卡片，提取状态词与时间，不点击任何控件。
  const nonce=UPLOAD_NONCE;
  const clean=v=>{try{const u=new URL(v,location.origin);u.search='';u.hash='';return u.href;}catch{return '';}};
  const norm=s=>(s||'').replace(/\s+/g,' ').trim();
  const STATUS=/(已投递|投递成功|已申请|已发送|待查看|未查看|已查看|已浏览|已读|查看过|被查看|感兴趣|有意向|不合适|不匹配|已拒绝|未通过|婉拒|已关闭|待沟通|已沟通|已回复|沟通中|面试|邀约|约面|合适)/;
  const TIME=/(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}(?:\s\d{1,2}:\d{2})?|\d+\s*(?:天|小时|分钟)前|今天|昨天)/;
  const rows=[],seen=new Set();
  for(const a of Array.from(document.querySelectorAll('a[href*="/job/"]'))){
    const url=clean(a.href);const m=url.match(/\/job\/(\d+)/);if(!m||seen.has(m[1]))continue;
    let card=a;for(let i=0;i<6&&card.parentElement;i++){card=card.parentElement;if(norm(card.innerText||'').length>=40)break;}
    const lines=(card.innerText||'').split('\n').map(norm).filter(Boolean);const text=norm(card.innerText||'');
    const position=norm(a.textContent).slice(0,120);
    const statusLine=lines.find(s=>STATUS.test(s)&&s.length<=40)||'';
    const timeMatch=text.match(TIME);
    const company=lines.find(s=>s!==position&&!STATUS.test(s)&&!TIME.test(s)&&s.length<=40&&!/[kK元薪]/.test(s))||'';
    rows.push({job_url:url,job_id:m[1],position,company,status_label:statusLine.slice(0,60),time_label:timeMatch?timeMatch[0]:'',excerpt:text.slice(0,80)});
    seen.add(m[1]);if(rows.length>=30)break;
  }
  const detail={status:'records',discovery:{links:[]},rows};
  const result={status:'unknown',filename:'feedback',hints:[],responses:[{method:'OBSERVE',url:clean(location.href),http_status:0,payload:JSON.stringify(detail).slice(0,11000)}]};
  location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
})();
