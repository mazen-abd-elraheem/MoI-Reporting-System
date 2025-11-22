from sqlalchemy import Column, String, Boolean, DateTime, func, CheckConstraint
from sqlalchemy.orm import relationship

from app.core.database import BaseOps 

class User(BaseOps):
    __tablename__ = "User"
    __table_args__ = (
        CheckConstraint(
            "(isAnonymous = 1) OR (email IS NOT NULL) OR (phoneNumber IS NOT NULL)",
            name="CK_User_ContactInfo"
        ),
        {'schema': 'dbo'}
    )

    # Primary Key
    userId = Column("userId", String(450), primary_key=True, index=True)
    
    # Attributes
    isAnonymous = Column("isAnonymous", Boolean, nullable=False, default=False)
    createdAt = Column("createdAt", DateTime, nullable=False, server_default=func.getutcdate())
    role = Column("role", String(50), nullable=False, default="citizen")
    
    email = Column("email", String(256), nullable=True)
    phoneNumber = Column("phoneNumber", String(20), nullable=True)
    hashedDeviceId = Column("hashedDeviceId", String(256), nullable=True)

    # Relationships
    reports = relationship("Report", back_populates="user")

    def __repr__(self):
        return f"<User(userId={self.userId}, role={self.role})>"