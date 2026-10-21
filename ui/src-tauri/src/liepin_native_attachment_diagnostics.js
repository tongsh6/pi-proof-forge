(async () => {
  const nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const info={url:location.href,title_candidates:[],ancestors:[],clickables:[],file_inputs_before:0,file_inputs_after:0};
  const finish=()=>{
    info.file_inputs_after=document.querySelectorAll('input[type="file"]').length;
    const result={status:'diagnostic',filename:'',hints:[JSON.stringify(info).slice(0,4000)],responses:[]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result)));
  };
  try{
    window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
    await wait(1200);
    info.file_inputs_before=document.querySelectorAll('input[type="file"]').length;
    const all=Array.from(document.querySelectorAll('body *'));
    const titles=all.filter(e=>visible(e) && (e.textContent||'').trim()==='附件简历' && e.children.length<=4).slice(0,5);
    for(const title of titles){
      info.title_candidates.push({tag:title.tagName,cls:String(title.className||'').slice(0,160),html:String(title.outerHTML||'').slice(0,300)});
      let node=title;
      for(let d=0;node && d<6;d++,node=node.parentElement){
        info.ancestors.push({depth:d,tag:node.tagName,cls:String(node.className||'').slice(0,160),text:(node.innerText||'').replace(/\s+/g,' ').slice(0,160)});
        for(const el of node.querySelectorAll('button,[role="button"],i,span,a')){
          if(!visible(el)) continue;
          const text=(el.textContent||'').trim();
          const cls=String(el.className||'');
          if(text==='+' || text==='添加' || /plus|add|upload|attach/i.test(cls) || /添加|上传/.test(el.getAttribute('aria-label')||'')){
            info.clickables.push({tag:el.tagName,cls:cls.slice(0,160),text:text.slice(0,40),aria:(el.getAttribute('aria-label')||'').slice(0,80),html:String(el.outerHTML||'').slice(0,300)});
          }
        }
      }
    }
    finish();
  }catch(e){info.error=String(e).slice(0,200);finish();}
})();
