from sqlalchemy.orm import Session
from sqlalchemy import func , extract , case , text

from fastapi import HTTPException, status
from typing import Optional , List , Dict, Tuple
import uuid

# Models & Schemas
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserRole

# Security Utilities (Already defined in app/core/security.py)
from app.core.security import hash_password, verify_password

class UserService:
    """
    Handles User Management: Registration, Authentication, Roles.
    """

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_by_id(db: Session, user_id: str) -> Optional[User]:
        return db.query(User).filter(User.userId == user_id).first()

    @staticmethod
    def create_user(db: Session, user_in: UserCreate) -> User:
        """Register a new user with a hashed password."""
        
        # 1. Check if email exists
        if user_in.email:
            existing_user = UserService.get_by_email(db, user_in.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

        # 2. Hash the password
        hashed_pwd = hash_password(user_in.password)

        # 3. Create User Record
        db_user = User(
            userId=f"user-{uuid.uuid4()}",
            email=user_in.email,
            phoneNumber=user_in.phoneNumber,
            passwordHash=hashed_pwd,
            role=user_in.role.value,  # Default is usually citizen
            isAnonymous=False
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return db_user

    @staticmethod
    def authenticate(db: Session, email: str, password: str) -> Optional[User]:
        """Verify email and password."""
        user = UserService.get_by_email(db, email)
        if not user:
            return None
        if not user.passwordHash:
            return None # User exists but has no password (maybe OTP user)
            
        if not verify_password(password, user.passwordHash):
            return None
            
        return user

    @staticmethod
    def update_role(db: Session, user_id: str, role_data: UserUpdate) -> User:
        """Promote or Demote a user (Admin only logic)."""
        user = UserService.get_by_id(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        user.role = role_data.role.value
        db.commit()
        db.refresh(user)
        return user

    
    # @staticmethod
    # def get_user_demographic_breakdown(db: Session) -> List[Tuple]:
    #     """Returns (role, is_anonymous, account_age_segment, user_count) for dashboard."""

    #     # SQLAlchemy 2.0 syntax - use positional arguments, not a list
    #     age_in_days = func.datediff(text('day'), User.createdAt, func.now())

    #     age_segment = case(
    #         (age_in_days <= 30, 'New (< 30 days)'),
    #         (age_in_days <= 90, 'Active (1-3 months)'),
    #         (age_in_days <= 365, 'Established (3-12 months)'),
    #         else_='Long-term (> 1 year)'
    #     ).label('account_age_segment')

    #     return db.query(
    #         User.role,
    #         User.isAnonymous,
    #         age_segment,
    #         func.count(User.userId).label('user_count')
    #     ).group_by(
    #         User.role,
    #         User.isAnonymous,
    #         age_segment
    #     ).order_by(
    #         User.role,
    #         User.isAnonymous,
    #         age_segment
    #     ).all()


    @staticmethod
    def get_all_users_list(db: Session):
        """Returns (userId, email, phoneNumber, role, isAnonymous, createdAt) for all users."""
        return db.query(
            User.userId,
            User.email,
            User.phoneNumber,
            User.role,
            User.createdAt,
        ).order_by(
            User.createdAt.desc()
        ).all()
