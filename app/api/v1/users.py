from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from typing import List , Dict
from app.core.database import get_db_ops
from app.api.v1.auth import get_current_user
from app.services.user_service import UserService
from app.models.user import User
from app.schemas.user import UserResponse, UserRoleUpdate, UserRole, UserDemographicResponse , UserListResponse # <--- Changed UserUpdate to UserRoleUpdate

router = APIRouter()

@router.put("/{user_id}/role", response_model=UserResponse)
def assign_role(
    user_id: str,
    role_data: UserRoleUpdate, # <--- This must be UserRoleUpdate to have the 'role' attribute
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)
):
    """
    Assign a role to a user (e.g., promote Citizen to Officer).
    **Requirement:** Requester must be an ADMIN.
    """
    # 1. Enforce RBAC (Role Based Access Control)
    # Admin role check (string or enum comparison)
    if current_user.role != "admin" and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized. Admin privileges required."
        )
    
    # 2. Prevent an Admin from demoting themselves (Safety check)
    if user_id == current_user.userId and role_data.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot demote yourself."
        )

    # 3. Update Role
    return UserService.update_role(db, user_id, role_data)



# @router.get(
# "/dashboard/users/demographic-breakdown",
# response_model=List[UserDemographicResponse],
# summary="Get User Demographic Breakdown for Dashboard")
# def get_user_demographic_breakdown(db: Session = Depends(get_db_ops)):
#     """
#     Get user breakdown by role, anonymity status, and account age segments.
#     This data helps understand user composition and growth patterns.
#     """
#     try:
#         rows = UserService.get_user_demographic_breakdown(db)

#         data = [
#             UserDemographicResponse(
#                 role=row.role,
#                 is_anonymous=row.isAnonymous,
#                 account_age_segment=row.account_age_segment,
#                 user_count=row.user_count
#             )
#             for row in rows
#         ]

#         return data
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Failed to get user demographic breakdown: {str(e)}"
#         )

@router.get(
    "/list",
    summary="Get All Users List"
)
def get_all_users_list(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_ops)
):
    """
    Get list of all users in the system.
    Exact same pattern as cold/hot monthly breakdown endpoints.
    """
    try:
        # Direct call to service method - identical pattern to your analytics
        rows = UserService.get_all_users_list(db)

        # Convert tuples to list of dictionaries - identical to your pattern
        data = [
            {
                "user_id": row.userId,
                "email": row.email,
                "phone_number": row.phoneNumber,
                "role": row.role,
                "created_at": row.createdAt,
            }
            for row in rows
        ]

        return data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get users list: {str(e)}"
        )