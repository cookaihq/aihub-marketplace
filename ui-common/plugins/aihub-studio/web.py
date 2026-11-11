from importlib import import_module
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEECH = 'skills/aihub-audio/models/minimax-speech/'
library = import_module(__package__ + '.skills.aihub-audio.models.minimax-speech.library')


def assets(extension):
    names = [SPEECH + 'voice-library.' + extension]
    if extension == 'js':
        names.append(SPEECH + 'integration.js')
    return '\n'.join((ROOT / name).read_text(encoding='utf-8') for name in names)


def media_policy(value):
    return value.replace("media-src 'self'", "media-src 'self' " + ' '.join(library.SAMPLE_ORIGINS))


def voices(configuration):
    return library.load(configuration)
