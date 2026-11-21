import os
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ['LDAP_BIND_PASSWORD'] = 'offline-placeholder'
os.environ['API_KEY'] = 'offline-test-key'
os.environ['DATABASE_URL'] = 'sqlite://'

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from database import Base
from models.data_model import LDAPUser, UserAlias
from services.gemini_alias_service import GeneratedAliases, clean_aliases, generate_aliases, save_aliases


class GeminiAliasTests(unittest.TestCase):
    def generated(self):
        return GeneratedAliases(first_names=['پویا'], last_names=['خسروی'],
                                full_names=['پویا خسروی'], latin_variants=['pooya', 'poya', 'puya', 'POOYA'],
                                nicknames=[])

    def test_model_payload_and_output(self):
        client = Mock()
        client.models.generate_content.return_value = SimpleNamespace(text=self.generated().model_dump_json())
        user = LDAPUser(first_name='Pouya', last_name='Khosravi', display_name='Pouya Khosravi',
                        email='private@example.com', distinguished_name='private DN')
        result = generate_aliases(client, 'configured-model', user, [])
        self.assertIn('puya', result.latin_variants)
        request = client.models.generate_content.call_args.kwargs
        self.assertEqual(request['model'], 'configured-model')
        self.assertNotIn('private', request['contents'])
        self.assertEqual(json.loads(request['contents'])['first_name'], 'Pouya')

    def test_cleaning_and_existing_aliases(self):
        generated = self.generated()
        generated.nicknames = ['<script>', '123', 'https://example.com']
        pairs = clean_aliases(generated, ['پويا'])
        names = [normalized for _, normalized in pairs]
        self.assertNotIn('پویا', names)
        self.assertEqual(names.count('pooya'), 1)
        self.assertEqual(len(pairs), 5)

    def test_saving_is_additive_idempotent_and_rollbackable(self):
        engine = create_engine('sqlite://')
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(LDAPUser(uid='test', distinguished_name='CN=test', enabled=True,
                                 last_seen_at=datetime.now(timezone.utc)))
            session.add(UserAlias(user_uid='test', name='manual', normalized_name='manual'))
            session.commit()
            pairs = clean_aliases(self.generated(), [])
            self.assertEqual(save_aliases(session, 'test', pairs), 6)
            session.rollback()
            self.assertEqual(len(session.scalars(select(UserAlias)).all()), 1)
            self.assertEqual(save_aliases(session, 'test', pairs), 6)
            session.commit()
            self.assertEqual(save_aliases(session, 'test', pairs), 0)
            session.commit()
            self.assertEqual(len(session.scalars(select(UserAlias)).all()), 7)
        engine.dispose()

    def test_transient_errors_retry_but_auth_errors_do_not(self):
        class APIError(Exception):
            code = 429
        client = Mock()
        client.models.generate_content.side_effect = [APIError(), SimpleNamespace(text=self.generated().model_dump_json())]
        with patch('services.gemini_alias_service.time.sleep'):
            generate_aliases(client, 'model', LDAPUser(first_name='Pouya'), [])
        self.assertEqual(client.models.generate_content.call_count, 2)
