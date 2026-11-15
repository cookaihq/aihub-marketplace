{
  const control = Configuration.prototype.controlHTML;
  Configuration.prototype.controlHTML = function(field) {
    const original = control.call(this, field);
    if (!['AIHUB_ELEVENLABS_DEFAULT_VOICE_ID', 'AIHUB_ELEVENLABS_FAVORITE_VOICE_IDS'].includes(field.id)) return original;
    return '<div class="voice-entry"><div><strong>ElevenLabs 预置音色库</strong><p>筛选、试听、选择和收藏。</p></div><button type="button" data-voice-open="' + field.id + '" ' + (this.expired ? 'disabled' : '') + '>打开音色库</button></div>' + original;
  };
}
