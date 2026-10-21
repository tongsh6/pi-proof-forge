(async () => {
  const payload=UPLOAD_PAYLOAD, nonce=UPLOAD_NONCE;
  const wait=ms=>new Promise(r=>setTimeout(r,ms));
  const visible=e=>Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility!=='hidden');
  const readCards=()=>Array.from(document.querySelectorAll('.attachment-view-box .resume-card-container')).map(card=>{
    const key=Object.keys(card).find(k=>/^__react(?:Fiber|InternalInstance)\$/.test(k));let fiber=key?card[key]:null;
    for(let i=0;fiber && i<10;i++,fiber=fiber.return){
      const record=fiber.memoizedProps?.attachmentResume;
      if(record)return{card,record};
    }
    return{card,record:null};
  });
  // 仅清理 App 自身命名规则的旧 PDF：姓名-公司-岗位-YYYYMMDD.序号
  const isAppGenerated=r=>r && String(r.originalExtension||'').toLowerCase()==='pdf' && /-\d{8}\.\d+$/.test(String(r.fileName||''));
  const detail={removed:[],skipped:[],failures:[],before_count:0,after_count:0};
  const finish=(status,hints=[])=>{const u=new URL(location.href);u.search='';u.hash='';
    const result={status,filename:'',hints,responses:[{method:'OBSERVE',url:u.href,http_status:0,payload:JSON.stringify(detail).slice(0,8000)}]};
    location.href='piproofforge-pdf://result?nonce='+encodeURIComponent(nonce)+'&payload='+encodeURIComponent(JSON.stringify(result)));};
  try{
    if(location.origin!=='https://c.liepin.com' || location.pathname!=='/resume/edit' || /安全验证|人机验证|滑动验证/.test(document.body?.innerText||'')){finish('not_submitted',['附件页未就绪']);return;}
    for(let round=0;round<20;round++){
      const cards=readCards();
      if(round===0)detail.before_count=cards.length;
      const target=cards.find(x=>isAppGenerated(x.record) && !detail.removed.some(name=>name===x.record.fileName));
      if(!target){
        detail.skipped=cards.filter(x=>x.record && !isAppGenerated(x.record)).map(x=>String(x.record.fileName||'')).slice(0,20);
        break;
      }
      const name=String(target.record.fileName||'');
      const more=Array.from(target.card.querySelectorAll('.more-icon')).filter(visible);
      if(more.length!==1){detail.failures.push(name+':more_not_unique');break;}
      more[0].dispatchEvent(new MouseEvent('mouseover',{bubbles:true}));
      await wait(400);
      const menus=Array.from(document.querySelectorAll('.ant-dropdown-menu-item')).filter(e=>visible(e) && e.textContent.trim()==='删除');
      if(menus.length!==1){detail.failures.push(name+':menu_not_unique');break;}
      menus[0].click(); await wait(500);
      const modals=Array.from(document.querySelectorAll('.ant-modal-content')).filter(e=>visible(e) && (e.innerText||'').replace(/\s/g,'').includes('注意：此操作不可恢复，您确定要删除吗？'));
      if(modals.length!==1){detail.failures.push(name+':confirm_not_unique');break;}
      const buttons=Array.from(modals[0].querySelectorAll('button.ant-btn-primary')).filter(e=>visible(e) && !e.disabled && /^(确定|确认|删除|确认删除)$/.test(e.textContent.replace(/\s/g,'')));
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
