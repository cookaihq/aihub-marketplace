// Product guidance; drafts and persistence remain in the shared form.
const baseTikinField = Configuration.prototype.fieldHTML;
Configuration.prototype.fieldHTML = function(field) {
  const html = baseTikinField.call(this, field);
  if (field.id !== 'TIKIN_API_KEY') return html;
  const fragment = document.createElement('template');
  fragment.innerHTML = html;
  const guide = document.createElement('p');
  guide.className = 'field-help key-guide';
  guide.innerHTML = '<a href="https://console.tikin.net" target="_blank" rel="noopener noreferrer">获取 API Key ↗</a> · 或联系团队负责人分配';
  fragment.content.querySelector('.context-field-label').after(guide);
  return fragment.innerHTML;
};
if(state?.page==='configuration'&&!ended)render();
