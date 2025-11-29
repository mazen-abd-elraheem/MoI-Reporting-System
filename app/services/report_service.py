import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy.orm import selectinload, Session
from fastapi import HTTPException, UploadFile

from app.services.blob_service import BlobStorageService
from app.schemas.attachment import FileType

from app.models.report import Report
from app.models.attachment import Attachment
from app.schemas.report import (
    ReportCreate, 
    ReportResponse, 
    ReportListResponse, 
    ReportStatusUpdate
)

def utcnow():
    """Helper function to get current UTC time"""
    return datetime.now(timezone.utc)

class ReportService:
    """Service layer for report operations"""
    
    @staticmethod
    async def create_report_with_files(
        db: Session,
        report_data: ReportCreate,
        files: List[UploadFile],
        user_id: Optional[str] = None
    ) -> ReportResponse:
        """
        Create a report with file attachments
        
        Process:
        1. Creates Report record in database
        2. Uploads each file to Azure Blob Storage
        3. Saves attachment metadata to database
        4. Returns response with temporary SAS download URLs
        
        Args:
            db: Database session
            report_data: Report data from request
            files: List of uploaded files
            user_id: User ID (None for anonymous reports)
        
        Returns:
            ReportResponse with report details and attachments
        
        Raises:
            HTTPException: If file upload or database operation fails
        """
        
        # --- 1. Create Report Record ---
        report_id = f"R-{uuid.uuid4().hex[:8].upper()}"
        
        db_report = Report(
            reportId=report_id,
            title=report_data.title,
            descriptionText=report_data.descriptionText,
            locationRaw=report_data.location,
            categoryId=report_data.categoryId.value if report_data.categoryId else "other",
            userId=user_id,
            transcribedVoiceText=report_data.transcribedVoiceText,
            status="Submitted",
            aiConfidence=None,
            createdAt=utcnow(),
            updatedAt=utcnow()
        )
        
        db.add(db_report)
        db.flush()  # Insert report without committing transaction
        
        # --- 2. Initialize Blob Service ---
        blob_service = BlobStorageService()
        attachment_responses_data = []
        uploaded_blobs = []  # Track uploaded blobs for rollback
        
        # --- 3. Process Each File ---
        for file in files:
            try:
                # Read file content
                file_bytes = await file.read()
                
                if len(file_bytes) == 0:
                    raise Exception(f"File '{file.filename}' is empty")
                
                # Upload to Azure Blob Storage
                blob_url = blob_service.upload_file(
                    file_content=file_bytes,
                    filename=file.filename or "unnamed",
                    content_type=file.content_type or "application/octet-stream"
                )
                
                if not blob_url:
                    raise Exception(f"Failed to upload file to blob storage")
                
                uploaded_blobs.append(blob_url)  # Track for potential rollback
                
                # Generate temporary SAS download URL (expires in 1 hour)
                download_url = blob_service.generate_download_url(blob_url)
                
                # Determine file type from MIME type
                mime = file.content_type or "application/octet-stream"
                if mime.startswith("image/"):
                    file_type = FileType.IMAGE
                elif mime.startswith("video/"):
                    file_type = FileType.VIDEO
                elif mime.startswith("audio/"):
                    file_type = FileType.AUDIO
                else:
                    file_type = FileType.DOCUMENT
                
                # Create attachment record in database
                new_attachment = Attachment(
                    attachmentId=str(uuid.uuid4()),
                    reportId=report_id,
                    blobStorageUri=blob_url,
                    mimeType=mime,
                    fileType=file_type.value,
                    fileSizeBytes=len(file_bytes)
                )
                db.add(new_attachment)
                
                # Prepare attachment data for response
                attachment_responses_data.append({
                    "attachmentId": new_attachment.attachmentId,
                    "reportId": report_id,
                    "blobStorageUri": blob_url,
                    "downloadUrl": download_url,
                    "mimeType": mime,
                    "fileType": file_type.value,
                    "fileSizeBytes": len(file_bytes),
                    "createdAt": utcnow()
                })
                
            except Exception as e:
                # Rollback: Delete uploaded blobs and rollback database transaction
                db.rollback()
                for blob_url in uploaded_blobs:
                    blob_service.delete_file(blob_url)
                
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to process file '{file.filename}': {str(e)}"
                )
        
        # --- 4. Commit Transaction and Return ---
        try:
            db.commit()
            db.refresh(db_report)
            
            return ReportResponse(
                reportId=db_report.reportId,
                title=db_report.title,
                descriptionText=db_report.descriptionText,
                categoryId=db_report.categoryId,
                status=db_report.status,
                location=db_report.locationRaw,
                aiConfidence=db_report.aiConfidence,
                createdAt=db_report.createdAt,
                updatedAt=db_report.updatedAt,
                userId=db_report.userId,
                transcribedVoiceText=db_report.transcribedVoiceText,
                attachments=attachment_responses_data,
                reportUrl=None  # Will be set by API endpoint
            )
        except Exception as e:
            # Rollback on commit failure
            db.rollback()
            for blob_url in uploaded_blobs:
                blob_service.delete_file(blob_url)
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create report: {str(e)}"
            )
    
    @staticmethod
    def get_report(db: Session, report_id: Optional[str] = None) -> Optional[ReportResponse]:
        """
        Get a single report by ID with attachments
        
        Args:
            db: Database session
            report_id: Unique report identifier
        
        Returns:
            ReportResponse with all details and attachments, or None if not found
        """
        
        if report_id:
        # Query report with eager loading of attachments
            report = db.query(Report).options(
                selectinload(Report.attachments)
            ).filter(Report.reportId == report_id).first()
  


        if not report:
            return None
        
        # Generate download URLs for all attachments
        blob_service = BlobStorageService()
        attachment_responses = []
        
        for att in report.attachments:
            download_url = blob_service.generate_download_url(att.blobStorageUri)
            print(download_url)
            attachment_responses.append({
                "attachmentId": att.attachmentId,
                "reportId": att.reportId,
                "blobStorageUri": att.blobStorageUri,
                "downloadUrl": download_url,
                "mimeType": att.mimeType,
                "fileType": att.fileType,
                "fileSizeBytes": att.fileSizeBytes,
                "createdAt": utcnow()  # Manual timestamp (until DB migration)
            })
        
        return ReportResponse(
            reportId=report.reportId,
            title=report.title,
            descriptionText=report.descriptionText,
            categoryId=report.categoryId,
            status=report.status,
            location=report.locationRaw,
            aiConfidence=report.aiConfidence,
            createdAt=report.createdAt,
            updatedAt=report.updatedAt,
            userId=report.userId,
            transcribedVoiceText=report.transcribedVoiceText,
            attachments=attachment_responses
        )
    @staticmethod
    def list_reports(
        db: Session, 
        skip: int = 0, 
        limit: int = 10,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> ReportListResponse:
        """
        List reports with pagination and filtering
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            status: Optional status filter
            category: Optional category filter
        
        Returns:
            ReportListResponse with paginated reports and metadata
        """
        
        # Build query with eager loading
        query = db.query(Report).options(selectinload(Report.attachments))
        
        # Apply filters
        if status:
            query = query.filter(Report.status == status)
        if category:
            query = query.filter(Report.categoryId == category)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination and ordering
        reports = query.order_by(Report.createdAt.desc()).offset(skip).limit(limit).all()
        
        # Generate download URLs for all attachments
        blob_service = BlobStorageService()
        report_responses = []
        
        for r in reports:
            attachment_responses = []
            for att in r.attachments:
                download_url = blob_service.generate_download_url(att.blobStorageUri)
                attachment_responses.append({
                    "attachmentId": att.attachmentId,
                    "reportId": att.reportId,
                    "blobStorageUri": att.blobStorageUri,
                    "downloadUrl": download_url,
                    "mimeType": att.mimeType,
                    "fileType": att.fileType,
                    "fileSizeBytes": att.fileSizeBytes,
                    "createdAt": utcnow()  # Manual timestamp
                })
            
            report_responses.append(
                ReportResponse(
                    reportId=r.reportId,
                    title=r.title,
                    descriptionText=r.descriptionText,
                    categoryId=r.categoryId,
                    status=r.status,
                    location=r.locationRaw,
                    aiConfidence=r.aiConfidence,
                    createdAt=r.createdAt,
                    updatedAt=r.updatedAt,
                    userId=r.userId,
                    transcribedVoiceText=r.transcribedVoiceText,
                    attachments=attachment_responses
                )
            )
        
        # Calculate pagination metadata
        return ReportListResponse(
            reports=report_responses,
            total=total,
            page=(skip // limit) + 1 if limit > 0 else 1,
            pageSize=limit,
            totalPages=(total + limit - 1) // limit if limit > 0 else 1
        ) 
    @staticmethod
    def get_report_by_user(
        db: Session, 
        user_id: str,
        skip: int = 0, 
        limit: int = 10,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> ReportListResponse:
        """
        List reports with pagination and filtering
        
        Args:
            db: Database session
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            status: Optional status filter
            category: Optional category filter
        
        Returns:
            ReportListResponse with paginated reports and metadata
        """
        
        # Build query with eager loading
        query = db.query(Report).options(selectinload(Report.attachments))
        
        # Apply filters
        if status:
            query = query.filter(Report.status == status)
        if category:
            query = query.filter(Report.categoryId == category)
        if user_id:
            query = query.filter(Report.userId == user_id)
        
        # Get total count before pagination
        total = query.count()
        
        # Apply pagination and ordering
        reports = query.order_by(Report.createdAt.desc()).offset(skip).limit(limit).all()
        
        # Generate download URLs for all attachments
        blob_service = BlobStorageService()
        report_responses = []
        
        for r in reports:
            attachment_responses = []
            for att in r.attachments:
                download_url = blob_service.generate_download_url(att.blobStorageUri)
                attachment_responses.append({
                    "attachmentId": att.attachmentId,
                    "reportId": att.reportId,
                    "blobStorageUri": att.blobStorageUri,
                    "downloadUrl": download_url,
                    "mimeType": att.mimeType,
                    "fileType": att.fileType,
                    "fileSizeBytes": att.fileSizeBytes,
                    "createdAt": utcnow()  # Manual timestamp
                })
            
            report_responses.append(
                ReportResponse(
                    reportId=r.reportId,
                    title=r.title,
                    descriptionText=r.descriptionText,
                    categoryId=r.categoryId,
                    status=r.status,
                    location=r.locationRaw,
                    aiConfidence=r.aiConfidence,
                    createdAt=r.createdAt,
                    updatedAt=r.updatedAt,
                    userId=r.userId,
                    transcribedVoiceText=r.transcribedVoiceText,
                    attachments=attachment_responses
                )
            )
        
        # Calculate pagination metadata
        return ReportListResponse(
            reports=report_responses,
            total=total,
            page=(skip // limit) + 1 if limit > 0 else 1,
            pageSize=limit,
            totalPages=(total + limit - 1) // limit if limit > 0 else 1
        )
    
    @staticmethod
    def update_report_status(
        db: Session,
        report_id: str,
        status_update: ReportStatusUpdate
    ) -> Optional[ReportResponse]:
        """
        Update the status of a report
        
        Args:
            db: Database session
            report_id: Unique report identifier
            status_update: New status and optional notes
        
        Returns:
            Updated ReportResponse, or None if report not found
        
        Raises:
            HTTPException: If database operation fails
        """
        
        # Query report with attachments
        report = db.query(Report).options(
            selectinload(Report.attachments)
        ).filter(Report.reportId == report_id).first()
        
        if not report:
            return None
        
        # Update status and timestamp
        report.status = status_update.status.value
        report.updatedAt = utcnow()
        
        try:
            db.commit()
            db.refresh(report)
            
            # Return updated report with attachments
            return ReportService.get_report(db, report_id)
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to update report status: {str(e)}"
            )
    
    @staticmethod
    def delete_report(db: Session, report_id: str) -> bool:
        """
        Delete a report and all its attachments
        
        This will:
        1. Delete all files from Azure Blob Storage
        2. Delete attachment records from database
        3. Delete report record from database
        
        Args:
            db: Database session
            report_id: Unique report identifier
        
        Returns:
            True if successful, False if report not found
        
        Raises:
            HTTPException: If deletion fails
        """
        
        # Query report with attachments
        report = db.query(Report).options(
            selectinload(Report.attachments)
        ).filter(Report.reportId == report_id).first()
        
        if not report:
            return False
        
        try:
            # Delete all files from blob storage
            blob_service = BlobStorageService()
            for attachment in report.attachments:
                blob_service.delete_file(attachment.blobStorageUri)
            
            # Delete report (cascade will delete attachments from DB)
            db.delete(report)
            db.commit()
            
            return True
        except Exception as e:
            db.rollback()
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to delete report: {str(e)}"
            )
    
    @staticmethod
    def get_report_statistics(db: Session) -> dict:
        """
        Get statistics about reports
        
        Args:
            db: Database session
        
        Returns:
            Dictionary with report statistics
        """
        from sqlalchemy import func
        
        total_reports = db.query(func.count(Report.reportId)).scalar()
        
        # Count by status
        status_counts = db.query(
            Report.status,
            func.count(Report.reportId)
        ).group_by(Report.status).all()
        
        # Count by category
        category_counts = db.query(
            Report.categoryId,
            func.count(Report.reportId)
        ).group_by(Report.categoryId).all()
        
        return {
            "total_reports": total_reports,
            "by_status": {status: count for status, count in status_counts},
            "by_category": {category: count for category, count in category_counts}
        }