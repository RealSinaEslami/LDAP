import os
import unittest
from unittest.mock import patch
from uuid import UUID

# Tests never read the real LDAP password or use the application's database.
os.environ['LDAP_BIND_PASSWORD'] = 'offline-placeholder'
os.environ['API_KEY'] = 'offline-test-key'
os.environ['DATABASE_URL'] = 'sqlite://'

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from database import Base
from models.data_model import LDAPUser
from routers.data_router import authorize
from schemas.data_schema import DataFromLDAP
from services import data_service as service


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.row = dict(uid='41b6fae1-3c54-4986-8a8e-19d1349e62dc', username='sample',
                        first_name='Al', last_name=None, display_name='Original', email=None,
                        department=None, title=None, phone=None, distinguished_name='CN=sample', enabled=True)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_sync_updates_without_duplicates_and_rolls_back_partial_failure(self):
        with patch.object(service, 'fetch_users', return_value=iter([self.row])):
            self.assertEqual(service.sync_users(self.session)['synced'], 1)
        updated = dict(self.row, display_name='Updated')
        with patch.object(service, 'fetch_users', return_value=iter([updated])):
            service.sync_users(self.session)
        self.assertEqual(len(self.session.scalars(select(LDAPUser)).all()), 1)

        def broken():
            yield dict(self.row, display_name='Must roll back')
            raise RuntimeError('Incomplete LDAP search')

        with patch.object(service, 'fetch_users', side_effect=broken):
            with self.assertRaises(service.SyncFailed):
                service.sync_users(self.session)
        user = self.session.get(LDAPUser, self.row['uid'])
        self.assertEqual(user.display_name, 'Updated')
        self.assertEqual(DataFromLDAP.model_validate(user).first_name, 'Al')

    def test_api_key_and_concurrent_sync(self):
        authorize('offline-test-key')
        with self.assertRaises(HTTPException) as error:
            authorize('invalid')
        self.assertEqual(error.exception.status_code, 401)
        service.sync_lock.acquire()
        try:
            with self.assertRaises(service.SyncInProgress):
                service.sync_users(self.session)
        finally:
            service.sync_lock.release()

    def test_ldap_paging_guid_mapping_and_cleanup(self):
        with patch.object(service, 'Server'), patch.object(service, 'Connection') as factory:
            connection = factory.return_value
            connection.bind.return_value = True
            calls = []

            def search(*args, **kwargs):
                calls.append(kwargs['paged_cookie'])
                connection.response = [{
                    'type': 'searchResEntry', 'dn': 'CN=sample',
                    'attributes': {'givenName': ['Al'], 'sn': [], 'userAccountControl': ['514']},
                    'raw_attributes': {'objectGUID': [UUID(self.row['uid']).bytes_le]},
                }]
                connection.result = {'result': 0, 'controls': {
                    '1.2.840.113556.1.4.319': {'value': {'cookie': b'next' if len(calls) == 1 else b''}}}}

            connection.search.side_effect = search
            results = list(service.fetch_users())
            self.assertEqual(calls, [None, b'next'])
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0]['uid'], self.row['uid'])
            self.assertFalse(results[0]['enabled'])
            self.assertIsNone(results[0]['last_name'])
            connection.unbind.assert_called_once()


if __name__ == '__main__':
    unittest.main()
