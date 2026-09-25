from __future__ import annotations

from pydantic import Field

from api.schemas.common import ApiModel


class LoginRequest(ApiModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class AccountOut(ApiModel):
    account_id: int
    username: str
    display_name: str
    role: str


class LoginResponse(ApiModel):
    account: AccountOut
