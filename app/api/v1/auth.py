from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional, List, Callable
import logging
from pydantic import BaseModel, EmailStr
from functools import wraps

from app.core.database import get_db_ops
from app.core.security import (
    create_access_token, 
    create_refresh_token,
    verify_token,
    verify_password_reset_token,
    generate_password_reset_token,
    UserRole,
    Authority,
    check_authority,
    check_resource_ownership,
    check_tenant_access,
    check_client_access,
    has_authority
)
from app.core.config import get_settings
from app.services.user_service import UserService
from app.schemas.user import UserCreate, UserResponse
from app.models.user import User

settings = get_settings()
router = APIRouter()
logger = logging.getLogger(__name__)

# OAuth2 scheme for Swagger UI
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"/api/{settings.API_VERSION}/auth/login"
)


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class TokenResponse(BaseModel):
    """Standard OAuth2 token response"""
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int  # seconds
    user_id: str
    role: str
    authorities: List[str]
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    """Request schema for token refresh"""
    refresh_token: str


class PasswordResetRequest(BaseModel):
    """Request schema for password reset"""
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with token"""
    token: str
    new_password: str


class PasswordChange(BaseModel):
    """Change password for authenticated user"""
    old_password: str
    new_password: str


# ============================================================================
# RATE LIMITING (Simple in-memory - use Redis in production)
# ============================================================================

from collections import defaultdict
from datetime import datetime

login_attempts = defaultdict(list)
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def check_rate_limit(identifier: str) -> None:
    """Check if user has exceeded login attempts"""
    now = datetime.utcnow()
    
    # Clean old attempts
    login_attempts[identifier] = [
        attempt for attempt in login_attempts[identifier]
        if now - attempt < LOCKOUT_DURATION
    ]
    
    if len(login_attempts[identifier]) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {LOCKOUT_DURATION.seconds // 60} minutes."
        )
    
    login_attempts[identifier].append(now)


# ============================================================================
# DEPENDENCIES - USER RETRIEVAL
# ============================================================================

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db_ops)
) -> User:
    """
    Dependency: Validates JWT access token and retrieves current user.
    This is the base dependency that all protected routes should use.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # Verify token (specifically access tokens)
    payload = verify_token(token, expected_type="access")
    if not payload:
        logger.warning("Invalid token provided")
        raise credentials_exception
    
    # Extract user ID from 'sub' claim
    user_id: str = payload.get("sub")
    if user_id is None:
        logger.warning("Token missing 'sub' claim")
        raise credentials_exception
    
    # Fetch user from database
    user = UserService.get_by_id(db, user_id=user_id)
    if not user:
        logger.warning(f"User {user_id} not found in database")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Check if user account is active
    if not getattr(user, 'is_active', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Attach token payload to user for easy access to authorities, tenant_id, etc.
    user._token_payload = payload
    
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Dependency: Ensures user is active"""
    if not getattr(current_user, 'is_active', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


# ============================================================================
# ROLE-BASED DEPENDENCIES
# ============================================================================

class RequireRole:
    """
    Dependency class to require specific roles.
    
    Usage:
        @router.get("/admin-only")
        def admin_route(user: User = Depends(RequireRole([UserRole.ADMIN]))):
            return {"message": "Admin access"}
    """
    def __init__(self, allowed_roles: List[UserRole]):
        self.allowed_roles = [role.value for role in allowed_roles]
    
    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_role = getattr(current_user, 'role', None)
        
        if user_role not in self.allowed_roles:
            logger.warning(
                f"Access denied: User {current_user.userId} with role {user_role} "
                f"attempted to access resource requiring {self.allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(self.allowed_roles)}"
            )
        
        return current_user


class RequireAuthority:
    """
    Dependency class to require specific authority/permission.
    
    Usage:
        @router.get("/users")
        def list_users(user: User = Depends(RequireAuthority(Authority.USER_LIST_ALL))):
            return {"users": [...]}
    """
    def __init__(self, required_authority: Authority):
        self.required_authority = required_authority
    
    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        user_role = getattr(current_user, 'role', None)
        check_authority(user_role, self.required_authority)
        return current_user


# ============================================================================
# CONVENIENCE DEPENDENCIES FOR COMMON ROLE CHECKS
# ============================================================================

async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: Require ADMIN role"""
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def require_officer_or_above(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: Require OFFICER, SUPERVISOR, or ADMIN role"""
    allowed_roles = [UserRole.OFFICER.value, UserRole.SUPERVISOR.value, UserRole.ADMIN.value]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officer access or higher required"
        )
    return current_user


async def require_supervisor_or_above(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: Require SUPERVISOR or ADMIN role"""
    allowed_roles = [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supervisor access or higher required"
        )
    return current_user


# ============================================================================
# HELPER FUNCTIONS FOR ROUTE HANDLERS
# ============================================================================

def verify_resource_access(
    resource_user_id: str,
    current_user: User,
    allow_roles: Optional[List[UserRole]] = None
) -> None:
    """
    Helper to verify user can access a resource.
    Use this in your route handlers for resource-specific checks.
    
    Args:
        resource_user_id: The user ID who owns the resource
        current_user: The current authenticated user
        allow_roles: Additional roles that can access (e.g., [UserRole.ADMIN, UserRole.OFFICER])
    """
    check_resource_ownership(
        resource_user_id=resource_user_id,
        current_user_id=current_user.userId,
        current_user_role=current_user.role,
        allow_roles=allow_roles
    )


def verify_tenant_access(resource_tenant_id: Optional[str], current_user: User) -> None:
    """
    Helper to verify tenant access.
    Use this when resources have tenant/organization isolation.
    """
    user_tenant_id = getattr(current_user, 'tenant_id', None)
    check_tenant_access(resource_tenant_id, user_tenant_id, current_user.role)


def verify_client_access(resource_client_id: Optional[str], current_user: User) -> None:
    """
    Helper to verify client/department access.
    Use this when resources have department isolation.
    """
    user_client_id = getattr(current_user, 'client_id', None)
    check_client_access(resource_client_id, user_client_id, current_user.role)


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_in: UserCreate,
    db: Session = Depends(get_db_ops)
):
    """
    Register a new user account.
    
    Password requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    """
    logger.info(f"Registration attempt for email: {user_in.email}")
    
    # Check if user already exists
    existing_user = UserService.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create user (password validation happens in security.py)
    user = UserService.create_user(db, user_in)
    logger.info(f"User registered successfully: {user.userId}")
    
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    request: Request = None,
    db: Session = Depends(get_db_ops)
):
    """
    OAuth2 compatible login endpoint.
    
    Returns access token and refresh token for authenticated requests.
    Token includes user's authorities for client-side permission checks.
    """
    # Rate limiting based on username (email)
    check_rate_limit(form_data.username)
    
    logger.info(f"Login attempt for email: {form_data.username}")
    
    # Authenticate user
    user = UserService.authenticate(
        db, 
        email=form_data.username, 
        password=form_data.password
    )
    
    if not user:
        logger.warning(f"Failed login attempt for: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is active
    if not getattr(user, 'is_active', True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive. Contact support."
        )
    
    # Clear rate limit on successful login
    if form_data.username in login_attempts:
        del login_attempts[form_data.username]
    
    # Prepare token data with role, tenant_id, client_id
    token_data = {
        "sub": user.userId,
        "role": user.role,
    }
    
    # Add tenant_id if exists
    if hasattr(user, 'tenant_id') and user.tenant_id:
        token_data["tenant_id"] = user.tenant_id
    
    # Add client_id (department) if exists
    if hasattr(user, 'client_id') and user.client_id:
        token_data["client_id"] = user.client_id
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data=token_data,
        expires_delta=access_token_expires
    )
    
    refresh_token = create_refresh_token(data=token_data)
    
    logger.info(f"User logged in successfully: {user.userId}, role: {user.role}")
    
    # Get authorities for response
    from app.core.security import get_user_authorities
    authorities = get_user_authorities(user.role)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user.userId,
        role=user.role,
        authorities=authorities,
        tenant_id=getattr(user, 'tenant_id', None),
        client_id=getattr(user, 'client_id', None)
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(
    refresh_request: RefreshTokenRequest,
    db: Session = Depends(get_db_ops)
):
    """
    Refresh an expired access token using a valid refresh token.
    """
    # Verify refresh token
    payload = verify_token(refresh_request.refresh_token, expected_type="refresh")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    user_id = payload.get("sub")
    role = payload.get("role")
    tenant_id = payload.get("tenant_id")
    client_id = payload.get("client_id")
    
    # Verify user still exists and is active
    user = UserService.get_by_id(db, user_id=user_id)
    if not user or not getattr(user, 'is_active', True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Issue new tokens with same data
    token_data = {
        "sub": user_id,
        "role": role,
    }
    if tenant_id:
        token_data["tenant_id"] = tenant_id
    if client_id:
        token_data["client_id"] = client_id
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_access_token = create_access_token(
        data=token_data,
        expires_delta=access_token_expires
    )
    
    new_refresh_token = create_refresh_token(data=token_data)
    
    logger.info(f"Token refreshed for user: {user_id}")
    
    from app.core.security import get_user_authorities
    authorities = get_user_authorities(role)
    
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user_id=user_id,
        role=role,
        authorities=authorities,
        tenant_id=tenant_id,
        client_id=client_id
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current authenticated user information.
    Useful for frontend to verify token and get user details.
    """
    return current_user


@router.get("/me/authorities")
def get_my_authorities(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user's authorities/permissions.
    Frontend can use this to show/hide UI elements based on permissions.
    """
    from app.core.security import get_user_authorities
    authorities = get_user_authorities(current_user.role)
    
    return {
        "user_id": current_user.userId,
        "role": current_user.role,
        "authorities": authorities,
        "tenant_id": getattr(current_user, 'tenant_id', None),
        "client_id": getattr(current_user, 'client_id', None)
    }


@router.post("/password-reset/request")
def request_password_reset(
    reset_request: PasswordResetRequest,
    db: Session = Depends(get_db_ops)
):
    """
    Request a password reset token (sent via email).
    """
    user = UserService.get_by_email(db, email=reset_request.email)
    
    # For security, always return success even if user doesn't exist
    # This prevents email enumeration attacks
    if user:
        reset_token = generate_password_reset_token(user.userId)
        
        # TODO: Send email with reset token
        # from app.services.notification_service import send_password_reset_email
        # send_password_reset_email(user.email, reset_token)
        
        logger.info(f"Password reset requested for: {user.email}")
    
    return {
        "message": "If the email exists, a password reset link has been sent"
    }


@router.post("/password-reset/confirm")
def confirm_password_reset(
    reset_confirm: PasswordResetConfirm,
    db: Session = Depends(get_db_ops)
):
    """
    Confirm password reset with token and set new password.
    """
    user_id = verify_password_reset_token(reset_confirm.token)
    
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Update password
    user = UserService.get_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    UserService.update_password(db, user, reset_confirm.new_password)
    
    logger.info(f"Password reset completed for user: {user_id}")
    
    return {"message": "Password has been reset successfully"}


@router.post("/change-password")
def change_password(
    password_change: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_ops)
):
    """
    Change password for currently authenticated user.
    """
    # Verify old password
    if not UserService.verify_password(current_user, password_change.old_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Update to new password
    UserService.update_password(db, current_user, password_change.new_password)
    
    logger.info(f"Password changed for user: {current_user.userId}")
    
    return {"message": "Password changed successfully"}


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_active_user)
):
    """
    Logout endpoint (client should discard tokens).
    
    For production: implement token blacklist in Redis.
    """
    logger.info(f"User logged out: {current_user.userId}")
    
    # TODO: Add token to blacklist in Redis
    # redis_client.setex(f"blacklist:{token}", expiry, "1")
    
    return {"message": "Logged out successfully"}


# ============================================================================
# ADMIN-ONLY ENDPOINTS (Examples)
# ============================================================================

@router.get("/admin/roles")
def get_all_roles(
    current_user: User = Depends(require_admin)
):
    """
    Get all available roles and their authorities.
    Admin only.
    """
    from app.core.security import ROLE_AUTHORITIES, UserRole
    
    roles_info = {}
    for role in UserRole:
        authorities = ROLE_AUTHORITIES.get(role, [])
        roles_info[role.value] = {
            "role": role.value,
            "authorities": [auth.value for auth in authorities]
        }
    
    return {"roles": roles_info}


@router.get("/admin/authorities")
def get_all_authorities(
    current_user: User = Depends(require_admin)
):
    """
    Get all available authorities in the system.
    Admin only - useful for permission management UI.
    """
    from app.core.security import Authority
    
    authorities = [
        {
            "value": auth.value,
            "name": auth.name,
            "description": auth.value.replace(":", " - ").replace("_", " ").title()
        }
        for auth in Authority
    ]
    
    return {"authorities": authorities}