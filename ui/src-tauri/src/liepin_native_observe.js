(() => {
  const visible = e => Boolean(e && e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const has = selector => Array.from(document.querySelectorAll(selector)).some(visible);
  const send = attachmentView => {
    const observation = {
      url: location.origin + location.pathname,
      authenticated: has('.nav-user-item, [data-selector="c-logout"]') || (location.hostname === 'c.liepin.com' && Array.from(document.querySelectorAll('a')).some(e => visible(e) && ((e.href === 'https://c.liepin.com/resume/edit' && e.textContent.includes('编辑简历')) || (location.pathname === '/resume/edit' && e.href.startsWith('https://c.liepin.com/resume/preview?') && e.textContent.includes('预览/下载简历'))))),
      login_form: has('input[placeholder*="手机号"], input[type="password"], #header-quick-menu-login, .inline-login-container') || Array.from(document.querySelectorAll('a,button')).some(e => visible(e) && /^(登录|登录\/注册)$/.test(e.textContent.trim())),
      challenge: location.hostname === 'safe.liepin.com' || /安全验证|人机验证|滑动验证/.test(document.body?.innerText || '')
    };
    if (attachmentView) observation.attachment_view = attachmentView;
    location.href = 'piproofforge-observe://result?nonce=' + encodeURIComponent(NONCE_VALUE) + '&payload=' + encodeURIComponent(JSON.stringify(observation));
  };
  if (!INSPECT_ATTACHMENTS) { send(null); return; }
  if (location.origin !== 'https://c.liepin.com' || !['/', '/resume/edit'].includes(location.pathname)) { send(null); return; }
  const inspectAttachments = () => {
  if (location.origin !== 'https://c.liepin.com' || !['/', '/resume/edit'].includes(location.pathname)) { send(null); return; }
  if (location.pathname === '/') {
    const label = '附件简历';
    const entries = Array.from(document.querySelectorAll('*')).filter(e =>
      visible(e) && e.textContent.trim() === label && !Array.from(e.children).some(child => child.textContent.trim() === label));
    if (entries.length !== 1) { send({entry_count:entries.length, inputs:[], hints:[]}); return; }
    // 仅打开已观察到的附件管理入口；不选择文件、不上传、不发送。
    entries[0].click();
  } else {
    // 只关闭已观察到的功能介绍，不接受协议或执行简历操作。
    const notices = Array.from(document.querySelectorAll('*')).filter(e => visible(e)
      && e.textContent.trim() === '支持上传多份附件简历啦' && e.children.length === 0);
    for (const notice of notices) {
      const parent = notice.parentElement;
      const buttons = parent ? Array.from(parent.querySelectorAll('button')).filter(e => visible(e) && e.textContent.trim() === '我知道了') : [];
      if (buttons.length === 1) buttons[0].click();
    }
    if (!document.querySelectorAll('input[type="file"]').length) {
      // 已有附件时平台使用独立加号；固定官方资源的 data-testid 已核实。
      const addButtons=Array.from(document.querySelectorAll('[data-testid="attachment-resume-add-btn"]')).filter(visible);
      if(addButtons.length===1) addButtons[0].click();
      else if(addButtons.length===0){
        const openers = Array.from(document.querySelectorAll('*')).filter(e => visible(e)
          && e.textContent.trim() === '去上传' && e.children.length === 0);
        if (openers.length === 1) openers[0].click();
      }
    }
  }
  setTimeout(() => {
    const inputs = Array.from(document.querySelectorAll('input[type="file"]')).slice(0,20).map(e => ({
      accept:e.accept.slice(0,256), multiple:e.multiple, disabled:e.disabled
    }));
    const panels = Array.from(document.querySelectorAll('[role="dialog"],.ant-modal-content,.ant-drawer-body')).filter(visible);
    const text = (panels.length ? panels.map(p => p.innerText).join('\n') : document.body?.innerText) || '';
    const controls=Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible)
      .map(e=>e.textContent.trim()).filter(Boolean).slice(0,10).map(s=>'页面控件：'+Array.from(s).slice(0,160).join(''));
    const hints = [...controls,...text.split('\n').map(s => s.trim()).filter(s => /pdf|docx?|简历|附件|上传|下载|MB|KB|格式|文件大小|最多|默认|自动|发送/i.test(s)).map(s=>Array.from(s).slice(0,180).join(''))].slice(0,20);
    send({entry_count:1, inputs, hints});
  }, 1000);
  };
  // 旧附件解析后的信息提示会遮挡附件入口；仅关闭已核实的提示，不同步经历。
  const syncNotices = location.pathname === '/resume/edit' ? Array.from(document.querySelectorAll('[role="dialog"]'))
    .filter(e => visible(e) && /\d+段经历可同步至在线简历中/.test((e.innerText || '').replace(/\s/g, ''))
      && (e.innerText || '').replace(/\s/g, '').includes('无需手动填写，可直接添加到在线简历中')) : [];
  const closeButtons = syncNotices.length === 1 ? Array.from(syncNotices[0].querySelectorAll('button'))
    .filter(e => visible(e) && e.getAttribute('aria-label') === 'Close') : [];
  if (closeButtons.length === 1) {
    closeButtons[0].click();
    setTimeout(inspectAttachments, 250);
  } else inspectAttachments();
})();
