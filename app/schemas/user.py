from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, List
from datetime import datetime

from enum import Enum




class UserListResponse(BaseModel):
    """Schema for listing users (admin view)"""
    user_id: str
    email: Optional[str]
    phone_number: Optional[str]
    role: str
    is_anonymous: bool
    created_at: datetime
    hashed_device_id: Optional[str]
    password_hash: Optional[str]  # Careful with this - maybe don't expose!


class UserDemographicResponse(BaseModel):
    """Response for demographic breakdown"""
    role: str
    is_anonymous: bool
    account_age_segment: str
    user_count: int

    class Config:
        from_attributes = True

class UserRole(str, Enum):
    CITIZEN = "citizen"
    OFFICER = "officer"
    ADMIN = "admin"

# Base shared properties
class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    phoneNumber: Optional[str] = Field(None, pattern=r'^\+?[1-9]\d{1,14}$')
    role: UserRole = UserRole.CITIZEN
    hashedDeviceId: Optional[str] = None  # Added for Anonymous Reporting

# Registration Input (For creating new registered users)
class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="Required for Officers/Admins")

# Login Input
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Role Update Input (For Admin dashboard)
class UserRoleUpdate(BaseModel):
    role: UserRole

# Output Response (Sanitized - No Passwords)
class UserResponse(UserBase):
    userId: str
    isAnonymous: bool
    createdAt: datetime
    
    class Config:
        from_attributes = True

# Profile Update Input
class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    phoneNumber: Optional[str] = None