from datetime import datetime
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class LDAPUser(Base):
    __tablename__ = 'ldap_users'
    uid: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str | None] = mapped_column(String(256), index=True)
    first_name: Mapped[str | None] = mapped_column(String(256))
    last_name: Mapped[str | None] = mapped_column(String(256))
    display_name: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(512))
    department: Mapped[str | None] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(128))
    distinguished_name: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool]
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
