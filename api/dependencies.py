from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional

from config import Settings, get_settings
from services.db import get_db_connection
from services.users_service import get_user_by_id

import snowflake.connector


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_app_settings() -> Settings:
    return get_settings()


def get_db() -> snowflake.connector.SnowflakeConnection:
    """
    FastAPI dependency that provides a request-scoped database connection.
    Use this in route handlers to get a connection that will be reused for all DB calls in that request.
    """
    return Depends(get_db_connection)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection)
) -> dict:
    """
    FastAPI dependency that verifies JWT token and returns current user.
    Use this in route handlers to protect endpoints.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        settings = get_settings()
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        
        if user_id is None or email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Fetch user from database to ensure they still exist
    user = get_user_by_id(user_id, conn=conn)
    if user is None:
        raise credentials_exception
    
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role
    }
