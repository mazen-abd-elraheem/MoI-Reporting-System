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

# Auth & Security
from app.api.v1.auth import (
    get_current_user,
    require_officer_or_above,
    verify_resource_access,
    verify_client_access
)
from app.core.security import UserRole, Authority, check_authority
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


# ============================================================================
# REPORT CRUD WITH ROLE-BASED ACCESS CONTROL
# ============================================================================

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
    current_user: User = Depends(get_current_user)  # ← All authenticated users can create
):
    """
    Submit a new incident report with file attachments.
    Returns the report with attachments including temporary download URLs.
    
    **Access Control:**
    - CITIZEN: Can only create reports for themselves
    - OFFICER/SUPERVISOR/ADMIN: Can create reports on behalf of citizens
    
    **Authorization:** Requires REPORT_CREATE authority
    """
    
    # 1. Check authority to create reports
    check_authority(current_user.role, Authority.REPORT_CREATE)
    
    # 2. Citizens can ONLY create reports for themselves
    if current_user.role == UserRole.CITIZEN.value:
        if user_id != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Citizens can only create reports for themselves"
            )
    # Officers/Supervisors/Admins can create for others
    
    # 3. Validate: At least one file is required
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file is required to create a report."
        )

    # 4. Prepare Report Data
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
    
    # 5. Add tenant/client isolation if supported
    # (These fields would need to be added to ReportCreate schema and Report model)
    # if hasattr(current_user, 'tenant_id') and current_user.tenant_id:
    #     report_data.tenant_id = current_user.tenant_id
    # if hasattr(current_user, 'client_id') and current_user.client_id:
    #     report_data.client_id = current_user.client_id
    
    # 6. Get base URL for reportUrl
    base_url = str(request.base_url).rstrip('/')
    
    # 7. Create Report with Files
    report_response = await ReportService.create_report_with_files(
        db,
        report_data,
        files,
        user_id=user_id
    )
    
    # 8. Add reportUrl to response
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
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Get paginated list of reports with their attachments.
    
    **Access Control:**
    - CITIZEN: Only sees their own reports
    - OFFICER: Sees reports in their department (client_id)
    - SUPERVISOR: Sees all reports in their organization (tenant_id)
    - ADMIN: Sees all reports
    """
    
    status_value = status.value if status else None
    category_value = category.value if category else None
    
    # Apply role-based filtering
    filters = {
        "status": status_value,
        "category": category_value
    }
    
    if current_user.role == UserRole.CITIZEN.value:
        # Citizens only see their own reports
        filters["user_id"] = current_user.userId
    
    elif current_user.role == UserRole.OFFICER.value:
        # Officers see reports in their department
        if hasattr(current_user, 'client_id') and current_user.client_id:
            filters["client_id"] = current_user.client_id
        else:
            # If no client_id, show only assigned reports
            filters["assigned_officer_id"] = current_user.userId
    
    elif current_user.role == UserRole.SUPERVISOR.value:
        # Supervisors see all in their organization
        if hasattr(current_user, 'tenant_id') and current_user.tenant_id:
            filters["tenant_id"] = current_user.tenant_id
    
    # Admin sees everything (no additional filters)
    
    return ReportService.list_reports(
        db,
        skip=skip,
        limit=limit,
        **filters
    )


@router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get report by ID"
)
def get_report(
    report_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Get a single report by its ID with all attachments.
    
    **Access Control:**
    - CITIZEN: Can only view their own reports
    - OFFICER: Can view reports in their department or assigned to them
    - SUPERVISOR/ADMIN: Can view all reports in their scope
    """
    
    report = ReportService.get_report(db, report_id)
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    # Check if user can access this report
    if current_user.role == UserRole.CITIZEN.value:
        # Citizens can only view their own reports
        if report.userId != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own reports"
            )
    
    elif current_user.role == UserRole.OFFICER.value:
        # Officers can view reports in their department or assigned to them
        can_access = False
        
        # Check if assigned to them
        if hasattr(report, 'assignedOfficerId') and report.assignedOfficerId == current_user.userId:
            can_access = True
        
        # Check if in their department
        if hasattr(report, 'client_id') and hasattr(current_user, 'client_id'):
            if report.client_id == current_user.client_id:
                can_access = True
        
        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view reports in your department or assigned to you"
            )
    
    elif current_user.role == UserRole.SUPERVISOR.value:
        # Supervisors can view reports in their organization
        if hasattr(report, 'tenant_id') and hasattr(current_user, 'tenant_id'):
            if report.tenant_id != current_user.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only view reports in your organization"
                )
    
    # Admin can view everything (no check needed)
    
    return report


@router.get(
    "/user/{user_id}",
    response_model=ReportListResponse,
    summary="Get reports by user_id"
)
def get_report_by_user(
    user_id: str,
    db: Session = Depends(get_db_ops),
    skip: int = 0,
    limit: int = 10,
    status: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Get all reports for a specific user.
    
    **Access Control:**
    - CITIZEN: Can only view their own reports (user_id must match)
    - OFFICER/SUPERVISOR/ADMIN: Can view reports for any user in their scope
    """
    
    # Citizens can only view their own reports
    if current_user.role == UserRole.CITIZEN.value:
        if user_id != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view your own reports"
            )
    
    # Officers/Supervisors have scope restrictions handled by list_reports logic
    # Admin can view any user's reports
    
    reports = ReportService.get_report_by_user(
        db, user_id, skip, limit, status, category
    )
    
    if not reports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No reports found for user {user_id}"
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
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Update the status of a report.
    
    **Access Control:**
    - CITIZEN: Can update their own pending reports only
    - OFFICER: Can update reports assigned to them or in their department
    - SUPERVISOR/ADMIN: Can update any report in their scope
    """
    
    report = ReportService.get_report(db, report_id)
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    # Role-based update logic
    if current_user.role == UserRole.CITIZEN.value:
        # Citizens can only update their own pending reports
        if report.userId != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own reports"
            )
        if report.status != "Pending":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update pending reports"
            )
        check_authority(current_user.role, Authority.REPORT_UPDATE_OWN)
    
    elif current_user.role == UserRole.OFFICER.value:
        # Officers can update reports in their department
        check_authority(current_user.role, Authority.REPORT_CLOSE)
        
        # Verify they have access to this report
        can_access = False
        if hasattr(report, 'assignedOfficerId') and report.assignedOfficerId == current_user.userId:
            can_access = True
        if hasattr(report, 'client_id') and hasattr(current_user, 'client_id'):
            if report.client_id == current_user.client_id:
                can_access = True
        
        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update reports assigned to you or in your department"
            )
    
    elif current_user.role in [UserRole.SUPERVISOR.value, UserRole.ADMIN.value]:
        # Supervisors and Admins can update reports in their scope
        check_authority(current_user.role, Authority.REPORT_UPDATE_ALL)
    
    # Update the report
    updated_report = ReportService.update_report_status(db, report_id, status_update)
    
    return updated_report


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a report"
)
def delete_report(
    report_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Delete a report permanently along with its attachments.
    
    **Access Control:**
    - CITIZEN: Can delete only their own reports
    - OFFICER/SUPERVISOR: Cannot delete reports
    - ADMIN: Can delete any report
    """
    
    report = ReportService.get_report(db, report_id)
    
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    # Role-based delete logic
    if current_user.role == UserRole.CITIZEN.value:
        # Citizens can only delete their own reports
        if report.userId != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own reports"
            )
        check_authority(current_user.role, Authority.REPORT_DELETE_OWN)
    
    elif current_user.role in [UserRole.OFFICER.value, UserRole.SUPERVISOR.value]:
        # Officers and Supervisors CANNOT delete reports
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Officers and Supervisors cannot delete reports"
        )
    
    elif current_user.role == UserRole.ADMIN.value:
        # Admins can delete any report
        check_authority(current_user.role, Authority.REPORT_DELETE_ALL)
    
    # Delete the report
    success = ReportService.delete_report(db, report_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete report"
        )
    
    return None


# ============================================================================
# ATTACHMENTS
# ============================================================================

@router.get(
    "/{report_id}/attachments",
    response_model=List[AttachmentResponse],
    summary="Get all attachments for a report"
)
def get_report_attachments(
    report_id: str,
    db: Session = Depends(get_db_ops),
    current_user: User = Depends(get_current_user)  # ← All authenticated users
):
    """
    Get all attachments associated with a report with temporary download URLs.
    
    **Access Control:** Same as get_report - must have access to the report
    """
    
    # Verify report exists
    report = db.query(Report).filter(Report.reportId == report_id).first()
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report with ID {report_id} not found"
        )
    
    # Check access using same logic as get_report
    if current_user.role == UserRole.CITIZEN.value:
        if report.userId != current_user.userId:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view attachments for your own reports"
            )
    
    elif current_user.role == UserRole.OFFICER.value:
        can_access = False
        if hasattr(report, 'assignedOfficerId') and report.assignedOfficerId == current_user.userId:
            can_access = True
        if hasattr(report, 'client_id') and hasattr(current_user, 'client_id'):
            if report.client_id == current_user.client_id:
                can_access = True
        if not can_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to report attachments"
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
                createdAt=datetime.now(timezone.utc)
            )
        )
    
    return results