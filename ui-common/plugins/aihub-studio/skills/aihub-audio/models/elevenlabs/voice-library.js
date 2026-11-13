class ElevenLabsVoiceLibrary extends AudioVoiceLibrary {
  constructor(ui) {
    super(ui, {key:'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', favoritesKey:'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS',
      endpoint:'/api/elevenlabs-voices', title:'ElevenLabs 预置音色库', provider:'ElevenLabs', selectLabel:'选择此音色', triggerSelector:'[data-open-elevenlabs-library]'});
  }
  favoriteTarget() { return this.target || ''; }
  favorites() { return this.favoriteIds || []; }
  prepareDialog() {
    this.mode = 'choose';
    this.favoriteIds = [...(this.ui.field(this.favoritesKey).effective.value || [])];
    this.dirtyFavorites = false;
    const targets = this.ui.snapshot.default_targets;
    const scopes = ['project', 'global'].filter(scope => targets[scope] &&
      [this.key, this.favoritesKey].every(key => this.ui.field(key).targets.includes(targets[scope])));
    this.scope = scopes.includes(marketplaceSaveScope) ? marketplaceSaveScope : scopes[0];
    this.target = targets[this.scope] || '';
    const panel = document.createElement('div'); panel.className = 'eleven-save-panel';
    panel.innerHTML = `<div><label>保存到 <select aria-label="音色保存范围" id="eleven-save-scope">${scopes.map(scope =>
      `<option value="${scope}">${scope === 'project' ? '当前项目' : '全局（所有项目）'}</option>`).join('')}</select></label>
      <small id="eleven-save-path"></small></div><p id="eleven-selected" aria-live="polite"></p>
      <button class="primary" data-voice-action="save-selection">保存并使用</button>`;
    this.dialog.append(panel);
    panel.querySelector('select').value = this.scope || '';
    panel.querySelector('select').addEventListener('change', event => {
      this.scope = event.target.value; this.target = targets[this.scope]; this.paintStatus();
    });
    this.paintStatus();
  }
  paintStatus() {
    if (!this.dialog?.querySelector('.eleven-save-panel')) return;
    this.dialog.querySelector('#speech-favorite-count').textContent = `已收藏 ${this.favorites().length} 个${this.dirtyFavorites ? ' · 未保存' : ''}`;
    const favoriteSave = this.dialog.querySelector('[data-voice-action="save-favorites"]');
    favoriteSave.hidden = !this.dirtyFavorites; favoriteSave.disabled = this.saving || !this.target;
    this.dialog.querySelector('[data-voice-action="retry"]').hidden = !this.failed;
    this.dialog.querySelector('#speech-notice').textContent = this.notice || '';
    this.dialog.querySelector('#eleven-save-path').textContent = this.ui.snapshot.layers.find(row => row.id === this.target)?.path || '没有可写入的保存位置';
    const voice = this.voices.find(voice => voice.voice_id === this.selected);
    this.dialog.querySelector('#eleven-selected').textContent = this.selected ? `已选：${voice?.voice_name || this.selected}` : '请选择一个音色';
    this.dialog.querySelector('[data-voice-action="save-selection"]').disabled = this.saving || !this.target || !this.selected;
    this.dialog.querySelector('#eleven-save-scope').disabled = this.saving;
  }
  async saveSelection(withVoice = true) {
    if (this.saving || !this.target || (withVoice && !this.selected)) return;
    this.saving = true; this.ui.busy = true; this.paintStatus();
    const changes = {[this.favoritesKey]:{op:'set',value:[...this.favorites()]}};
    if (withVoice) changes[this.key] = {op:'set',value:this.selected};
    try {
      const result = await this.ui.api('/api/save', {target:this.target, revision:this.ui.snapshot.revision, changes});
      for (const key of Object.keys(changes)) {
        delete (this.ui.drafts[this.target] || {})[key];
        delete (this.ui.inputs[this.target] || {})[key];
      }
      this.ui.set(result.config); this.ui.queuePreview(); this.dirtyFavorites = false;
      this.notice = withVoice ? '音色和收藏已保存。下次单人语音任务读取此选择。' : '收藏已保存。';
      if (withVoice && this.ui.field(this.key).effective.value !== this.selected) this.notice += ' 当前生效音色由页面所示的更高优先级配置决定。';
    } catch (error) { this.notice = error.message + ' 选择和收藏仍保留，可重试保存。'; }
    finally { this.saving = false; this.ui.busy = false; this.ui.paint(); this.renderResults(); }
  }
  async click(event) {
    const button = event.target.closest('button'); if (!button || button.disabled || this.saving) return;
    if (button.dataset.voiceFavorite) {
      const id = button.dataset.voiceFavorite;
      if (!this.favorites().includes(id) && this.favorites().length >= 2000) { this.notice='最多收藏 2000 个音色。'; this.paintStatus(); return; }
      this.favoriteIds = this.favorites().includes(id) ? this.favorites().filter(value => value !== id) : [...this.favorites(), id];
      this.dirtyFavorites = true; this.notice=''; this.renderResults();
      this.dialog.querySelector(`[data-voice-favorite="${CSS.escape(id)}"]`)?.focus(); return;
    }
    if (button.dataset.voiceUse) { this.selected = button.dataset.voiceUse; this.notice=''; this.renderResults();
      this.dialog.querySelector('[data-voice-action="save-selection"]').focus(); return; }
    if (button.dataset.voiceAction === 'save-selection') return this.saveSelection();
    if (button.dataset.voiceAction === 'save-favorites') return this.saveSelection(false);
    return super.click(event);
  }
}
