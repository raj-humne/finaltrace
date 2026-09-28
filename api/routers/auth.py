from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_current_account, get_db
from api.models.identity import Account
from api.schemas.auth import AccountOut, LoginRequest, LoginResponse
from api.security.auth_service import authenticate, create_session, revoke_session
from api.security.exceptions import AccountInactive, AccountLocked, InvalidCredentials
from api.security.passwords import hash_password
from api.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_minutes * 60,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        account = authenticate(db, username=payload.username, password=payload.password)
    except AccountLocked as exc:
        raise HTTPException(
            status_code=423,
            detail=f"account locked, retry in {exc.retry_after_seconds:.0f}s",
        ) from exc
    except AccountInactive as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    raw_token = create_session(db, account)
    _set_session_cookie(response, raw_token)
    return LoginResponse(account=AccountOut.model_validate(account))


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    account: Account = Depends(get_current_account),
    db: Session = Depends(get_db),
) -> None:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        revoke_session(db, raw_token, actor=account.username)
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/me", response_model=AccountOut)
def me(account: Account = Depends(get_current_account)) -> AccountOut:
    return AccountOut.model_validate(account)


@router.post("/_setup_once", status_code=201, include_in_schema=False)
def _setup_once(db: Session = Depends(get_db)) -> dict:
    """TEMPORARY: creates exactly one hardcoded demo account, once, then
    refuses forever. Exists only because this Render free-tier deployment has
    no shell/SSH to run `python -m api.cli create-user`. Remove this route
    after the first successful call.
    """
    if db.scalar(select(Account)) is not None:
        raise HTTPException(status_code=403, detail="setup already completed")

    account = Account(
        username="vishesh",
        display_name="Vishesh",
        role="analyst",
        password_hash=hash_password("123456789100"),
    )
    db.add(account)
    db.commit()
    return {"created": account.username}
