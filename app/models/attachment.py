from sqlalchemy import Column, String, BigInteger, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship

from app.core.database import BaseOps  

class Attachment(BaseOps):
    __tablename__ = "Attachment"
    __table_args__ = (
        CheckConstraint('fileSizeBytes > 0', name='CK_Attachment_FileSize'),
        {'schema': 'dbo'}
    )

    # Primary Key
    attachmentId = Column("attachmentId", String(450), primary_key=True, index=True)
    
    # Foreign Key
    reportId = Column(
        "reportId",
        String(450), 
        ForeignKey("dbo.Report.reportId", ondelete="CASCADE"),
        nullable=False
    )
    
    # Metadata Columns
    blobStorageUri = Column("blobStorageUri", String(2048), nullable=False)
    mimeType = Column("mimeType", String(100), nullable=False)
    fileType = Column("fileType", String(50), nullable=False)
    fileSizeBytes = Column(
        "fileSizeBytes",
        BigInteger,
        nullable=False
    )

    # Relationship
    report = relationship("Report", back_populates="attachments")

    def __repr__(self):
        return f"<Attachment(attachmentId={self.attachmentId}, fileType={self.fileType})>"