from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    UploadFile,
    File,
    Form,
    Request
)
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timezone

# Database
from app.core.database import get_db_ops
from app.api.v1.auth import get_current_user
from app.models.user import User

# Schemas
from app.schemas.report import (
    ReportCreate,
    ReportResponse,
    ReportListResponse,
    ReportStatusUpdate,
    ReportStatus,
    ReportCategory
)
from app.schemas.attachment import AttachmentResponse, FileType

# Models
from app.models.report import Report
from app.models.attachment import Attachment

# Services
from app.services.report_service import ReportService
from app.services.blob_service import BlobStorageService

router = APIRouter()


# ---------------------------------------------------------
# REPORT CRUD
# ---------------------------------------------------------

@router.post(
    "/",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new report"
)
async def create_report(
    request: Request,
    title: str = Form(...),
    user_id: str = Form(...),
    descriptionText: str = Form(...),
    location: str = Form(...),
    categoryId: Optional[ReportCategory] = Form(None),
    isAnonymous: bool = Form(False),
    transcribedVoiceText: Optional[str] = Form(None),
    hashedDeviceId: Optional[str] = Form(None),
    files: List[UploadFile] = File(...), 
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)
):
    """
    Submit a new incident report with file attachments.
    Returns the report with attachments including temporary download URLs.
    """
    
    # 1. Validate: At least one file is required
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required to create a report."
        )

    # 2. Prepare Report Data
    report_data = ReportCreate(
        title=title,
        descriptionText=descriptionText,
        location=location,
        categoryId=categoryId,
        isAnonymous=isAnonymous,
        transcribedVoiceText=transcribedVoiceText,
        hashedDeviceId=hashedDeviceId,
        attachments=[]
    )
    
    # 3. Get base URL for reportUrl
    base_url = str(request.base_url).rstrip('/')
    
    # 4. Create Report with Files
    userid = user_id
    report_response = await ReportService.create_report_with_files(
        db, 
        report_data, 
        files,
        user_id = userid
    )
    
    # 5. Add reportUrl to response
    report_response.reportUrl = f"{base_url}/api/v1/reports/{report_response.reportId}"
    
    return report_response


@router.get(
    "/",
    response_model=ReportListResponse,
    summary="List all reports"
)
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[ReportStatus] = Query(None),
    category: Optional[ReportCategory] = Query(None),
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)

):
    """Get paginated list of reports with their attachments"""
    status_value = status.value if status else None
    category_value = category.value if category else None
    
    return ReportService.list_reports(
        db,
        skip=skip,
        limit=limit,
        status=status_value,
        category=category_value
    )


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get report by ID"
)
def get_report(
    report_id: Optional[str] = None,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)
):
    """Get a single report by its ID with all attachments"""
    report = ReportService.get_report(db, report_id)
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    return report

@router.get(
    "/user/{user_id}",
    response_model = ReportListResponse,
    summary="Get report by user_id"
)
def get_report_by_user(
    user_id :  str,
    db: Session = Depends(get_db_ops),
    skip: int = 0, 
    limit: int = 10,
    status: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get a single report by its ID with all attachments"""
    reports = ReportService.get_report_by_user(db, user_id, skip, limit, status, category)
    
    if not reports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {user_id} not found"
        )
    
    return reports

@router.put(
    "/{report_id}/status",
    response_model=ReportResponse,
    summary="Update report status"
)
def update_report_status(
    report_id: str,
    status_update: ReportStatusUpdate,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)
):
    """Update the status of a report"""
    report = ReportService.update_report_status(db, report_id, status_update)
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    return report


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a report"
)
def delete_report(
    report_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)

):
    """Delete a report permanently along with its attachments"""
    success = ReportService.delete_report(db, report_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    return None


# ---------------------------------------------------------
# ATTACHMENTS
# ---------------------------------------------------------

@router.get(
    "/{report_id}/attachments",
    response_model=List[AttachmentResponse],
    summary="Get all attachments for a report"
)
def get_report_attachments(
    report_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)

):
    """Get all attachments associated with a report with temporary download URLs"""
    # Verify report exists
    report = db.query(Report).filter(Report.reportId == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    # Get attachments
    attachments = db.query(Attachment).filter(Attachment.reportId == report_id).all()
    
    # Generate download URLs
    blob_service = BlobStorageService()
    results = []
    
    for attachment in attachments:
        download_url = blob_service.generate_download_url(attachment.blobStorageUri)
        results.append(
            AttachmentResponse(
                attachmentId=attachment.attachmentId,
                reportId=attachment.reportId,
                blobStorageUri=attachment.blobStorageUri,
                downloadUrl=download_url,
                mimeType=attachment.mimeType,
                fileType=attachment.fileType,
                fileSizeBytes=attachment.fileSizeBytes,
                createdAt=datetime.now(timezone.utc)  # Manual timestamp
            )
        )
    
    return results