(async () => {
  const nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const fileInputs=()=>Array.from(document.querySelectorAll('input[type="file"]')).map(e=>({accept:String(e.accept||'').slice(0,60),disabled:e.disabled,visible:visible(e),cls:String(e.className||'').slice(0,80)}));
  const info={url:location.href,titles:[],ancestors:[],clickables:[],clicked:null,modals:[],inputs_before:[],inputs_after:[]};
  const finish=()=>{
    info.inputs_after=fileInputs();
    // 回传走 not_submitted 状态并按 ≤170 字符分片，以通过宿主侧 normalize_upload_observation 的校验（每条 hint ≤180，最多 20 条）。
    const text=JSON.stringify(info);
    const hints=[];
    for(let i=0;i<text.length && hints.length<20;i+=170) hints.push(text.slice(i,i+170));
    const result={status:'not_submitted',filename:'diagnostic',hints,responses:[]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));
  };
  try{
    window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
    for (const el of Array.from(document.querySelectorAll('div,main,section')).slice(0,400)) {
      try { if (el.scrollHeight > el.clientHeight + 200) el.scrollTop = el.scrollHeight; } catch {}
    }
    await wait(1200);
    info.inputs_before=fileInputs();
    const all=Array.from(document.querySelectorAll('body *'));
    const titles=all.filter(e=>visible(e) && (e.textContent||'').trim()==='附件简历' && e.children.length<=4).slice(0,3);
    for(const title of titles){
      info.titles.push({tag:title.tagName,cls:String(title.className||'').slice(0,80)});
      let node=title;
      for(let d=0;node && d<5;d++,node=node.parentElement){
        if(d>=1) info.ancestors.push({d,tag:node.tagName,cls:String(node.className||'').slice(0,80),text:(node.innerText||'').replace(/\s+/g,' ').slice(0,80)});
        for(const el of node.querySelectorAll('button,[role="button"],i,span,a,svg')){
          if(!visible(el)) continue;
          const text=(el.textContent||'').trim();
          const cls=String(el.className?.baseVal ?? el.className ?? '');
          if(text==='+' || text==='添加' || /plus|add|upload|attach/i.test(cls) || /添加|上传/.test(el.getAttribute('aria-label')||'')){
            if(!info.clickables.some(c=>c.html===String(el.outerHTML||'').slice(0,160)))
              info.clickables.push({tag:el.tagName,cls:cls.slice(0,80),text:text.slice(0,20),html:String(el.outerHTML||'').slice(0,160)});
          }
        }
      }
    }
    // 主动点一次首个候选，记录是否弹出上传弹窗或生成 file 控件；只打开弹窗，不选择文件。
    const target=info.clickables[0] && Array.from(document.querySelectorAll(info.clickables[0].tag.toLowerCase())).find(el=>String(el.outerHTML||'').slice(0,160)===info.clickables[0].html);
    if(target){
      target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
      await wait(800);
      info.clicked=info.clickables[0].html.slice(0,80);
    }
    info.modals=Array.from(document.querySelectorAll('[class*="modal"],[class*="Modal"],[class*="dialog"],[class*="Dialog"],[role="dialog"]'))
      .filter(visible).slice(0,4).map(e=>({cls:String(e.className||'').slice(0,80),text:(e.innerText||'').replace(/\s+/g,' ').slice(0,120)}));
    finish();
  }catch(e){info.error=String(e).slice(0,120);finish();}
})();
