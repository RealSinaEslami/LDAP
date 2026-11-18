import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID

os.environ['LDAP_BIND_PASSWORD'] = 'offline-placeholder'
os.environ['API_KEY'] = 'offline-test-key'
os.environ['DATABASE_URL'] = 'sqlite://'

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from models.data_model import LDAPUser
from routers.data_router import add_alias, delete_alias, list_aliases
from schemas.data_schema import AliasCreate, SearchHit
from services import data_service
from services.name_matching import normalize_name, score_name
from services.search_service import search_users


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.ali = self.user(1, 'Ali', 'Masoudi')
        self.fatemeh = self.user(2, 'Fatemeh', 'Ahmadi')
        self.other = self.user(3, 'Fatemeh', 'Kazemi')
        self.session.commit()

    def user(self, number, first, last):
        user = LDAPUser(uid=str(UUID(int=number)), username=f'user{number}', first_name=first,
                        last_name=last, display_name=f'{first} {last}', distinguished_name=f'CN=user{number}',
                        enabled=True, last_seen_at=datetime.now(timezone.utc))
        self.session.add(user)
        return user

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def search(self, query, **kwargs):
        return search_users(self.session, query, **kwargs)

    def alias(self, user, name):
        return add_alias(UUID(user.uid), AliasCreate(name=name), self.session)

    def test_exact_typo_reordered_prefix_and_unrelated(self):
        for query in ['Ali Masoudi', 'Ali Masodi', 'Ali Masuodi', 'Masoudi Ali', 'ali mas']:
            with self.subTest(query=query):
                hit = self.search(query)[0]
                self.assertEqual(hit['user'].uid, self.ali.uid)
                SearchHit.model_validate(hit)
        self.assertEqual(self.search('Ali Masoudi')[0]['score'], 100)
        self.assertEqual(self.search('Qzxw Jkpr'), [])
        self.assertEqual(self.search('a'), [])
        self.assertEqual(self.search('...'), [])

    def test_persian_normalization_and_aliases_are_person_specific(self):
        self.assertEqual(normalize_name('  عَلِيّ كاظمي '), 'علی کاظمی')
        self.alias(self.fatemeh, 'یاسی')
        self.alias(self.fatemeh, 'Yasi Ahmadi')
        self.alias(self.fatemeh, 'فاطمه احمدی')
        for query in ['ياسي', 'Yasi Ahmadi', 'فاطمه احمدي']:
            hit = self.search(query)[0]
            self.assertEqual(hit['user'].uid, self.fatemeh.uid)
            self.assertEqual(hit['matched_field'], 'alias')
        self.assertNotIn(self.other.uid, [h['user'].uid for h in self.search('یاسی')])

    def test_alias_duplicates_validation_and_delete(self):
        alias = self.alias(self.fatemeh, 'یاسی')
        with self.assertRaises(HTTPException) as error:
            self.alias(self.fatemeh, ' ياسي ')
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(ValidationError):
            AliasCreate(name='---')
        self.assertEqual(len(list_aliases(UUID(self.fatemeh.uid), self.session)), 1)
        with self.assertRaises(HTTPException):
            delete_alias(UUID(self.other.uid), alias.id, self.session)
        delete_alias(UUID(self.fatemeh.uid), alias.id, self.session)
        self.assertEqual(self.search('یاسی'), [])

    def test_shared_alias_is_ambiguous_and_filter_and_limit_work(self):
        self.alias(self.fatemeh, 'یاسی')
        self.alias(self.other, 'یاسی')
        self.other.enabled = False
        self.session.commit()
        self.assertEqual(len(self.search('یاسی')), 2)
        self.assertEqual(len(self.search('یاسی', limit=1)), 1)
        self.assertEqual(len(self.search('یاسی', enabled_only=True)), 1)
        self.assertEqual(self.search('Ali Masodi', min_score=100), [])

    def test_alias_survives_ldap_sync(self):
        self.alias(self.fatemeh, 'یاسی')
        data = dict(uid=self.fatemeh.uid, username='renamed', first_name='Fatemeh',
                    last_name='Ahmadi', display_name='New display name', email=None,
                    department=None, title=None, phone=None, distinguished_name='CN=renamed', enabled=True)
        with patch.object(data_service, 'fetch_users', return_value=iter([data])):
            data_service.sync_users(self.session)
        self.assertEqual(self.search('یاسی')[0]['user'].username, 'renamed')


if __name__ == '__main__':
    unittest.main()
