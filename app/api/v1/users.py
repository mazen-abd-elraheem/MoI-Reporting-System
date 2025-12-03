from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict

from app.core.database import get_db_ops

# Auth & Security
from app.api.v1.auth import (
    get_current_user,
    require_admin,
    RequireAuthority
)
from app.core.security import Authority, UserRole, check_authority

from app.services.user_service import UserService
from app.models.user import User
from app.schemas.user import (
    UserResponse,
    UserRoleUpdate,
    UserRole as UserRoleEnum,
    UserDemographicResponse,
    UserListResponse
)

router = APIRouter()


# ============================================================================
# USER MANAGEMENT - ADMIN ONLY
# ============================================================================

@router.put("/{user_id}/role", response_model=UserResponse)
def assign_role(
    user_id: str,
    role_data: UserRoleUpdate,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(require_admin)  # ← ADMIN ONLY
):
    """
    Assign or update a user's role (e.g., promote Citizen to Officer).
    
    **Access:** ADMIN only
    **Authority:** USER_UPDATE
    
    **Business Rules:**
    - Only admins can change roles
    - Admins cannot demote themselves
    - Role changes are logged for audit
    """
    
    # 1. Verify admin authority
    check_authority(current_user.role, Authority.USER_UPDATE)
    
    # 2. Prevent admin from demoting themselves (safety check)
    if user_id == current_user.userId:
        if role_data.role != UserRoleEnum.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot demote yourself. Ask another admin to do this."
            )
    
    # 3. Verify target user exists
    target_user = UserService.get_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # 4. Log the role change for audit
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"AUDIT: Admin {current_user.userId} changing role of user {user_id} "
        f"from {target_user.role} to {role_data.role.value}"
    )
    
    # 5. Update role
    updated_user = UserService.update_role(db, user_id, role_data)
    
    return updated_user


@router.get(
    "/list",
    summary="Get all users list"
)
def get_all_users_list(
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(RequireAuthority(Authority.USER_LIST_ALL))  # ← Admin/Supervisor
):
    """
    Get list of all users in the system.
    
    **Access:** ADMIN, SUPERVISOR
    **Authority:** USER_LIST_ALL
    
    **Filtering:**
    - Supervisors see only users in their organization (tenant_id)
    - Admins see all users
    """
    
    try:
        # Apply tenant filtering for supervisors
        tenant_filter = None
        if current_user.role == UserRole.SUPERVISOR.value:
            tenant_filter = getattr(current_user, 'tenant_id', None)
        
        # Get users from service
        rows = UserService.get_all_users_list(db, tenant_id=tenant_filter)

        # Convert to response format
        data = [
            {
                "user_id": row.userId,
                "email": row.email,
                "phone_number": row.phoneNumber,
                "role": row.role,
                "is_anonymous": row.isAnonymous,
                "created_at": row.createdAt,
            }
            for row in rows
        ]

        return {
            "users": data,
            "total": len(data),
            "filtered_by_tenant": tenant_filter is not None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get users list: {str(e)}"
        )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID"
)
def get_user(
    user_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Get detailed information about a specific user.
    
    **Access Control:**
    - Users can always view their own profile
    - ADMIN/SUPERVISOR: Can view any user in their scope
    - OFFICER: Cannot view other users (unless it's themselves)
    """
    
    # Users can always view their own profile
    if user_id == current_user.userId:
        return current_user
    
    # Check if user has authority to view other users
    if current_user.role == UserRole.CITIZEN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your own profile"
        )
    
    if current_user.role == UserRole.OFFICER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officers can only view their own profile"
        )
    
    # Admin and Supervisor can view other users
    check_authority(current_user.role, Authority.USER_READ)
    
    # Fetch target user
    target_user = UserService.get_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Supervisors can only view users in their organization
    if current_user.role == UserRole.SUPERVISOR.value:
        if hasattr(current_user, 'tenant_id') and hasattr(target_user, 'tenant_id'):
            if current_user.tenant_id != target_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only view users in your organization"
                )
    
    return target_user


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user information"
)
def update_user(
    user_id: str,
    update_data: dict,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Update user information.
    
    **Access Control:**
    - Users can update their own basic profile (limited fields)
    - ADMIN: Can update any user's information (all fields)
    - OFFICER/SUPERVISOR: Can only update their own profile
    """
    
    # Fetch target user
    target_user = UserService.get_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Users updating their own profile
    if user_id == current_user.userId:
        # Allow limited fields for self-update
        allowed_self_update_fields = [
            "email",
            "phoneNumber",
            "hashedDeviceId"
        ]
        
        # Filter update_data to only allowed fields
        filtered_data = {
            k: v for k, v in update_data.items()
            if k in allowed_self_update_fields
        }
        
        if not filtered_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid fields to update. Allowed: {allowed_self_update_fields}"
            )
        
        update_data = filtered_data
    
    else:
        # Updating someone else's profile - requires admin
        if current_user.role != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can update other users' information"
            )
        
        check_authority(current_user.role, Authority.USER_UPDATE)
        
        # Admin can update all fields except role (use dedicated endpoint)
        if "role" in update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use the /users/{user_id}/role endpoint to change roles"
            )
    
    # Update user
    updated_user = UserService.update(db, user_id, update_data)
    
    # Log audit trail
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"AUDIT: User {current_user.userId} updated user {user_id}. "
        f"Fields: {list(update_data.keys())}"
    )
    
    return updated_user


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user"
)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(require_admin)  # ← ADMIN ONLY
):
    """
    Delete a user permanently.
    
    **Access:** ADMIN only
    **Authority:** USER_DELETE
    
    **Business Rules:**
    - Only admins can delete users
    - Users cannot delete themselves
    - Deletion is logged for audit
    """
    
    # Check authority
    check_authority(current_user.role, Authority.USER_DELETE)
    
    # Prevent self-deletion
    if user_id == current_user.userId:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account. Ask another admin to do this."
        )
    
    # Verify user exists
    target_user = UserService.get_by_id(db, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found"
        )
    
    # Log deletion for audit
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(
        f"AUDIT: Admin {current_user.userId} DELETING user {user_id} "
        f"(role: {target_user.role}, email: {target_user.email})"
    )
    
    # Delete user
    success = UserService.delete(db, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )
    
    return None


# ============================================================================
# USER STATISTICS (Optional - for dashboard)
# ============================================================================

@router.get(
    "/stats/demographics",
    response_model=List[UserDemographicResponse],
    summary="Get user demographic breakdown"
)
def get_user_demographic_breakdown(
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(RequireAuthority(Authority.ANALYTICS_VIEW))  # ← Admin/Supervisor
):
    """
    Get user breakdown by role, anonymity status, and account age segments.
    This data helps understand user composition and growth patterns.
    
    **Access:** ADMIN, SUPERVISOR (with analytics authority)
    """
    
    try:
        # Apply tenant filtering for supervisors
        tenant_filter = None
        if current_user.role == UserRole.SUPERVISOR.value:
            tenant_filter = getattr(current_user, 'tenant_id', None)
        
        rows = UserService.get_user_demographic_breakdown(db, tenant_id=tenant_filter)

        data = [
            UserDemographicResponse(
                role=row.role,
                is_anonymous=row.isAnonymous,
                account_age_segment=row.account_age_segment,
                user_count=row.user_count
            )
            for row in rows
        ]

        return data
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user demographic breakdown: {str(e)}"
        )


@router.get(
    "/stats/summary",
    summary="Get user statistics summary"
)
def get_user_stats_summary(
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(RequireAuthority(Authority.ANALYTICS_VIEW))  # ← Admin/Supervisor
):
    """
    Get high-level user statistics.
    
    **Access:** ADMIN, SUPERVISOR
    """
    
    try:
        # Apply tenant filtering for supervisors
        tenant_filter = None
        if current_user.role == UserRole.SUPERVISOR.value:
            tenant_filter = getattr(current_user, 'tenant_id', None)
        
        stats = UserService.get_user_stats(db, tenant_id=tenant_filter)
        
        return {
            "total_users": stats.get("total_users", 0),
            "by_role": stats.get("by_role", {}),
            "anonymous_users": stats.get("anonymous_users", 0),
            "active_users_30d": stats.get("active_users_30d", 0),
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get user stats: {str(e)}"
        )