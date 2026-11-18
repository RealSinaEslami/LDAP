import secrets
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from config import get_settings
from database import get_db
from models.data_model import LDAPUser, UserAlias
from schemas.data_schema import AliasCreate, AliasOut, DataFromLDAP, SearchHit, SyncResult
from services.data_service import SyncFailed, SyncInProgress, sync_users
from services.name_matching import normalize_name
from services.search_service import search_users

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


@router.get('/users/search', response_model=list[SearchHit])
def search_data(q: str = Query(..., min_length=1, max_length=256),
                limit: int = Query(10, ge=1, le=50),
                min_score: float = Query(70, ge=0, le=100), enabled_only: bool = False,
                session: Session = Depends(get_db)):
    return search_users(session, q, limit, min_score, enabled_only)


@router.get('/users/{uid}', response_model=DataFromLDAP)
def get_user(uid: UUID, session: Session = Depends(get_db)):
    user = session.get(LDAPUser, str(uid))
    if user is None:
        raise HTTPException(404, 'User not found')
    return user


@router.get('/users/{uid}/aliases', response_model=list[AliasOut])
def list_aliases(uid: UUID, session: Session = Depends(get_db)):
    get_user(uid, session)
    return session.scalars(select(UserAlias).where(UserAlias.user_uid == str(uid))
                           .order_by(UserAlias.id)).all()


@router.post('/users/{uid}/aliases', response_model=AliasOut, status_code=201)
def add_alias(uid: UUID, body: AliasCreate, session: Session = Depends(get_db)):
    get_user(uid, session)
    alias = UserAlias(user_uid=str(uid), name=body.name, normalized_name=normalize_name(body.name))
    session.add(alias)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Alias already exists for this user') from None
    session.refresh(alias)
    return alias


@router.delete('/users/{uid}/aliases/{alias_id}', status_code=204)
def delete_alias(uid: UUID, alias_id: int, session: Session = Depends(get_db)):
    alias = session.get(UserAlias, alias_id)
    if alias is None or alias.user_uid != str(uid):
        raise HTTPException(404, 'Alias not found')
    session.delete(alias)
    session.commit()
