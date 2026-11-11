"""Voice catalogue access remains scoped to an authenticated Studio configuration page."""
from contextlib import contextmanager
from importlib import import_module
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError

MARKET = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(MARKET / 'aihub-studio/shared'), str(MARKET / 'ui-common')]
from skill_ui import server
from skill_ui.contracts import UIError
from web import MarketplaceHandler
library = import_module('plugins.aihub-studio.skills.aihub-audio.models.minimax-speech.library')


class VoiceLibrary(unittest.TestCase):
    def test_samples_use_published_https_hosts_without_credentials(self):
        allowed = 'https://ftres.oss-cn-beijing.aliyuncs.com/aitools/voices/sample.mp3'
        self.assertEqual(library.sample_url(allowed), allowed)
        for url in ('http://ftres.oss-cn-beijing.aliyuncs.com/a.mp3', 'https://localhost/audio',
                    'https://127.0.0.1/audio', 'https://filecdn.minimax.chat.evil.test/a.mp3',
                    'https://user:secret@filecdn.minimax.chat/a.mp3', 'https://filecdn.minimax.chat:444/a.mp3', None):
            self.assertEqual(library.sample_url(url), '')

    def test_loader_retains_voice_ids_when_sample_is_unusable(self):
        cfg = SimpleNamespace(package=MARKET / 'aihub-studio',project=MARKET,environment={},options={'global_enabled':False})
        fixture = {'voices':[{'voice_id':'Chinese (Mandarin)_Warm_Girl','sample_audio':'https://localhost/secret'}]}
        with patch.object(library.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps(fixture),'')) as run:
            result = library.load(cfg)
            self.assertEqual(result['voices'][0]['sample_audio'], '')
            self.assertEqual(result['voices'][0]['voice_id'], 'Chinese (Mandarin)_Warm_Girl')
            payload = json.loads(run.call_args.kwargs['input'])
            self.assertFalse(payload['global_enabled'])
            self.assertNotIn('url', payload)
        with patch.object(library.subprocess,'run',side_effect=subprocess.TimeoutExpired('node',35)):
            with self.assertRaises(UIError): library.load(cfg)

    @contextmanager
    def service(self, plugin='aihub-studio', page='configuration'):
        with tempfile.TemporaryDirectory(dir=os.environ['TEMP'],prefix='voice-http-') as folder:
            path = Path(folder)
            adapter = SimpleNamespace(plugin=plugin,options={},configuration=object())
            with patch.object(server,'Handler',MarketplaceHandler):
                app = server.Server(adapter,path,page,path)
            thread = threading.Thread(target=app.serve_forever,daemon=True); thread.start()
            client = build_opener(ProxyHandler({}))
            def get(route='/api/minimax-voices',auth=True,host=None):
                headers = {'Cookie':app.cookie_name + '=' + app.cookie} if auth else {}
                if host: headers['Host']=host
                return client.open(Request(app.origin + route,headers=headers),timeout=5)
            try: yield app,get
            finally: app.shutdown();app.server_close();thread.join(timeout=5)

    def test_auth_origin_lifetime_and_product_boundaries(self):
        with patch.object(library,'load',return_value={'voices':[]}) as load:
            with self.service() as (app,get):
                for kwargs,status in (({'auth':False},401),({'host':'foreign.invalid'},403)):
                    with self.assertRaises(HTTPError) as error: get(**kwargs)
                    self.assertEqual(error.exception.code,status)
                load.assert_not_called()
                with get() as response:
                    self.assertEqual(json.load(response), {'voices':[]})
                    self.assertIn('https://filecdn.minimax.chat',response.headers['Content-Security-Policy'])
                load.assert_called_once()
                with get('/app.js') as response:
                    script = response.read().decode()
                    self.assertIn('class SpeechVoiceLibrary',script)
                    self.assertNotIn('模拟保存',script)
                app.last_use=0
                with self.assertRaises(HTTPError) as error: get()
                self.assertEqual(error.exception.code,410)
            for plugin,page in (('tikin-social','configuration'),('aihub-studio','artifacts')):
                with self.service(plugin,page) as (_,get):
                    with self.assertRaises(HTTPError) as error: get()
                    self.assertEqual(error.exception.code,404)
                    with get('/app.js') as response:
                        self.assertNotIn('SpeechVoiceLibrary',response.read().decode())
                        self.assertNotIn('https://filecdn.minimax.chat',response.headers['Content-Security-Policy'])


if __name__ == '__main__': unittest.main()
