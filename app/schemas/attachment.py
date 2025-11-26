from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

class FileType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"

# Schema for INPUT (Client -> Server)
class AttachmentCreate(BaseModel):
    blobStorageUri: str = Field(..., description="URI to the stored blob file.")
    mimeType: str = Field(..., description="MIME type of the file.")
    fileType: str = Field(..., description="Classification of the file (e.g., Image, Video, Document).")
    fileSizeBytes: int = Field(..., gt=0, le=52428800, description="Size of the file in bytes (max 50MB).")

# Schema for OUTPUT (Server -> Client)
class AttachmentResponse(BaseModel):
    attachmentId: str
    reportId: str
    blobStorageUri: str
    downloadUrl: Optional[str] = None  # Temporary SAS URL for downloading
    mimeType: str
    fileType: str
    fileSizeBytes: int
    createdAt: datetime

    class Config:
        from_attributes = True