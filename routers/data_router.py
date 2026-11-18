import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session
from config import get_settings
from database import get_db
from models.data_model import LDAPUser
from schemas.data_schema import DataFromLDAP, SyncResult
from services.data_service import SyncFailed, SyncInProgress, sync_users

key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


def authorize(key: str | None = Depends(key_header)):
    expected = get_settings().api_key.get_secret_value()
    if key is None or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(401, 'Invalid API key')


router = APIRouter(prefix='/data', tags=['LDAP users'], dependencies=[Depends(authorize)])


@router.post('/sync', response_model=SyncResult)
def sync_data(session: Session = Depends(get_db)):
    try:
        return sync_users(session)
    except SyncInProgress as error:
        raise HTTPException(409, str(error)) from None
    except SyncFailed as error:
        raise HTTPException(502, str(error)) from None


@router.get('/users', response_model=list[DataFromLDAP])
def list_users(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
               q: str | None = Query(None, max_length=256), session: Session = Depends(get_db)):
    statement = select(LDAPUser)
    if q:
        statement = statement.where(LDAPUser.username.contains(q, autoescape=True))
    return session.scalars(statement.order_by(LDAPUser.uid).offset(offset).limit(limit)).all()


@router.get('/users/{uid}', response_model=DataFromLDAP)
def get_user(uid: UUID, session: Session = Depends(get_db)):
    user = session.get(LDAPUser, str(uid))
    if user is None:
        raise HTTPException(404, 'User not found')
    return user
