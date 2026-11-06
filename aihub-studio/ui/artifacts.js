// Marketplace navigation and presentation; shared runtime remains unmodified.
if (state?.page === 'artifacts') {
  const statuses = {completed:'已完成', partial:'部分完成', running:'进行中', failed:'失败', incomplete:'待继续', pending:'待继续'};
  const folderIcon = '<svg viewBox="0 0 64 48" fill="none" aria-hidden="true"><path d="M3 9a5 5 0 0 1 5-5h16l6 7h26a5 5 0 0 1 5 5v24a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5Z" fill="currentColor" opacity=".22"/><path d="M3 18a5 5 0 0 1 5-5h48a5 5 0 0 1 5 5v22a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5Z" fill="currentColor" opacity=".65"/></svg>';
  const branchIcon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="5" cy="4" r="2"/><circle cx="15" cy="5" r="2"/><circle cx="5" cy="16" r="2"/><path d="M5 6v8m0-3c8 0 10-1 10-4"/></svg>';
  const data = () => state.artifacts;
  const mode = () => ['tasks','conversations','files'].includes(value('browse')) ? value('browse') : 'tasks';
  const mobile = () => matchMedia('(max-width: 780px)').matches;
  const tasks = () => [...(data().tasks||[])].sort((a,b)=>b.updated_at.localeCompare(a.updated_at)||a.id.localeCompare(b.id));
  const taskById = id => (data().tasks||[]).find(t=>t.id===id);
  const outputs = id => (data().items||[]).filter(a=>a.task_id===id);
  const stamp = text => text && Number.isFinite(Date.parse(text)) ? new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(text)) : '时间未知';
  const statusBadge = t => `<span class="task-status ${e(t.status)}">${e(statuses[t.status]||'未完成')}</span>`;
  const sessionTitle = s => s?.title || (s?.id==='unlinked'?'未关联会话':'未命名会话');
  const sessions = () => data().conversations || [];
  const sessionTasks = () => tasks();
  const sessionMatches = () => true;
  const selectedSession = () => sessions().find(s => s.id === data().selected_conversation);
  const markScroll = () => history.replaceState({...history.state,scroll:scrollY,conversationScroll:document.querySelector('.conversation-list')?.scrollTop||0},'',location.href);
  function go(changes, {replace=false, drill=false}={}) {
    markScroll();
    const oldURL = location.pathname+location.search, url = new URL(location.href);
    for (const [key,val] of Object.entries(changes)) val==null||val===''?url.searchParams.delete(key):url.searchParams.set(key,val);
    const next = replace ? {...history.state} : {scroll:0,conversationScroll:history.state?.conversationScroll||0};
    if (drill) next.artifactBackURL=oldURL;
    history[replace?'replaceState':'pushState'](next,'',url);
    fetchPage({scroll:replace ? history.state?.scroll||0 : 0});
  }
  navigate = (changes, replace=false) => go(changes,{replace});
  function back() {
    if (history.state?.artifactBackURL) { history.back(); return; }
    if (value('view')==='detail') go({view:'collection',id:null,info:null},{replace:true});
    else if(value('folder')) go({folder:null},{replace:true});
    else go({conversation:null},{replace:true});
  }
  header = function() {
    const c=data().project_context||{}, branch=c.branch||'分支信息暂不可用';
    return `<header class="topbar"><div class="identity"><span class="symbol" aria-hidden="true">▧</span><div><strong>${e(state.title.replace(' · 合成预览',''))}</strong><div class="project-context"><span title="${e(c.path||state.project)}">项目 · ${e(c.name||state.project)}</span><span class="branch-pill" title="当前项目的 Git 状态">${branchIcon}<span>${e(branch)}</span></span></div></div></div><div class="session"><div class="session-line"><strong id="countdown"></strong><label><input id="residency" type="checkbox" ${state.lifetime.resident?'checked':''}>常驻</label><button class="text-button" data-action="stop">结束页面</button></div><small>常驻会持续占用系统资源；仅对本次服务有效。</small></div></header>${state.lifetime.resident?'<div class="notice">本次产物服务正在常驻。取消后重新开始 60 分钟空闲倒计时。</div>':''}`;
  };
  function tabs() {
    return `<nav class="browse-tabs" aria-label="产物查看方式">${[['tasks','按任务'],['conversations','按会话'],['files','按文件']].map(([id,label])=>`<button data-artifact-action="mode" data-mode="${id}" class="${mode()===id?'active':''}" aria-current="${mode()===id?'page':'false'}">${label}</button>`).join('')}</nav>`;
  }
  function pageHeading() {
    return `<div class="heading artifacts-heading"><div><div class="eyebrow">YOUR ARTIFACTS</div><h1>产物</h1><p>${data().totals.tasks} 个任务 · ${data().totals.files} 件产物<span class="subtle-divider">/</span>最近活动优先</p></div><button data-action="reload">↻ 刷新</button></div>${tabs()}`;
  }
  function fileType(a) {
    const extension = a.title?.match(/\.([a-z0-9]{1,8})$/i)?.[1]?.toUpperCase();
    return extension || ({image:'图片',video:'视频',audio:'音频',document:'文档',table:'表格',remote:'链接'}[a.kind]||'文件');
  }
  function taskThumbnail(a, remaining=0) {
    const p=a.preview||{},type=fileType(a);
    let visual;
    if(a.status&&a.status!=='可用') visual=`<span class="thumbnail-unavailable"><span aria-hidden="true">▧</span>${e(a.status)}</span>`;
    else if(p.type==='image'&&p.resource) visual=`<img loading="lazy" src="${resourceURL(p.resource)}" alt="${e(a.title)}的缩略图">`;
    else if(p.type==='video'&&p.resource) visual=`${a.thumbnail_resource?`<img loading="lazy" src="${resourceURL(a.thumbnail_resource)}" alt="${e(a.title)}的视频封面">`:`<video muted preload="metadata" playsinline aria-label="${e(a.title)}的视频封面" src="${resourceURL(p.resource)}#t=0.1"></video>`}<span class="thumbnail-play" aria-hidden="true">▶</span>`;
    else if(p.type==='table') visual=`<span class="thumbnail-sheet"><span class="sheet-heading">${(p.columns||[]).slice(0,3).map(c=>`<span>${e(c)}</span>`).join('')}</span>${(p.rows||[]).slice(0,3).map(row=>`<span class="sheet-row">${row.slice(0,3).map(c=>`<span>${e(c)}</span>`).join('')}</span>`).join('')}</span>`;
    else if(type==='JSON') visual=`<span class="thumbnail-code">${e((p.text||'{}').slice(0,200))}</span>`;
    else if(p.type==='markdown'||(p.type==='text'&&type!=='ZIP')) visual=`<span class="thumbnail-paper"><strong>${e(a.title)}</strong><span>${e((p.text||'').replace(/^#+\s*/gm,'').slice(0,180))}</span></span>`;
    else if(a.kind==='audio') visual='<span class="thumbnail-audio" aria-hidden="true">▂ ▅ ▃ ▇ ▄ ▂ ▆ ▃ ▅ ▂</span>';
    else visual=`<span class="thumbnail-format" aria-hidden="true">${e(type)}</span>`;
    return `<span class="task-thumbnail kind-${e(a.kind)} ${a.status&&a.status!=='可用'?'unavailable':''}" title="${e(a.title)}"><span class="thumbnail-visual">${visual}</span><span class="thumbnail-type">${e(type)}</span>${remaining?`<span class="thumbnail-more">+${remaining}<small>更多文件</small></span>`:''}</span>`;
  }
  function thumbnailStrip(t) {
    const files=outputs(t.id),shown=(t.thumbnail_ids||[]).map(id=>files.find(a=>a.id===id)).filter(Boolean);
    if(!files.length)return `<div class="folder-thumbnails empty-thumbnails"><span class="folder-icon">${folderIcon}</span><span>${t.status==='running'?'产物生成中':'暂无产物'}</span></div>`;
    return `<div class="folder-thumbnails count-${shown.length}">${shown.map((a,i)=>taskThumbnail(a,i===2?t.output_count-shown.length:0)).join('')}</div>`;
  }
  function fileTypes(t) {
    const counts=new Map(Object.entries(t.type_counts||{}).map(([type,n])=>[kinds[type]||type,n]));
    return `<div class="folder-types">${[...counts].map(([kind,count])=>`<span>${e(kind)} ${count}</span>`).join('')||`<span>${t.status==='failed'?'本次未生成交付文件':'任务信息已保留'}</span>`}</div>`;
  }
  function folderCard(t, conversationId) {
    const count=t.output_count, unavailable=t.unavailable_count;
    const relation=conversationId&&t.participants.find(p=>p.conversation_id===conversationId)?.relation;
    return `<article class="folder-card thumbnail-folder"><button class="folder-open" data-artifact-action="task" data-id="${e(t.id)}" aria-label="打开任务 ${e(t.title)} ${e(stamp(t.created_at))}"><div class="folder-top"><span class="folder-label"><span class="folder-icon">${folderIcon}</span>任务文件夹</span>${statusBadge(t)}</div><h3>${e(t.title)}</h3><p>${e(t.host)}<span>·</span>${e(t.skill)}</p>${thumbnailStrip(t)}${fileTypes(t)}<div class="folder-bottom"><strong>${count?count+' 件产物':'暂无产物'}</strong><span>${e(stamp(t.updated_at))} <span aria-hidden="true">›</span></span></div>${relation||unavailable?`<div class="folder-context">${relation?`<span>${e(relation)}${t.participants.length>1?' · 跨会话协作':''}</span>`:''}${unavailable?`<span class="file-warning">${unavailable} 件当前不可用</span>`:''}</div>`:''}</button></article>`;
  }
  function pager(count, key) {
    const section=key==='filepage'?'files':key==='sessionpage'?'sessions':'tasks';
    const {size,page,total}=data().paging[section], pages=Math.ceil(total/size);
    if(pages<=1)return '';
    return `<div class="pagination"><span>${(page-1)*size+1}–${Math.min(page*size,total)} / ${total}</span><div><button data-artifact-action="page" data-key="${key}" data-page="${page-1}" ${page===1?'disabled':''}>上一页</button><span>${page} / ${pages}</span><button data-artifact-action="page" data-key="${key}" data-page="${page+1}" ${page===pages?'disabled':''}>下一页</button></div></div>`;
  }
  function folderGrid(list,key,conversationId) {
    return `<div class="folder-grid">${list.map(t=>folderCard(t,conversationId)).join('')||'<div class="empty"><h2>没有找到任务</h2><p>调整搜索或状态筛选后再查看。</p></div>'}</div>${pager(0,key)}`;
  }
  function taskCollection() {
    const query=value('taskq').toLowerCase(), status=value('status');
    const list=tasks().filter(t=>(!status||t.status===status)&&[t.title,t.host,t.skill].join(' ').toLowerCase().includes(query));
    return `<div class="toolbar task-toolbar"><input id="task-search" data-query="taskq" type="search" placeholder="搜索任务、Skill 或执行工具…" aria-label="搜索任务" value="${e(value('taskq'))}"><select data-filter="status" aria-label="任务状态"><option value="">全部状态</option>${Object.entries(statuses).map(([id,label])=>`<option value="${id}" ${status===id?'selected':''}>${label}</option>`).join('')}</select><span class="result-count">${data().paging.tasks.total} 个任务</span></div>${folderGrid(list,'taskpage')}`;
  }
  function conversationCollection() {
    const visible=sessions().filter(sessionMatches), selected=selectedSession();
    return `<div class="conversations ${selected?'has-selection':''}"><aside class="conversation-panel" aria-label="会话列表"><div class="conversation-search"><input data-query="sessionq" type="search" placeholder="搜索会话…" aria-label="搜索会话" value="${e(value('sessionq'))}"></div><div class="conversation-list">${visible.map(s=>`<button class="conversation-row ${selected?.id===s.id?'active':''}" data-artifact-action="conversation" data-id="${e(s.id)}" aria-pressed="${selected?.id===s.id}"><span class="conversation-avatar">${s.id==='unlinked'?'?':s.host==='Codex'?'C':'W'}</span><span class="conversation-label"><strong>${e(sessionTitle(s))}</strong><small>${e(s.host||'未取得会话身份')}${s.fork_of?' · 分叉会话':''}${!s.title&&s.short_id?' · '+e(s.short_id):''}</small><small>${s.updated_at?e(stamp(s.updated_at))+' · ':''}${s.task_count} 个任务</small></span><span aria-hidden="true">›</span></button>`).join('')||'<p class="muted">没有匹配的会话</p>'}</div>${pager(0,'sessionpage')}</aside><section class="conversation-content">${selected?`<button class="text-button mobile-conversation-back" data-artifact-action="back">← 会话列表</button><div class="conversation-heading"><div><h2>${e(sessionTitle(selected))}</h2><p>${e(selected.host||'没有关联会话的任务会收纳在这里')}${selected.short_id?' · '+e(selected.short_id):''}${selected.fork_of?' · 独立分叉会话':''}</p></div><span>${selected.task_count} 个任务</span></div>${folderGrid(sessionTasks(selected.id),'conversationpage',selected.id)}`:'<div class="empty"><h2>选择一个会话</h2><p>查看这次会话创建或继续的任务。</p></div>'}</section></div>`;
  }
  filtered = () => data().items || [];
  const originalCard=card;
  card = a => originalCard(a).replaceAll('data-action="open"','data-artifact-action="file"').replace('<div class="card-visual">',`<div class="card-visual">${a.status!=='可用'?`<span class="availability">${e(a.status)}</span>`:''}`);
  function fileCollection() {
    const folder=value('folder'), all=folder?outputs(folder):data().items, typeKey=folder?'ftype':'type', qKey=folder?'fq':'q', list=value('layout')==='list';
    const types=data().available_types||[];
    return `<div class="toolbar file-toolbar"><input data-query="${qKey}" type="search" placeholder="搜索产物…" aria-label="搜索产物" value="${e(value(qKey))}"><select data-filter="${typeKey}" aria-label="按类型筛选"><option value="">全部类型</option>${types.map(k=>`<option value="${e(k)}" ${value(typeKey)===k?'selected':''}>${e(kinds[k]||k)}</option>`).join('')}</select>${!folder?`<input data-query="filetaskq" type="search" placeholder="搜索任务筛选…" aria-label="搜索任务筛选" value="${e(value('filetaskq'))}"><select data-filter="filetask" aria-label="按任务筛选"><option value="">全部任务</option>${(data().task_options||[]).map(t=>`<option value="${e(t.id)}" ${value('filetask')===t.id?'selected':''}>${e(t.title)} · ${t.created_at.slice(11,16)}</option>`).join('')}</select>`:''}<div class="segmented"><button data-artifact-action="layout" data-layout="cards" class="${!list?'active':''}">卡片</button><button data-artifact-action="layout" data-layout="list" class="${list?'active':''}">列表</button></div></div><div class="count">${data().paging.files.total} 件产物</div><div id="collection" class="${list?'list':'grid'}">${filtered().map(card).join('')||'<div class="empty"><h2>暂无产物</h2><p>任务信息会保留，有文件交付后可在这里查看。</p></div>'}</div>${pager(0,'filepage')}`;
  }
  function taskInfo(t) {
    const linked=t.participants.map(p=>{const s=sessions().find(s=>s.id===p.conversation_id);return `${sessionTitle(s)}（${p.relation}）`;});
    return `<details class="task-info"><summary>任务信息${t.supporting.length?'与辅助资料':''}</summary><dl><dt>任务目录</dt><dd>${e(t.directory)}</dd><dt>基本信息</dt><dd>task-info.json</dd><dt>执行工具 / Agent</dt><dd>${e(t.host)} · ${e(t.agent_name)} · ${e(t.agent_role)}</dd>${t.agent_model?`<dt>Agent 模型</dt><dd>${e(t.agent_model)}</dd>`:''}${t.generation_model?`<dt>生成模型</dt><dd>${e(t.generation_model)}</dd>`:''}<dt>关联会话</dt><dd>${linked.length?linked.map(e).join('<br>'):'未关联会话'}</dd><dt>创建 / 最近活动</dt><dd>${e(stamp(t.created_at))} / ${e(stamp(t.updated_at))}</dd><dt>任务标识</dt><dd>${e(t.id)}</dd></dl>${t.supporting.length?`<div class="supporting"><h3>辅助资料 · 不计入产物数量</h3>${t.supporting.map(s=>`<details><summary>${e(s.title)}</summary><p>${e(s.text)}</p></details>`).join('')}</div>`:''}</details>`;
  }
  function taskDetail() {
    const t=taskById(value('folder'));
    if(!t)return '<div class="empty"><h2>任务暂不可用</h2><button data-artifact-action="back">返回任务列表</button></div>';
    return `<nav class="task-breadcrumb"><button class="text-button" data-artifact-action="back">← ${mode()==='conversations'?'会话任务':'全部任务'}</button><span>/</span><span>${e(t.title)}</span></nav><div class="task-detail-heading"><span class="folder-icon">${folderIcon}</span><div><h2>${e(t.title)}</h2><p>${e(t.host)} · ${e(t.skill)} · ${e(stamp(t.created_at))}</p></div>${statusBadge(t)}</div>${t.message?`<p class="task-message ${e(t.status)}">${e(t.message)}</p>`:''}${taskInfo(t)}${fileCollection()}`;
  }
  collection = function() {
    return `<section class="content artifacts-content">${value('folder')?tabs()+taskDetail():pageHeading()+(mode()==='conversations'?conversationCollection():mode()==='files'?fileCollection():taskCollection())}</section>`;
  };
  detail = function() {
    const a=data().items.find(a=>a.id===value('id'));
    if(!a)return '<div class="empty"><h2>这件产物已不可用</h2><button data-artifact-action="back">返回</button></div>';
    const t=taskById(a.task_id), local=Boolean(value('folder')), siblings=data().items, nav=data().navigation||{}, index=(nav.index||1)-1;
    const sidebar=value('sidebar','1')!=='0', info=value('info')==='1', link=safeURL(a.url), copy=a.copy_text??a.preview?.text;
    return `<nav class="viewer-nav"><button class="text-button" data-artifact-action="back">← ${local?e(t?.title||'任务产物'):'文件集合'}</button><button class="text-button sidebar-toggle" data-action="sidebar">${sidebar?'收起':'展开'}文件侧栏</button><div class="file-step"><button data-artifact-action="adjacent" data-id="${e(nav.previous||'')}" aria-label="上一件产物" ${index<1?'disabled':''}>‹</button><span>${nav.index||1} / ${nav.total||1}</span><button data-artifact-action="adjacent" data-id="${e(nav.next||'')}" aria-label="下一件产物" ${!nav.next?'disabled':''}>›</button></div></nav><div class="viewer-body">${sidebar?`<aside class="sidebar" aria-label="${local?'当前任务产物':'筛选后的产物'}">${siblings.map(item=>`<button data-artifact-action="adjacent" data-id="${e(item.id)}" class="${a.id===item.id?'active':''}">${e(item.title)}</button>`).join('')}</aside>`:''}<section class="viewer"><header class="preview-toolbar"><div><h2>${e(a.title)}</h2><small>${e(t?.title)} · ${e(a.status)}</small></div><div class="actions">${copy!==undefined?'<button data-action="copy">复制内容</button>':''}${link?`<a class="button" href="${e(link)}" target="_blank" rel="noopener noreferrer">打开 ↗</a>`:''}${a.resource?`<a class="button" href="${resourceURL(a.resource,true)}" download>下载</a>`:''}<button data-action="info">ⓘ 信息</button></div></header><div class="preview">${a.preview_note?`<p class="muted">${e(a.preview_note)}</p>`:''}${previewHTML(a)}</div></section>${info?`<aside class="metadata"><h3>产物信息</h3><button class="text-button" data-action="info">关闭信息 ×</button><dl>${Object.entries(a.metadata||{}).map(([k,v])=>`<dt>${e(k)}</dt><dd>${e(v)}</dd>`).join('')}</dl></aside>`:''}</div>`;
  };
  const originalRender=render;
  render = function() {
    originalRender();
    document.querySelector('.shell')?.classList.add('artifacts-shell');
    const list=document.querySelector('.conversation-list');
    if(list)list.scrollTop=history.state?.conversationScroll||0;
  };
  let requestSequence=0;
  async function fetchPage({refresh=false,scroll=history.state?.scroll||0}={}) {
    const sequence=++requestSequence, query=new URLSearchParams(location.search);
    query.set('mobile',mobile()?'1':'0');
    if(refresh)query.set('refresh','1');
    root.setAttribute('aria-busy','true');
    try {
      const snapshot=await api('/api/artifacts?'+query);
      if(sequence!==requestSequence)return;
      const active=document.activeElement, field=active?.dataset?.query, start=active?.selectionStart,end=active?.selectionEnd;
      state.artifacts=snapshot;render();
      if(field){const input=root.querySelector(`[data-query="${field}"]`);input?.focus({preventScroll:true});input?.setSelectionRange(start,end);}
      window.scrollTo(0,scroll);
    } catch(error) {if(sequence===requestSequence)fail(error);}
    finally {if(sequence===requestSequence)root.removeAttribute('aria-busy');}
  }
  load=async function(){
    state=await api('/api/state');csrf=state.csrf;remaining=state.lifetime.remaining;
    await fetchPage({refresh:true});
  };
  window.addEventListener('popstate',event=>{event.stopImmediatePropagation();fetchPage();},true);
  root.addEventListener('click', event=>{
    const b=event.target.closest('[data-artifact-action]');if(!b||ended)return;
    event.stopImmediatePropagation();
    const act=b.dataset.artifactAction;
    if(act==='mode')go({browse:b.dataset.mode,view:'collection',folder:null,id:null,info:null,filepage:null});
    if(act==='task')go({folder:b.dataset.id,view:'collection',id:null,fq:null,ftype:null,filepage:null},{drill:true});
    if(act==='conversation')go({conversation:b.dataset.id,conversationpage:null,folder:null},{replace:!mobile(),drill:mobile()});
    if(act==='file')go({view:'detail',id:b.dataset.id,info:null},{drill:true});
    if(act==='adjacent')go({id:b.dataset.id,info:null},{replace:true});
    if(act==='layout')go({layout:b.dataset.layout},{replace:true});
    if(act==='page')go({[b.dataset.key]:b.dataset.page},{replace:true});
    if(act==='back')back();
  },true);
  root.addEventListener('input',event=>{
    const node=event.target,key=node.dataset.query;if(!key||ended)return;
    event.stopImmediatePropagation();
    if(event.isComposing)return;
    go({[key]:node.value,taskpage:null,conversationpage:null,filepage:null,sessionpage:null},{replace:true});
  },true);
  root.addEventListener('change',event=>{
    const node=event.target,key=node.dataset.filter;if(!key||ended)return;
    event.stopImmediatePropagation();go({[key]:node.value,taskpage:null,conversationpage:null,filepage:null,sessionpage:null},{replace:true});
  },true);
  matchMedia('(max-width: 780px)').addEventListener('change',()=>fetchPage());
  document.title=state.title+' · 产物';
  await fetchPage();
}
