import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    roles: list[Literal["owner", "investor", "verifier", "admin"]] | None = None


class AuditLogRead(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict
    request_id: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class NotificationRead(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: datetime | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
