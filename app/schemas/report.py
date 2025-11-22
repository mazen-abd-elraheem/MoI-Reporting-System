from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


class AttachmentCreate(BaseModel):
    blobStorageUri: str = Field(..., description="URI to the stored blob file.")
    mimeType: str = Field(..., description="MIME type of the file.")
    fileType: str = Field(..., description="Classification of the file (e.g., Image, Video, Document).")
    fileSizeBytes: int = Field(..., description="Size of the file in bytes.")
    
class AttachmentResponse(AttachmentCreate):
    attachmentId: str
    reportId: str

# Enums must match your SQL constraints exactly
class ReportStatus(str, Enum):
    SUBMITTED = "Submitted"
    ASSIGNED = "Assigned"
    IN_PROGRESS = "InProgress"
    RESOLVED = "Resolved"
    REJECTED = "Rejected"

class ReportCategory(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    UTILITIES = "utilities"
    CRIME = "crime"
    TRAFFIC = "traffic"
    PUBLIC_NUISANCE = "public_nuisance"
    ENVIRONMENTAL = "environmental"
    OTHER = "other"

# Base schema with common fields (using ORM snake_case mapping)
class ReportBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=500)
    descriptionText: str = Field(..., min_length=10)
    
    # Optional in Base because AI might fill it later, 
    # but usually required for display.
    categoryId: Optional[ReportCategory] = None 
    
    # Configuration for camelCase in/out and ORM compatibility
    model_config = ConfigDict(
        alias_generator=lambda field_name: field_name, # Not using alias generator here
        populate_by_name=True,
        from_attributes=True
    )

# Schema for CREATING a report (Input)
class ReportCreate(ReportBase):
    location: str = Field(..., description="Physical address, landmark, or Google Maps link")
    
    transcribedVoiceText: Optional[str] = None
    
    isAnonymous: bool = Field(False, description="True if user wants to remain anonymous")
    hashedDeviceId: Optional[str] = Field(None, description="Required if isAnonymous=True for tracking")
    
    # Nested Attachments: Client sends list of file metadata with the report
    attachments: List[AttachmentCreate] = []

# Schema for UPDATING a report (General Input)
class ReportUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=500)
    descriptionText: Optional[str] = Field(None, min_length=10)
    status: Optional[ReportStatus] = None
    categoryId: Optional[ReportCategory] = None
    location: Optional[str] = None 

# --- NEW: Schema for STATUS ONLY updates (Required by your API) ---
class ReportStatusUpdate(BaseModel):
    status: ReportStatus
    notes: Optional[str] = None # For admin notes/resolution details

# Schema for READING a report (Output)
class ReportResponse(ReportBase):
    # Field names explicitly defined as camelCase for JSON output
    reportId: str
    status: ReportStatus
    location: str  # Matches [locationRaw] in DB
    aiConfidence: Optional[float] = None
    createdAt: datetime
    updatedAt: datetime
    userId: Optional[str] = None
    transcribedVoiceText: Optional[str] = None
    
    # Returns full attachment objects
    attachments: List[AttachmentResponse] = []

    model_config = ConfigDict(
        from_attributes = True,
        # Configure Pydantic to map snake_case ORM attributes to camelCase response fields
        alias_generator=lambda field_name: {
            "report_id": "reportId",
            "category_id": "categoryId",
            "location_raw": "location",
            "created_at": "createdAt",
            "updated_at": "updatedAt",
            "user_id": "userId",
            "description_text": "descriptionText",
            "ai_confidence": "aiConfidence",
            "transcribed_voice_text": "transcribedVoiceText",
            "hashed_device_id": "hashedDeviceId",
        }.get(field_name, field_name),
        populate_by_name=True
    )

# --- NEW: Schema for LIST responses ---
class ReportListResponse(BaseModel):
    reports: List[ReportResponse]
    total: int
    page: int
    pageSize: int
    totalPages: int