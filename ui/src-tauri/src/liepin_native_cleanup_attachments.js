(async () => {
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const classOf=e=>String(e.className?.baseVal ?? e.className ?? '');
  const queryAll=(root,...selectors)=>{const out=[];for(const selector of selectors){try{out.push(...Array.from(root.querySelectorAll(selector)));}catch{}}return out;};
  const queryDocument=(...selectors)=>queryAll(document,...selectors);
  const cardNodes=()=>queryDocument('[class*="attachmentView--"] [class*="attachmentCard--"]','.attachment-view-box .resume-card-container');
  const menuNodes=()=>queryDocument('[class*="ant-c-dropdown-menu-item"]','.ant-dropdown-menu-item');
  const modalNodes=()=>queryDocument('[class*="ant-c-modal-root"]','.ant-modal-content');
  const recordOf=card=>{
    const key=Object.keys(card).find(k=>/^__react(?:Fiber|InternalInstance)\$/.test(k));
    let fiber=key?card[key]:null;
    for(let i=0;fiber && i<12;i++,fiber=fiber.return){
      const record=fiber.memoizedProps?.attachmentResume;
      if(record)return record;
    }
    return null;
  };
  const readCards=()=>cardNodes().map(card=>({card,record:recordOf(card)}));
  // 仅清理 App 自身命名规则的旧 PDF：姓名-公司-岗位-YYYYMMDD.序号
  const isAppGenerated=r=>r && String(r.originalExtension||'pdf').toLowerCase()==='pdf' && /-\d{8}\.\d+$/.test(String(r.fileName||''));
  const pointerClick=el=>{
    const rect=typeof el.getBoundingClientRect==='function'?el.getBoundingClientRect():{x:0,y:0,width:0,height:0};
    const opts={bubbles:true,cancelable:true,view:window,clientX:rect.x+Math.max(1,Math.min(rect.width/2,8)),clientY:rect.y+Math.max(1,Math.min(rect.height/2,8)),button:0};
    for(const type of ['pointerover','mouseover','mousemove','pointerdown','mousedown','pointerup','mouseup','click']){
      try{el.dispatchEvent(new MouseEvent(type,opts));}catch{}
    }
  };
  const detail={removed:[],skipped:[],failures:[],before_count:0,after_count:0,menu:'unknown',modal:'unknown'};
  const finish=(status,hints=[])=>{const u=new URL(location.href);u.search='';u.hash='';
    const result={status,filename:'',hints,responses:[{method:'OBSERVE',url:u.href,http_status:0,payload:JSON.stringify(detail).slice(0,8000)}]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result));};
  try{
    if(location.origin!=='https://c.liepin.com' || location.pathname!=='/resume/edit' || /安全验证|人机验证|滑动验证/.test(document.body?.innerText||'')){finish('not_submitted',['附件页未就绪']);return;}
    window.scrollTo({top:document.body.scrollHeight,behavior:'instant'});
    for(const el of Array.from(document.querySelectorAll('div,main,section')).slice(0,400)){
      try{if(el.scrollHeight>el.clientHeight+200)el.scrollTop=el.scrollHeight;}catch{}
    }
    await wait(600);
    for(let round=0;round<8;round++){
      const cards=readCards();
      if(round===0)detail.before_count=cards.length;
      const target=cards.find(x=>isAppGenerated(x.record) && !detail.removed.includes(String(x.record.fileName)));
      if(!target){
        detail.skipped=cards.filter(x=>x.record && !isAppGenerated(x.record)).map(x=>String(x.record.fileName||'')).slice(0,20);
        break;
      }
      const name=String(target.record.fileName||'');
      // 新版卡片操作入口：卡片内唯一的「...」下拉触发器；兼容旧 .more-icon。
      const trigger=Array.from(target.card.querySelectorAll('[class*="anticon-ellipsis"], .more-icon')).filter(visible);
      if(trigger.length!==1){detail.failures.push(name+':more_not_unique');break;}
      pointerClick(trigger[0]);
      await wait(700);
      const menus=menuNodes().filter(e=>visible(e) && (e.textContent||'').replace(/\s/g,'')==='删除');
      if(menus.length!==1){detail.failures.push(name+':menu_not_unique');break;}
      detail.menu='new';
      pointerClick(menus[0]);
      await wait(700);
      const modals=modalNodes().filter(e=>visible(e) && (e.innerText||'').replace(/\s/g,'').includes('不可恢复'));
      if(modals.length!==1){detail.failures.push(name+':confirm_not_unique');break;}
      detail.modal=classOf(modals[0]).split(/\s+/)[0]||'unknown';
      const buttons=Array.from(modals[0].querySelectorAll('button')).filter(e=>visible(e) && !e.disabled && /^(确定|确认|删除|确认删除)$/.test((e.textContent||'').replace(/\s/g,'')));
      if(buttons.length!==1){detail.failures.push(name+':confirm_button_not_unique');break;}
      const before=readCards().length;
      buttons[0].click();
      let removed=false;
      for(let i=0;i<20;i++){await wait(300);const now=readCards();if(now.length<before && !now.some(x=>String(x.record?.fileName||'')===name)){removed=true;break;}}
      if(!removed){detail.failures.push(name+':not_removed');break;}
      detail.removed.push(name);
    }
    detail.after_count=readCards().length;
    const remaining=readCards().filter(x=>isAppGenerated(x.record)).map(x=>String(x.record?.fileName||''));
    if(remaining.length){finish('unknown',['仍有旧附件未移除'].concat(remaining.slice(0,5)));return;}
    finish('success',detail.removed.length?['已移除旧附件 '+detail.removed.length+' 份']:['没有需要移除的旧附件']);
  }catch(e){finish('unknown',['清理异常'])}
})();
