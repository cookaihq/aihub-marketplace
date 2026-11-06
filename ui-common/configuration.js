
// Preview customization kept outside the shared runtime. Preserves its save handlers.
{
  const app = document.querySelector('#app');
  let queued = false, observedBar;
  const resize = new ResizeObserver(entries => {
    const height = Math.ceil(entries[0].target.getBoundingClientRect().height) + 'px';
    if (app.style.getPropertyValue('--savebar-height') !== height) app.style.setProperty('--savebar-height', height);
  });
  const keyGuides = {
    AIHUB_API_KEY: {name: 'AIhub 控制台', url: 'https://api.aihubmax.com/console'},
    TIKIN_API_KEY: {name: 'Tikin 控制台', url: 'https://console.tikin.net'},
  };
  function enhanceConfiguration() {
    queued = false;
    const content = app.querySelector('.config-content');
    if (!content) { resize.disconnect(); observedBar = undefined; return; }
    const bar = content.querySelector('.save-box');
    if (bar && !bar.classList.contains('pinned-save')) {
      bar.classList.add('pinned-save');
      bar.setAttribute('aria-label', '配置保存栏');
      bar.querySelector('h3')?.remove();
      const details = document.createElement('details');
      details.className = 'save-details';
      const toggle = document.createElement('summary');
      toggle.className = 'save-details-toggle';
      details.append(toggle, bar.querySelector('#summary'));
      bar.prepend(details);
    }
    if (bar) {
      const count = bar.querySelectorAll('#summary li').length;
      const toggle = bar.querySelector('.save-details-toggle');
      const label = count ? `本次修改 · ${count} 项（查看详情）` : '暂无修改';
      if (toggle.textContent !== label) toggle.textContent = label;
      if (observedBar !== bar) { resize.disconnect(); resize.observe(bar); observedBar = bar; }
    }
    for (const [id, guide] of Object.entries(keyGuides)) {
      const input = content.querySelector('#field-' + id);
      if (!input || content.querySelector('#key-help-' + id)) continue;
      const help = document.createElement('p');
      help.id = 'key-help-' + id;
      help.className = 'key-acquisition';
      const link = document.createElement('a');
      link.href = guide.url; link.textContent = guide.name;
      link.target = '_blank'; link.rel = 'noopener noreferrer';
      help.append('还没有 API Key？前往 ', link, ' 获取，或联系团队负责人分配。');
      input.closest('.secret-row').after(help);
      input.setAttribute('aria-describedby', help.id);
    }
  }
  const observe = new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(enhanceConfiguration); }
  });
  observe.observe(app, {childList: true, subtree: true});
  enhanceConfiguration();
}
