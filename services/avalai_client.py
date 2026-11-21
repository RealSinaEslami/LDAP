"""Minimal AvalAI Chat Completions adapter for the alias generator."""
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx


class AvalAIError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(f'LLM request failed (status={code})')


def completion_url(url: str) -> str:
    url = url.strip().rstrip('/')
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('LLM_URL must be an HTTP(S) base URL or chat/completions endpoint')
    if parsed.path.endswith('/chat/completions'):
        return url
    if parsed.path not in ('', '/v1'):
        raise ValueError('Use the provider base URL ending in /v1 or /chat/completions')
    return url + ('/v1' if not parsed.path else '') + '/chat/completions'


class AvalAIClient:
    def __init__(self, api_key: str, url: str, transport=None):
        self.url = completion_url(url)
        self.models = self
        self.client = httpx.Client(timeout=60, follow_redirects=False, transport=transport,
                                   headers={'Authorization': f'Bearer {api_key}'})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()

    def generate_content(self, *, model, contents, config):
        # JSON mode is broadly compatible; Pydantic validates the actual response locally.
        schema = config['response_schema'].model_json_schema()
        instruction = config['system_instruction'] + '\nReturn a JSON object matching this schema:\n' + json.dumps(schema)
        try:
            response = self.client.post(self.url, json={
                'model': model,
                'messages': [{'role': 'system', 'content': instruction},
                             {'role': 'user', 'content': contents}],
                'response_format': {'type': 'json_object'},
            })
        except httpx.TransportError:
            raise AvalAIError(503) from None
        if not response.is_success:
            raise AvalAIError(response.status_code)
        data = response.json()
        choice = data['choices'][0]
        if choice.get('finish_reason') in ('length', 'content_filter'):
            raise ValueError('Incomplete or blocked model response')
        text = choice['message'].get('content')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Empty model response')
        return SimpleNamespace(text=text)
