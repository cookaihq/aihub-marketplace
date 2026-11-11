// MiniMax voice selection shares the configuration center draft and save protocol.
class SpeechVoiceLibrary {
  constructor(ui) {
    this.ui = ui;
    this.key = 'AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID';
    this.favoritesKey = 'audio.minimax_speech.favorite_voice_ids';
    this.voices = [];
    this.query = ''; this.language = ''; this.gender = ''; this.tag = ''; this.samplesOnly = false;
    this.tab = 'all'; this.page = 1; this.pageSize = 12;
  }
  escape(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  favoriteTarget() { return this.ui.field(this.favoritesKey).targets?.[0] || ''; }
  favorites() {
    const change = this.ui.drafts[this.favoriteTarget()]?.[this.favoritesKey];
    return change?.op === 'set' ? change.value : change?.op === 'unset' ? [] : this.ui.field(this.favoritesKey).effective.value || [];
  }
  async open(mode) {
    if (this.dialog) return;
    this.mode = mode; this.tab = mode === 'favorites' ? 'favorites' : 'all'; this.page = 1;
    const field = this.ui.field(this.key), draft = this.ui.changes()[this.key];
    this.selected = draft?.op === 'set' ? draft.value : draft?.op === 'unset' ? '' : field.effective.value || '';
    this.playing = ''; this.notice = ''; this.loading = true;
    this.dialog = document.createElement('dialog');
    this.dialog.id = 'voice-library-dialog'; this.dialog.className = 'speech-library';
    this.dialog.setAttribute('aria-labelledby', 'voice-library-title');
    this.dialog.innerHTML = `<header class="speech-header"><div><small>AIhub Studio / 音频 / MiniMax Speech</small><h2 id="voice-library-title">音色库 </h2></div><button data-voice-action="close" aria-label="关闭音色库">✕</button></header>
      <div class="speech-tools"><div class="speech-tabs"><div role="tablist" aria-label="音色范围"><button role="tab" data-voice-tab="all">全部音色</button><button role="tab" data-voice-tab="favorites">我的收藏</button></div><div class="speech-library-actions"><span id="speech-favorite-count"></span><button data-voice-action="save-favorites" hidden>保存收藏</button></div></div>
      <div class="speech-search"><label class="speech-search-box"><span aria-hidden="true">⌕</span><input id="speech-search" type="search" placeholder="搜索名称、ID、语言或风格" aria-label="搜索名称、ID、语言或风格"></label><label class="speech-sample-filter"><input id="speech-samples" type="checkbox">仅看可试听</label></div>
      <div class="speech-filters"><select id="speech-language" aria-label="语种"><option value="">全部语种</option></select><select id="speech-gender" aria-label="性别"><option value="">全部性别</option></select><select id="speech-tag" aria-label="风格或场景"><option value="">全部风格 / 场景</option></select><button data-voice-action="reset">清除筛选</button></div></div>
      <div class="speech-result-meta" id="speech-result-meta" aria-live="polite"></div><p id="speech-notice" role="status"></p><button class="speech-retry" data-voice-action="retry" hidden>重新载入音色</button><div class="speech-results" id="speech-results"></div>
      <div class="speech-pagination"><button data-voice-action="previous">上一页</button><span id="speech-page"></span><button data-voice-action="next">下一页</button></div>
      <audio id="speech-audio" preload="none" hidden></audio>`;
    document.body.append(this.dialog);
    this.audio = this.dialog.querySelector('audio');
    this.dialog.addEventListener('click', event => this.click(event));
    this.keyHandler = event => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.close(); }
      if (event.key === 'Tab') {
        const controls = [...this.dialog.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),audio[controls]')].filter(node => node.getClientRects().length);
        const first = controls[0], last = controls.at(-1);
        if (!this.dialog.contains(document.activeElement)) { event.preventDefault(); event.stopPropagation(); first?.focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); event.stopPropagation(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); event.stopPropagation(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', this.keyHandler, true);
    this.dialog.addEventListener('cancel', event => { event.preventDefault(); this.close(); });
    this.dialog.querySelector('#speech-search').value = this.query;
    this.dialog.querySelector('#speech-samples').checked = this.samplesOnly;
    this.dialog.addEventListener('input', event => {
      if (event.target.id === 'speech-search') { this.query = event.target.value; this.page = 1; this.renderResults(); }
    });
    this.dialog.addEventListener('change', event => {
      const field = {'speech-language':'language','speech-gender':'gender','speech-tag':'tag'}[event.target.id];
      if (field) this[field] = event.target.value;
      if (event.target.id === 'speech-samples') this.samplesOnly = event.target.checked;
      if (field || event.target.id === 'speech-samples') { this.page = 1; this.renderResults(); }
    });
    for (const type of ['play', 'pause', 'ended']) this.audio.addEventListener(type, () => this.paintPlayer());
    this.audio.addEventListener('error', () => { this.notice = '样音暂时无法播放，可以继续收藏或选择音色。'; this.paintStatus(); });
    this.dialog.showModal(); this.renderResults(); this.dialog.querySelector('#speech-search').focus();
    await this.load();
  }
  async load() {
    const dialog = this.dialog;
    const request = this.request = (this.request || 0) + 1;
    this.loading = true; this.failed = false; this.notice = ''; this.renderResults();
    try {
      const result = await this.ui.api('/api/minimax-voices');
      if (this.dialog === dialog && this.request === request) this.voices = result.voices;
    } catch (error) {
      if (this.dialog === dialog && this.request === request) { this.failed = true; this.notice = error.message; }
    } finally {
      if (this.dialog === dialog && this.request === request) {
        this.loading = false; this.fillFilters(); this.renderResults();
      }
    }
  }

  fillFilters() {
    const groups = [['language','语种'], ['gender','性别'], ['tag','风格 / 场景']];
    for (const [key, title] of groups) {
      const values = [...new Set(this.voices.flatMap(v => key === 'tag' ? v.tag_list : v[key]).filter(Boolean))];
      const select = this.dialog.querySelector('#speech-' + key);
      select.innerHTML = '<option value="">全部' + title + '</option>' + values.map(value => `<option value="${this.escape(value)}">${this.escape(value)}</option>`).join('');
      select.value = this[key];
    }
  }
  filtered() {
    const favorites = this.favorites();
    const missing = this.tab === 'favorites' ? favorites.filter(id => !this.voices.some(v => v.voice_id === id)).map(id => ({voice_id:id,voice_name:id,language:'',gender:'',tag_list:[],description:'当前清单未收录，保留收藏记录。',unlisted:true,sample_audio:''})) : [];
    const tokens = this.query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return [...this.voices, ...missing].filter(v => {
      const text = [v.voice_id,v.voice_name,v.language,v.accent,v.gender,v.age,v.description,...v.tag_list].join(' ').toLowerCase();
      return (this.tab !== 'favorites' || favorites.includes(v.voice_id)) && (!this.language || v.language === this.language) && (!this.gender || v.gender === this.gender) && (!this.tag || v.tag_list.includes(this.tag)) && (!this.samplesOnly || v.sample_audio) && tokens.every(t => text.includes(t));
    });
  }
  renderResults() {
    if (!this.dialog) return;
    const escape = value => this.escape(value), favorites = this.favorites(), filtered = this.filtered();
    const totalPages = Math.max(1, Math.ceil(filtered.length / this.pageSize)); this.page = Math.min(this.page, totalPages);
    const visible = filtered.slice((this.page - 1) * this.pageSize, this.page * this.pageSize);
    if (this.playing && !visible.some(v => v.voice_id === this.playing)) this.audio.pause();
    for (const tab of this.dialog.querySelectorAll('[data-voice-tab]')) {
      const active = tab.dataset.voiceTab === this.tab; tab.classList.toggle('active', active); tab.setAttribute('aria-selected', String(active));
      tab.textContent = tab.dataset.voiceTab === 'favorites' ? `我的收藏 (${favorites.length})` : `全部音色 (${this.voices.length})`;
    }
    this.dialog.querySelector('#speech-result-meta').textContent = this.loading ? '正在读取音色…' : `${filtered.length} 个匹配音色 · 每页 ${this.pageSize} 个`;
    this.dialog.querySelector('#speech-results').innerHTML = visible.map(v => `<article class="speech-card ${v.voice_id === this.selected ? 'selected' : ''}" data-voice-id="${escape(v.voice_id)}">
      <div class="speech-card-top"><button class="speech-play" data-voice-play="${escape(v.voice_id)}" ${v.sample_audio ? '' : 'disabled'} aria-label="试听 ${escape(v.voice_name)}">▶</button><div class="speech-card-name"><strong>${escape(v.voice_name)}</strong><small>${escape([v.language,v.gender,v.age].filter(Boolean).join(' · '))}</small></div><button class="speech-star ${favorites.includes(v.voice_id)?'saved':''}" data-voice-favorite="${escape(v.voice_id)}" ${!this.favoriteTarget() || this.saving ? 'disabled' : ''} aria-pressed="${favorites.includes(v.voice_id)}" aria-label="${favorites.includes(v.voice_id)?'取消收藏':'收藏'} ${escape(v.voice_name)}">${favorites.includes(v.voice_id)?'★':'☆'}</button></div>
      <div class="speech-tags">${v.tag_list.slice(0,3).map(t => `<span>${escape(t)}</span>`).join('') || '<span>暂无风格标签</span>'}</div><p>${escape(v.description || '暂无音色描述，可先试听。')}</p>
      <code>${escape(v.voice_id)}</code><div class="speech-card-bottom"><small>${v.unlisted?'未收录':''}${v.sample_audio?'可试听':'暂无样音'}${v.voice_id===this.selected?' · 当前选择':''}</small>${this.mode==='choose'?`<button data-voice-use="${escape(v.voice_id)}">使用此音色</button>`:''}</div></article>`).join('') || `<div class="speech-empty"><strong>${this.loading?'正在载入…':'没有匹配音色'}</strong><p>${this.tab==='favorites'?'可以在全部音色中点击星标收藏，再回到这里比较。':'试试清除筛选；自定义或克隆音色也可在配置中手填 ID。'}</p><button data-voice-action="reset">清除筛选</button></div>`;
    this.dialog.querySelector('#speech-page').textContent = `${this.page} / ${totalPages}`;
    this.dialog.querySelector('[data-voice-action="previous"]').disabled = this.page === 1;
    this.dialog.querySelector('[data-voice-action="next"]').disabled = this.page === totalPages;
    this.paintStatus(); this.paintPlayer();
  }
  paintStatus() {
    if (!this.dialog) return;
    const dirty = !!this.ui.drafts[this.favoriteTarget()]?.[this.favoritesKey], count = this.favorites().length;
    this.dialog.querySelector('#speech-favorite-count').textContent = `已收藏 ${count} 个${dirty?' · 未保存':''}`;
    const save = this.dialog.querySelector('[data-voice-action="save-favorites"]');
    save.hidden = !dirty || !this.favoriteTarget(); save.disabled = this.saving;
    this.dialog.querySelector('[data-voice-action="retry"]').hidden = !this.failed;
    this.dialog.querySelector('#speech-notice').textContent = this.notice;
  }
  paintPlayer() {
    if (!this.dialog) return;
    const active = this.playing && !this.audio.paused;
    for (const button of this.dialog.querySelectorAll('[data-voice-play]')) {
      const playing = active && button.dataset.voicePlay === this.playing;
      button.textContent = playing ? 'Ⅱ' : '▶'; button.classList.toggle('playing', !!playing);
      const name = this.voices.find(v => v.voice_id === button.dataset.voicePlay)?.voice_name || '';
      button.setAttribute('aria-label', `${playing?'暂停':'试听'} ${name}`);
    }
  }
  async play(id) {
    const voice = this.voices.find(v => v.voice_id === id); if (!voice?.sample_audio) return;
    if (id === this.playing && !this.audio.paused) { this.audio.pause(); return; }
    if (id !== this.playing) { this.audio.pause(); this.audio.src = voice.sample_audio; this.playing = id; }
    try { await this.audio.play(); this.notice = ''; } catch { this.notice = '样音暂时无法播放，请重试。收藏和默认音色选择仍可用。'; }
    this.paintPlayer(); this.paintStatus();
  }
  async saveFavorites() {
    if (this.saving) return;
    const change = this.ui.drafts[this.favoriteTarget()]?.[this.favoritesKey]; if (!change) return;
    this.saving = true; this.ui.busy = true; this.paintStatus();
    try {
      const result = await this.ui.api('/api/save', {target:this.favoriteTarget(), revision:this.ui.snapshot.revision, changes:{[this.favoritesKey]:change}});
      delete this.ui.drafts[this.favoriteTarget()][this.favoritesKey];
      delete (this.ui.inputs[this.favoriteTarget()] || {})[this.favoritesKey];
      this.ui.set(result.config); this.ui.queuePreview();
      this.notice = '收藏已保存。';
    } catch (error) { this.notice = error.message + ' 收藏草稿仍保留。'; }
    finally { this.saving = false; this.ui.busy = false; this.ui.paint(); this.renderResults(); this.dialog?.querySelector('#speech-search').focus(); }
  }
  async click(event) {
    const button = event.target.closest('button'); if (!button || button.disabled || this.saving) return;
    if (button.dataset.voiceTab) { this.tab = button.dataset.voiceTab; this.page = 1; this.renderResults(); return; }
    if (button.dataset.voiceFavorite) {
      if (!this.favoriteTarget()) return;
      const id = button.dataset.voiceFavorite, values = this.favorites();
      if (!values.includes(id) && values.length >= 2000) { this.notice = '最多收藏 2000 个音色。'; this.paintStatus(); return; }
      (this.ui.drafts[this.favoriteTarget()] ??= {})[this.favoritesKey] = {op:'set', value:values.includes(id)?values.filter(v => v!==id):[...values,id]};
      delete (this.ui.inputs[this.favoriteTarget()] || {})[this.favoritesKey];
      delete (this.ui.errors[this.favoriteTarget()] || {})[this.favoritesKey];
      this.notice = '';
      this.renderResults(); this.dialog.querySelector(`[data-voice-favorite="${CSS.escape(id)}"]`)?.focus(); return;
    }
    if (button.dataset.voicePlay) { await this.play(button.dataset.voicePlay); return; }
    if (button.dataset.voiceUse && !this.saving) {
      this.selected = button.dataset.voiceUse;
      this.ui.stage({op:'set',value:this.selected}, this.selected); this.close(); return;
    }
    const action = button.dataset.voiceAction;
    if (action === 'close') this.close();
    if (action === 'retry' && !this.loading) await this.load();
    if (action === 'save-favorites') await this.saveFavorites();
    if (action === 'reset') {
      this.query=''; this.language=''; this.gender=''; this.tag=''; this.samplesOnly=false; this.page=1;
      this.dialog.querySelector('#speech-search').value=''; this.dialog.querySelector('#speech-samples').checked=false;
      this.fillFilters(); this.renderResults();
    }
    if (action === 'previous' || action === 'next') { this.page += action === 'next' ? 1 : -1; this.renderResults(); this.dialog.querySelector('#speech-results').scrollTop=0; }
  }
  close() {
    if (!this.dialog || this.saving) return;
    this.audio.pause(); this.audio.removeAttribute('src'); this.audio.load();
    document.removeEventListener('keydown', this.keyHandler, true);
    this.dialog.close(); this.dialog.remove(); this.dialog=null;
    this.ui.render(); this.ui.queuePreview(); this.ui.root.querySelector('[data-open-voice-library]')?.focus();
  }
}
