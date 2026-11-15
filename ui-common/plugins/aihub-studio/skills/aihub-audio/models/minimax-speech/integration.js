// The model adds controls inside the shared center, without a separate page or service.
{
  const voiceKey = 'AIHUB_MINIMAX_SPEECH_DEFAULT_VOICE_ID';
  const favoriteKey = 'audio.minimax_speech.favorite_voice_ids';
  const library = new SpeechVoiceLibrary(configurationUI);
  const control = Configuration.prototype.controlHTML;
  Configuration.prototype.controlHTML = function(field) {
    const original = control.call(this, field);
    if (![voiceKey, favoriteKey].includes(field.id)) return original;
    const isVoice = field.id === voiceKey;
    return '<div class="voice-library-controls"><div class="voice-entry"><div><strong>' + (isVoice ? '从音色库选择' : '管理收藏音色') + '</strong><p>搜索、筛选、试听，保留常用候选。</p></div><button type="button" class="primary" data-open-voice-library="' + (isVoice ? 'choose' : 'favorites') + '">' + (isVoice ? '打开音色库' : '打开我的收藏') + '</button></div></div>' + (isVoice ? '<div class="manual-voice-label">也可填写自定义 / 克隆音色 ID</div>' : '') + original;
  };
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-open-voice-library]');
    if (button && !configurationUI.busy && !configurationUI.expired && !configurationUI.uncertain) library.open(button.dataset.openVoiceLibrary);
  });
  window.addEventListener('pagehide', () => library.close());
}
