from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
import snowflake.connector

from config import get_settings
from dependencies import get_db_connection, get_current_user
from services.users_service import create_user, get_user_by_email, get_user_password_hash
from passlib.context import CryptContext
from jose import JWTError, jwt


router = APIRouter(prefix="/auth", tags=["auth"])

# Password hashing context
# Configure bcrypt with specific rounds to avoid version detection issues
# Suppress bcrypt version warning by explicitly setting backend
import warnings
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", category=UserWarning, module="passlib")
    pwd_context = CryptContext(
        schemes=["bcrypt"],
        deprecated="auto",
        bcrypt__rounds=12,  # Explicitly set rounds to avoid auto-detection issues
    )


class UserSignup(BaseModel):
    email: EmailStr
    password: str
    display_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    role: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    settings = get_settings()
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_exp_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return encoded_jwt


@router.post("/signup", status_code=201, response_model=Token)
async def signup(
    user_data: UserSignup,
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection)
):
    """Create a new user account."""
    # Check if user already exists
    existing_user = get_user_by_email(user_data.email, conn=conn)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists"
        )
    
    # Hash password and create user
    hashed_password = get_password_hash(user_data.password)
    user = create_user(
        email=user_data.email,
        hashed_password=hashed_password,
        display_name=user_data.display_name,
        conn=conn
    )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role
        }
    )


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn: snowflake.connector.SnowflakeConnection = Depends(get_db_connection)
):
    """Authenticate user and return access token."""
    # OAuth2PasswordRequestForm uses 'username' field, but we use email
    email = form_data.username
    
    # Get user and password hash
    user = get_user_by_email(email, conn=conn)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    password_hash = get_user_password_hash(email, conn=conn)
    if not password_hash or not verify_password(form_data.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.id, "email": user.email})
    
    return Token(
        access_token=access_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role
        }
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: dict = Depends(get_current_user)
):
    """Get current user information."""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        display_name=current_user.get("display_name"),
        role=current_user["role"]
    )

