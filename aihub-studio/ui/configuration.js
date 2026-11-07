// Marketplace integration. The vendored layered UI owns drafts and saving.
{
  // Preserve the business launcher's explicit save scope. It does not change
  // the effective source, and an existing draft still supplies its own target.
  const open = Configuration.prototype.open;
  Configuration.prototype.open = function(id, tab = 'edit', target) {
    this.selected = id;
    return open.call(this, id, tab, target || this.preferred(marketplaceSaveScope) || this.preferred());
  };
  // Model lists have different real caller chains. Do not present another
  // Skill's unrelated files as part of this field's priority chain.
  const trace = Configuration.prototype.traceHTML;
  Configuration.prototype.traceHTML = function(field) {
    const original = this.snapshot;
    this.snapshot = {...original, layers: original.layers.filter(layer =>
      field.rows.some(row => row.layer === layer.id && row.status !== 'skipped') ||
      (!layer.enabled && layer.path.endsWith('settings.json') &&
       (field.id.startsWith('routing.') || field.id === 'default_skill_reminders')))};
    try { return trace.call(this, field); } finally { this.snapshot = original; }
  };
  // Input updates paint the preview without rebuilding the focused control.
  // Keep the per-field undo action in sync with the first typed draft too.
  const paint = Configuration.prototype.paint;
  Configuration.prototype.paint = function() {
    paint.call(this);
    const actions = this.root.querySelector('.edit-actions');
    if (!actions) return;
    const undo = actions.querySelector('[data-config="undo"]');
    if (this.changes()[this.selected] && !undo) {
      const button = document.createElement('button');
      button.dataset.config = 'undo'; button.textContent = '撤销本项修改';
      actions.append(button);
    } else if (!this.changes()[this.selected] && undo) undo.remove();
  };
  const app = document.querySelector('#app');
  const keyGuides = {
    AIHUB_API_KEY: {name: 'AIhub 控制台', url: 'https://api.aihubmax.com/console'},
    TIKIN_API_KEY: {name: 'Tikin 控制台', url: 'https://console.tikin.net'},
  };
  let queued = false;
  function enhanceConfiguration() {
    queued = false;
    const input = app.querySelector('[data-config-field]');
    const guide = keyGuides[input?.dataset.configField];
    if (!guide || app.querySelector('.key-acquisition')) return;
    const help = document.createElement('p');
    help.className = 'key-acquisition'; help.id = 'key-acquisition';
    const link = document.createElement('a');
    link.href = guide.url; link.textContent = guide.name;
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    help.append('还没有 API Key？前往 ', link, ' 获取，或联系团队负责人分配。');
    input.closest('.secret-row').after(help);
    input.setAttribute('aria-describedby', help.id);
  }
  new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(enhanceConfiguration); }
  }).observe(app, {childList: true, subtree: true});
}
