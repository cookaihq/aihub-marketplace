// ElevenLabs catalogue shares the full configuration form and its draft lifecycle.
(() => {
  const encode = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const paths = {
    play:'<path d="m8 5 11 7-11 7Z" fill="currentColor" stroke="none"/>',
    pause:'<path d="M8 5v14M16 5v14" stroke-width="4"/>',
    search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
    close:'<path d="m6 6 12 12M6 18 18 6"/>',
    star:'<path d="m12 3 2.8 5.8 6.4.9-4.6 4.5 1.1 6.3-5.7-3-5.7 3 1.1-6.3-4.6-4.5 6.4-.9Z"/>',
    refresh:'<path d="M20 10a8 8 0 0 0-14-5L3 8m0-5v5h5m-4 6a8 8 0 0 0 14 5l3-3m0 5v-5h-5"/>',
    check:'<path d="m5 12 4 4L19 6"/>',
    arrow:'<path d="m14 6-6 6 6 6"/>',
    wave:'<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
    copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>',
  };
  const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || ''}</svg>`;
  // Explicit initial-letter keys implement the requested Chinese name order.
  const languages = [
    ['ar','阿拉伯语','alby'],['de','德语','dy'],['ru','俄语','ey'],['fr','法语','fy'],
    ['ko','韩语','hy'],['pt','葡萄牙语','ptyy'],['ja','日语','ry'],['es','西班牙语','xbyy'],
    ['it','意大利语','ydly'],['hi','印地语','ydy'],['en','英语','yy'],['zh','中文','zw'],
  ].sort((a,b) => a[2].localeCompare(b[2]));
  const languageNames = new Map(languages.map(([id,name]) => [id,name]));
  const VOICE = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', FAVORITES = 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS';

  class ElevenLabsVoiceLibrary {
    constructor(ui) {
      this.ui=ui;this.rows=[];this.byId=new Map();this.index=[];this.scope='global';
      this.tab='all';this.query='';this.language='';this.gender='';this.tag='';this.samples=false;
      this.page=1;this.pageSize=50;this.favoriteSet=new Set();this.filterCache=null;
      this.audio=new Audio();this.audio.preload='none';
      for(const event of ['play','pause','ended'])this.audio.addEventListener(event,()=>this.paintPlayback());
      this.audio.addEventListener('error',()=>this.message('样音暂时无法播放。仍可选择和收藏音色。',true));
      document.addEventListener('click', event=>{
        const button=event.target.closest('[data-voice-open]');
        if(!button?.dataset.voiceOpen.includes('ELEVENLABS')||button.disabled||this.ui.expired)return;
        event.preventDefault();event.stopImmediatePropagation();this.open();
      },true);
      ui.subscribe(()=>this.syncDrafts());
    }
    async open() {
      if(this.dialog?.open||this.ui.expired)return;
      this.syncAccount();
      const scopes=['global','project'].filter(scope=>[VOICE,FAVORITES].every(id=>this.ui.targets(this.ui.field(id)).some(layer=>layer.id===this.ui.snapshot.default_targets[scope])));
      const draftId=[VOICE,FAVORITES].find(id=>this.ui.hasFieldDraft(id));
      const draftScope=draftId&&this.ui.layer(this.ui.switchIntents[draftId]?.target||this.ui.fieldTarget(draftId))?.scope;
      this.scope=scopes.includes(draftScope)?draftScope:scopes.includes(this.scope)?this.scope:scopes[0];
      this.allowedScopes=scopes;
      this.selected=this.ui.draftValue(VOICE) || '';
      this.favoriteSet=new Set(this.ui.draftValue(FAVORITES) || []);
      this.favoritesDirty=this.ui.hasFieldDraft(FAVORITES);
      const dialog=this.dialog=document.createElement('dialog');
      dialog.className='el-library';dialog.id='el-voice-list';dialog.setAttribute('aria-labelledby','el-title');
      dialog.innerHTML=`<header class="el-header"><div><div class="el-breadcrumb">AIhub Studio <span>/</span> 音频 <span>/</span> ElevenLabs </div><h2 id="el-title">发现适合你的声音</h2><p>试听、收藏，把喜欢的音色用于下一次创作。</p></div><button class="el-icon el-close" data-el="close" aria-label="返回配置中心" title="返回配置中心">${icon('close')}</button></header>
        <div class="el-toolbar"><div class="el-tabs" role="tablist" aria-label="音色范围"><button role="tab" data-el-tab="all">${icon('wave')} 全部音色 <span id="el-total">—</span></button><button role="tab" data-el-tab="favorites">${icon('star')} 我的收藏 <span id="el-favorites">0</span></button></div><div class="el-cache"><span id="el-cache-status" role="status"><i></i> 正在读取音色库</span><button data-el="refresh" id="el-refresh">${icon('refresh')}<span>重新下载</span></button></div></div>
        <div class="el-filters"><label class="el-search">${icon('search')}<input id="el-search" type="search" placeholder="搜索音色名称、ID 或声音特点…" aria-label="搜索音色" autocomplete="off"><kbd>/</kbd></label><select id="el-language" aria-label="语种"><option value="">全部语种</option>${languages.map(([id,name])=>`<option value="${encode(id)}">${name}</option>`).join('')}</select><select id="el-gender" aria-label="性别"><option value="">全部性别</option><option>女声</option><option>男声</option></select><select id="el-tag" aria-label="风格场景"><option value="">全部风格</option>${['广告','教育','纪录片','角色','对话','播客','旁白','社交媒体','叙事','有声书'].map(t=>`<option>${t}</option>`).join('')}</select></div>
        <div class="el-list-meta"><p id="el-match-count" aria-live="polite">准备音色库…</p><div><button class="el-clear" data-el="clear" hidden>清除筛选</button><label class="el-samples"><input id="el-samples" type="checkbox">仅看可试听</label></div></div>
        <div id="el-banner" role="status" hidden></div>
        <div class="el-table-head"><span>音色</span><span>语种 / 声音</span><span>适用场景</span><span>选择音色</span></div>
        <div class="el-list" id="el-list" aria-label="音色列表"></div>
        <div class="el-pagination"><span id="el-range"></span><div><button class="el-icon" data-el="previous" aria-label="上一页">${icon('arrow')}</button><span id="el-page">1 / 1</span><button class="el-icon el-next" data-el="next" aria-label="下一页">${icon('arrow')}</button></div><span class="el-page-size">每页 50 个</span></div>
        <footer class="el-footer"><div class="el-save-scope"><span>保存到</span><div role="radiogroup" aria-label="音色保存范围"><button role="radio" data-el-scope="global" aria-checked="true">全局</button><button role="radio" data-el-scope="project" aria-checked="false">本项目</button></div><small id="el-scope-help">多个项目共用</small></div><div class="el-selection" id="el-selection">选择一个音色</div><button class="el-primary" data-el="save" disabled>保存并使用</button></footer>
        <div class="el-bottom-note"><span>目录通常低频更新；搜索与筛选在本机完成，需要时可重新下载</span><span>试听使用已有样音，不生成新语音</span></div>`;
      document.body.append(dialog);
      dialog.addEventListener('click',event=>this.click(event));
      dialog.addEventListener('cancel',event=>{event.preventDefault();this.close();});
      dialog.addEventListener('input',event=>{
        if(event.target.id!=='el-search'||event.isComposing)return;
        this.query=event.target.value;this.page=1;clearTimeout(this.timer);
        this.timer=setTimeout(()=>this.renderRows(),70);
      });
      dialog.addEventListener('compositionend',event=>{
        if(event.target.id==='el-search'){this.query=event.target.value;this.page=1;this.renderRows();}
      });
      dialog.addEventListener('change',event=>{
        const key={'el-language':'language','el-gender':'gender','el-tag':'tag'}[event.target.id];
        if(key)this[key]=event.target.value;
        if(event.target.id==='el-samples')this.samples=event.target.checked;
        if(key||event.target.id==='el-samples'){this.page=1;this.renderRows();}
      });
      dialog.addEventListener('keydown',event=>{
        if(event.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)){event.preventDefault();dialog.querySelector('#el-search').focus();}
        if(['ArrowLeft','ArrowRight'].includes(event.key)&&event.target.closest('[role=radiogroup]')){
          event.preventDefault();this.setScope(event.key==='ArrowLeft'?'global':'project');dialog.querySelector(`[data-el-scope="${this.scope}"]`).focus();
        }
      });
      this.restoreFilters();dialog.showModal();this.paintFooter();this.paintFeedback();
      if(this.rows.length)this.renderRows();
      await this.load(false);
    }
    restoreFilters() {
      for(const key of ['query','language','gender','tag'])this.dialog.querySelector('#el-'+(key==='query'?'search':key)).value=this[key];
      this.dialog.querySelector('#el-samples').checked=this.samples;
    }
    async load(refresh=false) {
      if(this.loading||this.ui.expired||this.ui.busy||this.ui.uncertain)return;
      this.loading=true;const dialog=this.dialog;
      const generation=this.loadGeneration=(this.loadGeneration||0)+1;
      const current=()=>this.dialog===dialog&&this.loadGeneration===generation;
      const first=!this.rows.length;
      this.message('');this.paintCache();
      if(first)this.renderLoading();else this.message('正在重新下载音色库，你可以继续浏览已有缓存。');
      try {
        const result=refresh ? await this.ui.api('/api/elevenlabs-voices/refresh',{}) : await this.ui.api('/api/elevenlabs-voices');
        if(!current())return;
        const genderNames={female:'女声',male:'男声'};
        const tagNames={narration:'旁白',conversational:'对话',social_media:'社交媒体',audiobook:'有声书',advertisement:'广告',education:'教育'};
        const rows=result.voices.map((voice,index)=>({...voice,color:index%8,
          languages:voice.languages||[],gender:genderNames[voice.gender]||voice.gender,
          tag_list:voice.tag_list.map(tag=>tagNames[tag]||tag)}));
        const byId=new Map(),index=[];
        for(let start=0;start<rows.length;start+=750){
          for(const voice of rows.slice(start,start+750)){
            const translated=voice.languages.map(id=>languageNames.get(id)||id);
            byId.set(voice.voice_id,voice);
            index.push({voice,text:[voice.voice_id,voice.voice_name,voice.description,voice.gender,voice.age,...translated,...voice.languages,...voice.tag_list].join(' ').toLowerCase()});
          }
          await new Promise(resolve=>setTimeout(resolve,0));
          if(!current())return;
        }
        const tags=[...new Set(rows.flatMap(voice=>voice.tag_list))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
        this.dialog.querySelector('#el-tag').innerHTML='<option value="">全部风格</option>'+tags.map(tag=>`<option>${encode(tag)}</option>`).join('');
        this.restoreFilters();this.savedAt=result.saved_at;this.rows=rows;this.loaded=true;
        this.byId=byId;this.index=index;this.filterCache=null;this.message(refresh?'音色库已更新，本机缓存已保存。':'');
      }catch(error){
        if(!current())return;
        this.message(error.message,true);
        if(!this.rows.length){
          this.dialog.querySelector('#el-list').innerHTML=`<div class="el-empty"><span class="el-empty-icon">${icon('info')}</span><h3>音色库暂时没有加载成功</h3><p>请检查网络后重试，已保存的音色与收藏会保留。</p><button data-el="refresh">重新下载</button></div>`;
        }
      }finally{
        if(current()){this.loading=false;this.paintCache();if(this.loaded)this.renderRows();this.paintFooter();}
      }
    }
    paintCache() {
      if(!this.dialog)return;
      const status=this.dialog.querySelector('#el-cache-status');
      status.innerHTML=`<i class="${this.loading?'el-pulse':''}"></i>${this.loading?(this.rows.length?'正在更新本机缓存':'首次载入音色库'):this.savedAt?'已缓存到本机':'尚无本机缓存'}`;
      status.title=this.savedAt?'缓存更新于 '+new Date(this.savedAt).toLocaleString('zh-CN'):'';
      const button=this.dialog.querySelector('#el-refresh');button.disabled=this.loading||this.ui.expired||this.ui.busy||this.ui.uncertain;
      button.classList.toggle('el-downloading',this.loading);button.querySelector('span').textContent=this.loading?'正在下载':'重新下载';
    }
    renderLoading() {
      this.dialog.querySelector('#el-list').setAttribute('aria-busy','true');
      this.dialog.querySelector('#el-list').innerHTML=`<div class="el-loading" role="status"><span class="el-spinner"></span><h3>正在下载音色库</h3><p>首次加载需要一点时间。完成后会缓存在本机，下次直接读取。</p><div class="el-progress"><span></span></div><small>正在准备音色列表…</small></div>`;
      this.dialog.querySelector('#el-match-count').textContent='正在准备全部音色';
      this.dialog.querySelector('#el-range').textContent='';
      for(const action of ['previous','next'])this.dialog.querySelector(`[data-el="${action}"]`).disabled=true;
    }
    filtered() {
      const key=JSON.stringify([this.tab,this.query,this.language,this.gender,this.tag,this.samples,this.tab==='favorites'?[...this.favoriteSet]:null]);
      if(this.filterCache?.key===key)return this.filterCache.value;
      const start=performance.now(),tokens=this.query.toLowerCase().trim().split(/\s+/).filter(Boolean);
      const value=[];
      for(const {voice,text} of this.index){
        if(this.tab==='favorites'&&!this.favoriteSet.has(voice.voice_id)||this.language&&!voice.languages.includes(this.language)||this.gender&&voice.gender!==this.gender||this.tag&&!voice.tag_list.includes(this.tag)||this.samples&&!voice.sample_audio)continue;
        if(tokens.every(token=>text.includes(token)))value.push(voice);
      }
      this.lastFilterMs=performance.now()-start;this.filterCache={key,value};return value;
    }
    renderRows() {
      if(!this.dialog||!this.loaded)return;
      const start=performance.now(),matches=this.filtered();
      this.totalPages=Math.max(1,Math.ceil(matches.length/this.pageSize));this.page=Math.min(this.page,this.totalPages);
      const from=(this.page-1)*this.pageSize,visible=matches.slice(from,from+this.pageSize),list=this.dialog.querySelector('#el-list');
      list.setAttribute('aria-busy','false');
      list.innerHTML=visible.map(voice=>`<article class="el-row ${this.selected===voice.voice_id?'el-selected':''}" data-el-id="${encode(voice.voice_id)}"><div class="el-voice"><button class="el-orb el-color-${voice.color}" data-el-play="${encode(voice.voice_id)}" aria-label="试听 ${encode(voice.voice_name)}" title="试听已有样音" ${voice.sample_audio?'':'disabled'}>${icon('play')}</button><div class="el-voice-text"><button class="el-name" data-el-detail="${encode(voice.voice_id)}" title="查看 ${encode(voice.voice_name)} 的详情">${encode(voice.voice_name)}${this.selected===voice.voice_id?'<span class="el-selected-label">已选择</span>':''}</button><p title="${encode(voice.description)}">${encode(voice.description)}</p></div></div><div class="el-voice-language"><span>${voice.languages.map(id=>encode(languageNames.get(id)||id)).join('、')}</span><small>${encode(voice.gender)} · ${encode(voice.age)}</small></div><div class="el-tags">${voice.tag_list.map(tag=>`<button data-el-tag="${encode(tag)}">${encode(tag)}</button>`).join('')}</div><div class="el-row-actions"><button class="el-icon el-star ${this.favoriteSet.has(voice.voice_id)?'is-favorite':''}" data-el-favorite="${encode(voice.voice_id)}" aria-label="${this.favoriteSet.has(voice.voice_id)?'取消收藏':'收藏'} ${encode(voice.voice_name)}" aria-pressed="${this.favoriteSet.has(voice.voice_id)}">${icon('star')}</button><button class="el-use" data-el-select="${encode(voice.voice_id)}">${this.selected===voice.voice_id?icon('check')+'已选择':'使用此音色'}</button></div></article>`).join('')||`<div class="el-empty"><span class="el-empty-icon">${icon(this.tab==='favorites'?'star':'search')}</span><h3>${this.tab==='favorites'?'这里还没有收藏的音色':'没有匹配的音色'}</h3><p>${this.tab==='favorites'?'在全部音色中点击星标，把喜欢的声音留在这里。':'换一个关键词，或清除筛选后再试试。'}</p><button data-el="${this.tab==='favorites'?'all':'clear'}">${this.tab==='favorites'?'浏览全部音色':'清除筛选'}</button></div>`;
      this.dialog.querySelector('#el-match-count').innerHTML=`<strong>${matches.length.toLocaleString('zh-CN')}</strong> 个${this.tab==='favorites'?'收藏':'匹配'}音色`;
      this.dialog.querySelector('#el-range').textContent=matches.length?`显示 ${from+1}–${Math.min(from+this.pageSize,matches.length)}`:'暂无音色';
      this.dialog.querySelector('#el-page').textContent=`${this.page} / ${this.totalPages}`;
      this.dialog.querySelector('#el-total').textContent=this.rows.length.toLocaleString('zh-CN');
      this.dialog.querySelector('#el-favorites').textContent=this.favoriteSet.size;
      for(const button of this.dialog.querySelectorAll('[data-el-tab]'))button.setAttribute('aria-selected',String(button.dataset.elTab===this.tab));
      this.dialog.querySelector('[data-el="previous"]').disabled=this.page===1;
      this.dialog.querySelector('[data-el="next"]').disabled=this.page===this.totalPages;
      this.dialog.querySelector('[data-el="clear"]').hidden=!(this.query||this.language||this.gender||this.tag||this.samples);
      this.paintFooter();this.paintPlayback();this.lastRenderMs=performance.now()-start;
      if(!this.rows.length){
        list.innerHTML=`<div class="el-empty"><span class="el-empty-icon">${icon('info')}</span><h3>目录当前没有音色</h3><p>目录已载入。可稍后重新下载，已保存的音色和收藏保留。</p><button data-el="refresh">重新下载</button></div>`;
      }
    }
    paintFooter() {
      if(!this.dialog)return;
      const locked=this.saving||this.ui.busy||this.ui.expired||this.ui.uncertain;
      for(const button of this.dialog.querySelectorAll('[data-el-scope]')){
        button.hidden=!this.allowedScopes.includes(button.dataset.elScope);button.setAttribute('aria-checked',String(button.dataset.elScope===this.scope));button.disabled=!!locked;
        button.tabIndex=button.dataset.elScope===this.scope?0:-1;
      }
      const exactDraft=this.fieldsToSave().some(id=>this.ui.hasFieldDraft(id)&&this.targetFor(id)!==this.ui.snapshot.default_targets[this.scope]);
      this.dialog.querySelector('#el-scope-help').textContent=exactDraft?'沿用主表各项保存位置':this.scope==='global'?'多个项目共用':'仅当前项目';
      const voice=this.byId.get(this.selected);
      this.dialog.querySelector('#el-selection').innerHTML=voice?`<span class="el-selection-dot el-color-${voice.color}"></span><div><small>已选择</small><strong>${encode(voice.voice_name)}</strong></div>`:'选择一个音色';
      const save=this.dialog.querySelector('[data-el="save"]');save.disabled=this.saving||!this.selected&&!this.favoritesDirty;
      const transfer=this.prepareTransfer();
      const pendingSwitch=this.fieldsToSave().some(id=>this.ui.switchIntents[id]&&this.ui.preview?.scope_plans?.[id]?.state!=='ready');
      save.disabled=locked||pendingSwitch||transfer&&(transfer.loading||transfer.error||transfer.plan?.state!=='ready')||this.fieldsToSave().some(id=>this.ui.needsReview?.[id])||!this.selected&&!this.favoritesDirty;
      save.textContent=this.saving?'正在保存…':this.fieldsToSave().length===1&&this.fieldsToSave()[0]===FAVORITES?'保存收藏':'保存并使用';
      for(const button of this.dialog.querySelectorAll('[data-el-select],[data-el-favorite]'))button.disabled=!!locked;
      this.dialog.querySelector('#el-refresh').disabled=!!locked||this.loading;
      if(this.ui.expired)this.audio.pause();
    }
    paintPlayback() {
      if(!this.dialog)return;
      for(const button of this.dialog.querySelectorAll('[data-el-play]')){
        const active=button.dataset.elPlay===this.playing&&!this.audio.paused;
        button.innerHTML=icon(active?'pause':'play');button.classList.toggle('is-playing',active);
        const name=this.byId.get(button.dataset.elPlay)?.voice_name||'';
        button.setAttribute('aria-label',(active?'暂停 ':'试听 ')+name);
      }
    }
    message(text,error=false) {
      this.notice=text;this.noticeError=error;this.paintFeedback();
    }
    targetFor(id) {
      return this.ui.switchIntents[id]?.target||(this.ui.hasFieldDraft(id)?this.ui.fieldTarget(id):this.ui.snapshot.default_targets[this.scope]);
    }
    prepareTransfer() {
      // Opening a picker is read-only. Preview an unedited transfer without
      // creating a main-form switch, so its exact cleanup is visible before saving.
      if(this.saving)return this.prospectiveTransfer;
      if(!this.selected||!this.fieldsToSave().includes(VOICE)||this.ui.hasFieldDraft(VOICE)||this.ui.field(VOICE).effective.source===this.targetFor(VOICE)){
        this.prospectiveTransfer=null;return null;
      }
      const intent={target:this.targetFor(VOICE),mode:'input'},revision=this.ui.snapshot.revision;
      const signature=JSON.stringify([revision,intent]);
      if(this.prospectiveTransfer?.signature===signature)return this.prospectiveTransfer;
      const proposal=this.prospectiveTransfer={signature,intent,loading:true},dialog=this.dialog;
      this.ui.api('/api/preview',{revision,changes:{files:{},switches:{[VOICE]:intent}}}).then(result=>{
        if(this.dialog!==dialog||this.prospectiveTransfer!==proposal)return;
        proposal.plan=result.config.scope_plans[VOICE];
        if(result.config.validation_errors?.length)proposal.error=result.config.validation_errors.join(' ');
      }).catch(error=>{if(this.prospectiveTransfer===proposal)proposal.error=error.message;}).finally(()=>{
        if(this.dialog===dialog&&this.prospectiveTransfer===proposal){proposal.loading=false;this.paintFooter();this.paintFeedback();}
      });
      return proposal;
    }
    fieldsToSave() {
      const ids=[VOICE,FAVORITES].filter(id=>this.ui.hasFieldDraft(id));
      if(this.transferVoice&&!ids.includes(VOICE))ids.push(VOICE);
      if(!ids.length&&this.selected)ids.push(VOICE);
      return ids;
    }
    setScope(scope) {
      if(this.ui.expired||this.ui.uncertain||this.ui.busy||this.saving||!this.allowedScopes.includes(scope))return;
      this.scope=scope;
      for(const id of [VOICE,FAVORITES])if(this.ui.hasFieldDraft(id))this.ui.requestSwitch(id,this.ui.snapshot.default_targets[scope],'input');
      this.paintFooter();this.paintFeedback();
    }
    syncDrafts() {
      this.syncAccount();
      const revision=this.ui.snapshot?.revision;
      if(this.revision!==revision&&!this.ui.hasFieldDraft(VOICE))this.transferVoice=false;
      this.revision=revision;
      const selected=this.ui.draftValue(VOICE)||'',favorites=this.ui.draftValue(FAVORITES)||[];
      const changed=selected!==this.selected||JSON.stringify(favorites)!==JSON.stringify([...this.favoriteSet]);
      this.selected=selected;this.favoriteSet=new Set(favorites);this.favoritesDirty=this.ui.hasFieldDraft(FAVORITES);
      if(!this.dialog)return;
      if(changed)this.renderRows();else this.paintFooter();
      this.paintFeedback();
    }
    syncAccount() {
      const revision=this.ui.snapshot?.fields.find(field=>field.id==='AIHUB_API_KEY')?.edit_revision;
      if(!revision||this.accountRevision===revision)return;
      this.accountRevision=revision;this.loadGeneration=(this.loadGeneration||0)+1;
      this.rows=[];this.byId=new Map();this.index=[];this.filterCache=null;
      this.loaded=false;this.loading=false;this.savedAt=null;this.page=1;
      this.audio.pause();this.audio.removeAttribute('src');this.playing=null;
      if(!this.dialog)return;
      this.dialog.querySelector('.el-details')?.remove();
      this.dialog.querySelector('#el-total').textContent='—';
      this.dialog.querySelector('#el-match-count').textContent='等待载入当前账号音色';
      this.dialog.querySelector('#el-range').textContent='';
      this.dialog.querySelector('#el-page').textContent='1 / 1';
      for(const action of ['previous','next'])this.dialog.querySelector(`[data-el="${action}"]`).disabled=true;
      this.dialog.querySelector('#el-list').innerHTML='<div class="el-empty"><h3>音色库账号已改变</h3><p>重新下载当前账号的目录，已保存的音色和收藏会保留。</p><button data-el="refresh">重新下载</button></div>';
      this.message('');this.paintCache();
    }
    paintFeedback() {
      if(!this.dialog)return;
      const banner=this.dialog.querySelector('#el-banner'),ui=this.ui;
      const errors=[ui.expired||ui.uncertain?ui.error:'',...this.fieldsToSave().flatMap(id=>ui.singleErrors?.[id]||[])].filter(Boolean);
      let html=errors.map(text=>`<p class="el-feedback-error">${encode(text)}</p>`).join('');
      if(ui.uncertain)html+='<button data-config="reload">重新载入并核对</button>';
      for(const id of [VOICE,FAVORITES]){
        if(ui.needsReview?.[id])html+=`<p class="el-feedback-error">${encode(ui.field(id).label)}已在文件中发生变化。已保存：${encode(JSON.stringify(ui.field(id).effective.value))}；草稿：${encode(JSON.stringify(ui.draftValue(id)))}。</p><button data-config="review-draft" data-id="${encode(id)}">已核对，保留这份草稿</button>`;
        const proposal=id===VOICE&&this.prospectiveTransfer;
        const prospective=proposal&&(!ui.switchIntents[id]||this.saving&&!ui.preview);
        if(prospective&&proposal.error)html+=`<p class="el-feedback-error">${encode(proposal.error)}</p>`;
        const template=document.createElement('template');template.innerHTML=prospective?ui.selectionHTML(id,proposal.intent,proposal.plan):ui.selectionHTML(id);
        if(prospective)template.content.querySelectorAll('[data-config]').forEach(button=>button.remove());
        template.content.querySelector('.switch-commit')?.remove();
        html+=template.innerHTML;
      }
      if(this.notice)html+=`<p class="${this.noticeError?'el-feedback-error':''}">${encode(this.notice)}</p>`;
      banner.hidden=!html;banner.className='el-banner';
      if(banner.innerHTML!==html)banner.innerHTML=html;
      if(ui.expired)banner.querySelectorAll('button').forEach(button=>button.disabled=true);
    }
    async save() {
      if(this.saving||this.ui.expired||this.ui.uncertain)return;
      const ids=this.fieldsToSave();
      const targets=Object.fromEntries(ids.map(id=>[id,this.targetFor(id)]));
      if(!ids.length||!ids.every(key=>this.ui.targets(this.ui.field(key)).some(layer=>layer.id===targets[key]))){this.message('所选范围当前无法保存，请选择另一个位置。',true);return;}
      this.saving=true;this.paintFooter();
      for(const id of ids)this.ui.requestSwitch(id,targets[id],this.ui.switchIntents[id]?.mode||'input');
      try{
        const result=await this.ui.save(ids);
        if(result?.saved){this.transferVoice=false;this.syncDrafts();const scopes=[...new Set(Object.values(targets).map(target=>this.ui.layer(target).scope==='global'?'全局':'本项目'))];this.message(`已保存到${scopes.join('、')}配置，已核对实际来源。`);}
        else this.message(this.ui.error||'请核对上方内容选择，再点击保存。',!!this.ui.error);
      }catch(error){this.message(error.message+' 选择和收藏保留，可重新核对后保存。',true);}
      finally{this.saving=false;this.paintFooter();this.paintFeedback();}
    }
    async details(id) {
      const voice=this.byId.get(id);if(!voice)return;
      const old=this.dialog.querySelector('.el-details');if(old)old.remove();
      const details=document.createElement('section');details.className='el-details';details.setAttribute('aria-label','音色详情');
      details.innerHTML=`<button class="el-icon" data-el="close-details" aria-label="关闭音色详情">${icon('close')}</button><strong>${encode(voice.voice_name)}</strong><p>${encode(voice.description)}</p><div><code>${encode(id)}</code><button data-el-copy="${encode(id)}">${icon('copy')}复制 ID</button></div>`;
      this.dialog.querySelector('.el-footer').before(details);details.querySelector('button').focus();
    }
    async click(event) {
      const button=event.target.closest('button');if(!button||button.disabled)return;
      const data=button.dataset,action=data.el;
      if(data.config){await this.ui.onClick(event);this.syncDrafts();return;}
      if(action==='close')return this.close();
      if(action==='refresh')return this.load(true);
      if(action==='save')return this.save();
      if(action==='close-details'){button.closest('.el-details').remove();return;}
      if(data.elCopy){try{await navigator.clipboard.writeText(data.elCopy);button.textContent='已复制';}catch{this.message('请从详情中选中并复制音色 ID。');}return;}
      if(data.elDetail)return this.details(data.elDetail);
      if(data.elScope){this.setScope(data.elScope);return;}
      if(data.elPlay){
        if(this.playing===data.elPlay&&!this.audio.paused){this.audio.pause();return;}
        this.playing=data.elPlay;this.audio.src=this.byId.get(data.elPlay)?.sample_audio||'';this.audio.currentTime=0;
        try{await this.audio.play();}catch{this.message('请再次点击试听以播放样音。',true);}return;
      }
      if(data.elFavorite){
        const target=this.targetFor(FAVORITES);
        const id=data.elFavorite;this.favoriteSet.has(id)?this.favoriteSet.delete(id):this.favoriteSet.add(id);
        this.ui.fileEdits?.[this.ui.fieldTarget(FAVORITES)]?.delete(FAVORITES);
        this.ui.stage(FAVORITES,{op:'set',value:[...this.favoriteSet]});
        this.ui.requestSwitch(FAVORITES,target,'input');
        this.favoritesDirty=this.ui.hasFieldDraft(FAVORITES);this.renderRows();this.dialog.querySelector(`[data-el-favorite="${CSS.escape(id)}"]`)?.focus();return;
      }
      if(data.elSelect){const target=this.targetFor(VOICE);this.selected=data.elSelect;this.transferVoice=true;this.ui.fileEdits?.[this.ui.fieldTarget(VOICE)]?.delete(VOICE);this.ui.stage(VOICE,{op:'set',value:this.selected});this.ui.requestSwitch(VOICE,target,'input');this.message('');this.renderRows();this.dialog.querySelector('[data-el="save"]').focus();return;}
      if(data.elTag){this.tag=data.elTag;this.page=1;this.restoreFilters();this.renderRows();return;}
      if(data.elTab||action==='all'){this.tab=data.elTab||'all';this.page=1;this.renderRows();return;}
      if(action==='clear'){
        this.query='';this.language='';this.gender='';this.tag='';this.samples=false;this.page=1;
        clearTimeout(this.timer);this.restoreFilters();this.renderRows();return;
      }
      if(action==='previous'||action==='next'){
        this.page+=action==='next'?1:-1;this.renderRows();this.dialog.querySelector('#el-list').scrollTop=0;
      }
    }
    close() {
      if(this.saving)return;
      this.audio.pause();clearTimeout(this.timer);this.dialog.close();this.dialog.remove();this.dialog=null;this.loading=false;this.prospectiveTransfer=null;
      this.ui.root.querySelector('[data-voice-open="'+VOICE+'"]')?.focus();
    }
  }
  const library=new ElevenLabsVoiceLibrary(configurationUI);
  let directOpened=false;
  const direct=()=>{if(!directOpened&&configurationUI.snapshot&&!ended&&new URL(location.href).searchParams.get('voice-library')==='elevenlabs'){directOpened=true;library.open();}};
  configurationUI.subscribe(direct);direct();
  window.addEventListener('pagehide',()=>{library.audio.pause();});
})();
