// Only this DOM vocabulary can be produced by a Markdown preview. Never insert document HTML.
function renderMarkdown(container, nodes) {
  const tags = new Set(['p','h1','h2','h3','h4','h5','h6','blockquote','ul','ol','li','strong','em','s',
    'table','thead','tbody','tr','th','td','pre','code','hr','br','span','a']);
  function unavailable(alt, reason) {
    const message = document.createElement('span');
    message.className = 'markdown-image-error';
    message.setAttribute('role', 'status');
    message.textContent = [alt, reason].filter(Boolean).join('：');
    return message;
  }
  function create(node) {
    if (node.tag === 'img') {
      if (!node.resource || node.error) return unavailable(node.alt, node.error || '图片不可用。');
      const img = document.createElement('img');
      img.alt = node.alt || '';
      img.title = node.title || '';
      img.loading = 'lazy';
      img.decoding = 'async';
      img.addEventListener('error', () => img.replaceWith(unavailable(node.alt, '图片无法读取或已变更，请刷新后核对。')), {once:true});
      img.src = resourceURL(node.resource);
      return img;
    }
    if (!node.tag) return document.createTextNode(node.text || '');
    const tag = tags.has(node.tag) ? node.tag : 'span';
    const element = document.createElement(tag);
    if (tag === 'a') {
      const href = safeURL(node.href);
      if (href) {
        element.href = href;
        element.target = '_blank';
        element.rel = 'noopener noreferrer';
      }
    }
    if (tag === 'ol' && Number.isSafeInteger(node.start)) element.start = node.start;
    if (node.title) element.title = node.title;
    if (node.text !== undefined) element.textContent = node.text;
    for (const child of node.children || []) element.append(create(child));
    return element;
  }
  container.replaceChildren(...nodes.map(create));
}
