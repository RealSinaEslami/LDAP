from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.name_matching import normalize_name


class DataFromLDAP(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    uid: UUID
    first_name: str | None
    last_name: str | None
    username: str | None
    display_name: str | None
    email: str | None
    department: str | None
    title: str | None
    phone: str | None
    distinguished_name: str
    enabled: bool
    last_seen_at: datetime


class SyncResult(BaseModel):
    synced: int
    synced_at: datetime


class AliasCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)

    @field_validator('name')
    @classmethod
    def meaningful_name(cls, value):
        if not normalize_name(value):
            raise ValueError('Name must contain letters or numbers')
        return value.strip()


class AliasOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_uid: UUID
    name: str


class SearchHit(BaseModel):
    user: DataFromLDAP
    score: float
    matched_name: str
    matched_field: str
    match_type: str
