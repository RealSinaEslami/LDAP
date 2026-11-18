from datetime import datetime, timezone
import ssl
from threading import Lock
from uuid import UUID
from ldap3 import Connection, NONE, Server, SUBTREE, Tls
from sqlalchemy.orm import Session
from config import get_settings
from models.data_model import LDAPUser

settings = get_settings()
sync_lock = Lock()


class SyncFailed(Exception):
    pass


class SyncInProgress(Exception):
    pass


def fetch_users():
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=settings.ldap_ca_file or None)
    server = Server(settings.ldap_host, port=settings.ldap_port, use_ssl=False,
                    tls=tls, get_info=NONE, connect_timeout=10)
    connection = Connection(server, user=settings.ldap_bind_user,
                            password=settings.ldap_bind_password.get_secret_value(),
                            raise_exceptions=True, receive_timeout=30, auto_referrals=False)
    attributes = ['objectGUID', 'givenName', 'sn', 'sAMAccountName', 'displayName', 'mail',
                  'department', 'title', 'telephoneNumber', 'userAccountControl']
    try:
        connection.open()
        if settings.ldap_start_tls and not connection.start_tls():
            raise RuntimeError('StartTLS failed')
        if not connection.bind():
            raise RuntimeError('LDAP bind failed')
        cookie = None
        while True:
            connection.search(settings.ldap_search_base,
                              '(&(objectCategory=person)(objectClass=user))',
                              search_scope=SUBTREE, attributes=attributes,
                              paged_size=500, paged_cookie=cookie)
            if connection.result.get('result') != 0:
                raise RuntimeError('LDAP search failed')
            for entry in connection.response:
                if entry['type'] != 'searchResEntry':
                    raise RuntimeError('Unexpected LDAP response or referral')
                values = entry['attributes']

                def value(name):
                    item = values.get(name)
                    return (item[0] if item else None) if isinstance(item, list) else item

                raw_guid = entry['raw_attributes'].get('objectGUID', [])
                if not raw_guid or value('userAccountControl') is None:
                    raise RuntimeError('Required LDAP attributes missing')
                yield dict(
                    uid=str(UUID(bytes_le=raw_guid[0])), username=value('sAMAccountName'),
                    first_name=value('givenName'), last_name=value('sn'), display_name=value('displayName'), email=value('mail'),
                    department=value('department'), title=value('title'),
                    phone=value('telephoneNumber'), distinguished_name=entry['dn'],
                    enabled=not bool(int(value('userAccountControl')) & 2),
                )
            control = connection.result.get('controls', {}).get('1.2.840.113556.1.4.319')
            if control is None:
                raise RuntimeError('Server did not confirm paged results')
            cookie = control['value']['cookie']
            if not cookie:
                break
    finally:
        connection.unbind()


def sync_users(session: Session):
    if not sync_lock.acquire(blocking=False):
        raise SyncInProgress('A sync is already running')
    try:
        count = 0
        now = datetime.now(timezone.utc)
        for data in fetch_users():
            user = session.get(LDAPUser, data['uid'])
            if user is None:
                user = LDAPUser(**data, last_seen_at=now)
                session.add(user)
            else:
                for name, value in data.items():
                    setattr(user, name, value)
                user.last_seen_at = now
            count += 1
        session.commit()
        return {'synced': count, 'synced_at': now}
    except Exception:
        session.rollback()
        # Do not expose credentials, LDAP responses, or database errors to clients.
        raise SyncFailed('Sync failed; check LDAP access, TLS, credentials and database') from None
    finally:
        sync_lock.release()
