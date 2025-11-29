from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional

from app.core.database import get_db_ops
from app.core.security import create_access_token, verify_token
from app.core.config import get_settings
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserResponse
from app.models.user import User


settings = get_settings()
router = APIRouter()

# Defines the "Lock" icon in Swagger UI
# This tells FastAPI that the token can be retrieved from this URL
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"/api/{settings.API_VERSION}/auth/login"
)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_ops)
) -> User:
    """
    Dependency: Validates JWT token and retrieves the current user.
    Used by other endpoints to protect routes.
    """
    # 1. Verify the token signature
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Extract user ID
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
        
    # 3. Check if user exists in DB
    user = UserService.get_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="User not found"
        )
    
    return user

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db_ops)
):
    """
    Register a new account (Citizen, Officer, etc).
    """
    return UserService.create_user(db, user_in)

@router.post("/login")
def login_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_ops)
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = UserService.authenticate(db, email=form_data.username, password=form_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    return {
        "access_token": create_access_token(
            data={"sub": user.userId, "role": user.role},
            expires_delta=access_token_expires
        ),
        "token_type": "bearer",
        "user_id": user.userId,
        "role": user.role,
    }
