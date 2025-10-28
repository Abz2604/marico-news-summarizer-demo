from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from config import Settings, get_settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_app_settings() -> Settings:
    return get_settings()


def get_current_user(token: str = Depends(oauth2_scheme)):
    """Placeholder auth dependency; to be implemented with JWT verification."""

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
