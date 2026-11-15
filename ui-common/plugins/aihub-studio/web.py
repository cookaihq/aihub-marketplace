from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEECH = 'skills/aihub-audio/models/minimax-speech/'
ELEVEN = 'skills/aihub-audio/models/elevenlabs/'
library = import_module(__package__ + '.skills.aihub-audio.models.minimax-speech.library')
eleven_library = import_module(__package__ + '.skills.aihub-audio.models.elevenlabs.library')


def assets(extension):
    names = ['form.css', 'skills/aihub-audio/voice-library.css'] if extension == 'css' else ['skills/aihub-audio/voice-library.js']
    if extension == 'js':
        names.extend([SPEECH + 'voice-library.js', SPEECH + 'integration.js', ELEVEN + 'voice-library.js', ELEVEN + 'integration.js'])
    else:
        names.append(ELEVEN + 'voice-library.css')
    content = '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in names)
    if extension == 'js':
        # The pinned app bootstraps with top-level await before these business
        # controls are installed. Apply all controls to its initial snapshot.
        content += "\nif(state?.page==='configuration'&&!ended)render();\n"
    return content


def media_policy(value):
    return value.replace("media-src 'self'", "media-src 'self' " + ' '.join(library.SAMPLE_ORIGINS + eleven_library.SAMPLE_ORIGINS))


def voices(configuration, provider='minimax'):
    return (eleven_library if provider == 'elevenlabs' else library).load(configuration)
