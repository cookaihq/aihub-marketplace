// Studio guidance extends the shared field form; all persistence stays in Configuration.
const baseStudioField = Configuration.prototype.fieldHTML;
Configuration.prototype.fieldHTML = function(field) {
  const fragment = document.createElement('template');
  fragment.innerHTML = baseStudioField.call(this, field);
  if (field.id === 'AIHUB_API_KEY') {
    const heading = fragment.content.querySelector('.context-field-label');
    const help = fragment.content.querySelector('.field-help');
    const info = document.createElement('div');
    info.className = 'key-heading-info';
    if (help) info.append(help);
    info.insertAdjacentHTML('beforeend', '<p class="key-guide"><a href="https://api.aihubmax.com/console" target="_blank" rel="noreferrer">获取 API Key ↗</a><span>或联系团队负责人分配</span></p>');
    heading.append(info);
  }
  return fragment.innerHTML;
};
