from sqlalchemy import Column, String, Boolean, DateTime, func, CheckConstraint
from sqlalchemy.orm import relationship

from app.core.database import BaseOps


class User(BaseOps):
    """
    User model with enhanced security fields for role-based access control
    and multi-tenancy support.
    """
    
    __tablename__ = "User"
    __table_args__ = (
        CheckConstraint(
            "(isAnonymous = 1) OR (email IS NOT NULL) OR (phoneNumber IS NOT NULL)",
            name="CK_User_ContactInfo"
        ),
        {'schema': 'dbo'}
    )

    # ============================================================================
    # PRIMARY KEY
    # ============================================================================
    userId = Column("userId", String(450), primary_key=True, index=True)
    
    # ============================================================================
    # AUTHENTICATION & SECURITY
    # ============================================================================
    passwordHash = Column("passwordHash", String(256), nullable=True)
    
    # Role-based access control
    role = Column("role", String(50), nullable=False, default="citizen", index=True)
    # Valid roles: "CITIZEN", "OFFICER", "SUPERVISOR", "ADMIN"
    
    is_active = Column("is_active", Boolean, nullable=False, default=True)
    # Set to False to disable account without deleting
    
    # ============================================================================
    # USER INFORMATION
    # ============================================================================
    email = Column("email", String(256), nullable=True, index=True)
    phoneNumber = Column("phoneNumber", String(20), nullable=True)
    
    # Anonymous user support
    isAnonymous = Column("isAnonymous", Boolean, nullable=False, default=False)
    hashedDeviceId = Column("hashedDeviceId", String(256), nullable=True)
    
    # ============================================================================
    # MULTI-TENANCY & DEPARTMENT ISOLATION (Optional but Recommended)
    # ============================================================================
    # Uncomment these if you want tenant/client isolation:
    
    # tenant_id = Column("tenant_id", String(100), nullable=True, index=True)
    # # Organization/Ministry level (e.g., "MoI", "MoH")
    # # Supervisors and below are restricted to their tenant
    
    # client_id = Column("client_id", String(100), nullable=True, index=True)
    # # Department/Branch level (e.g., "Cairo_Police", "Alexandria_Police")
    # # Officers are restricted to their client/department
    
    # ============================================================================
    # TIMESTAMPS
    # ============================================================================
    createdAt = Column("createdAt", DateTime, nullable=False, server_default=func.getutcdate())
    updatedAt = Column("updatedAt", DateTime, nullable=True, onupdate=func.getutcdate())
    lastLoginAt = Column("lastLoginAt", DateTime, nullable=True)
    
    # ============================================================================
    # RELATIONSHIPS
    # ============================================================================
    reports = relationship("Report", back_populates="user")

    # ============================================================================
    # METHODS
    # ============================================================================
    
    def __repr__(self):
        return f"<User(userId={self.userId}, role={self.role}, email={self.email})>"
    
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return self.role.upper() == "ADMIN"
    
    def is_officer_or_above(self) -> bool:
        """Check if user is officer, supervisor, or admin"""
        return self.role.upper() in ["OFFICER", "SUPERVISOR", "ADMIN"]
    
    def can_access_tenant(self, tenant_id: str) -> bool:
        """
        Check if user can access resources in a specific tenant.
        Admins can access all tenants, others are restricted to their own.
        """
        if self.is_admin():
            return True
        
        # If tenant_id field exists, check it
        if hasattr(self, 'tenant_id'):
            return self.tenant_id == tenant_id
        
        return True  # No tenant isolation
    
    def can_access_client(self, client_id: str) -> bool:
        """
        Check if user can access resources in a specific client/department.
        Admins and Supervisors can access all clients, Officers are restricted.
        """
        if self.role.upper() in ["ADMIN", "SUPERVISOR"]:
            return True
        
        # If client_id field exists, check it
        if hasattr(self, 'client_id'):
            return self.client_id == client_id
        
        return True  # No client isolation
