from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


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
