{
  const voiceKey = 'AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', favoriteKey = 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS';
  const library = new ElevenLabsVoiceLibrary(configurationUI);
  const control = Configuration.prototype.controlHTML;
  Configuration.prototype.controlHTML = function(field) {
    const original = control.call(this, field);
    if (![voiceKey, favoriteKey].includes(field.id)) return original;
    return '<div class="voice-library-controls"><div class="voice-entry"><div><strong>ElevenLabs 预置音色库</strong><p>筛选、试听、选择和收藏，保存到当前项目或全局配置。</p></div><button type="button" class="primary" data-open-elevenlabs-library="' +
      (field.id === favoriteKey ? 'favorites' : 'choose') + '">打开音色库</button></div></div>' + original;
  };
  root.addEventListener('click', event => {
    const button = event.target.closest('[data-open-elevenlabs-library]');
    if (button && !configurationUI.busy) library.open(button.dataset.openElevenlabsLibrary);
  });
  const afterRender = Configuration.prototype.afterRender;
  let opened = false;
  Configuration.prototype.afterRender = function() {
    afterRender.call(this);
    if (!opened && new URL(location.href).searchParams.get('voice-library') === 'elevenlabs') {
      opened = true;
      queueMicrotask(() => { configurationUI.open(voiceKey); library.open('choose'); });
    }
  };
  // The core completes its first render before the appended integrations execute.
  if (configurationUI.snapshot) configurationUI.afterRender();
  window.addEventListener('pagehide', () => library.close());
}
