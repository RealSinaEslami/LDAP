import json
import os
import unittest

os.environ['LDAP_BIND_PASSWORD'] = 'offline-placeholder'
os.environ['API_KEY'] = 'offline-test-key'
os.environ['DATABASE_URL'] = 'sqlite://'

import httpx

from services.avalai_client import AvalAIClient, AvalAIError, completion_url
from services.gemini_alias_service import GeneratedAliases


class AvalAITests(unittest.TestCase):
    def test_urls(self):
        expected = 'https://api.avalai.ir/v1/chat/completions'
        for url in ['https://api.avalai.ir', 'https://api.avalai.ir/v1/', expected]:
            self.assertEqual(completion_url(url), expected)
        with self.assertRaises(ValueError):
            completion_url('https://api.avalai.ir/v1/responses')

    def test_request_uses_configured_url_key_model(self):
        def handler(request):
            self.assertEqual(str(request.url), 'https://provider.example/v1/chat/completions')
            self.assertEqual(request.headers['Authorization'], 'Bearer test-key')
            body = json.loads(request.content)
            self.assertEqual(body['model'], 'my-model')
            self.assertEqual(body['response_format']['type'], 'json_object')
            self.assertEqual(body['messages'][1]['content'], 'name-data')
            return httpx.Response(200, json={'choices': [{'message': {'content': '{"ok":true}'}}]})

        with AvalAIClient('test-key', 'https://provider.example/v1', httpx.MockTransport(handler)) as client:
            response = client.models.generate_content(model='my-model', contents='name-data',
                        config={'system_instruction': 'Names only', 'response_schema': GeneratedAliases})
            self.assertEqual(json.loads(response.text), {'ok': True})

    def test_errors_are_redacted_and_status_preserved(self):
        with AvalAIClient('secret', 'https://provider.example/v1',
                         httpx.MockTransport(lambda request: httpx.Response(401, text='private response'))) as client:
            with self.assertRaises(AvalAIError) as error:
                client.generate_content(model='m', contents='data',
                                        config={'system_instruction': '', 'response_schema': GeneratedAliases})
            self.assertEqual(error.exception.code, 401)
            self.assertNotIn('private', str(error.exception))
