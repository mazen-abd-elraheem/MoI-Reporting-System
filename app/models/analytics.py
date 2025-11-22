from sqlalchemy import Column, String, Float, DateTime, Text, Integer, Boolean, func

from app.core.database import BaseAnalytics  

class HotFactReport(BaseAnalytics):
    """
    Maps to [hot].[Fact_Reports] in Analytics DB
    Recent reports (last 90 days)
    """
    __tablename__ = "Fact_Reports"
    __table_args__ = {'schema': 'hot'}

    # Primary key
    reportId = Column("reportId", String(450), primary_key=True)
    
    # Core fields
    title = Column("title", String(500), nullable=False)
    descriptionText = Column("descriptionText", Text, nullable=False)
    locationRaw = Column("locationRaw", String(2048), nullable=True)
    
    status = Column("status", String(50), nullable=False)
    categoryId = Column("categoryId", String(100), nullable=False)
    
    # Metrics
    aiConfidence = Column("aiConfidence", Float, nullable=True)
    
    # Timestamps
    createdAt = Column("createdAt", DateTime, nullable=False)
    updatedAt = Column("updatedAt", DateTime, nullable=False)
    
    # User info (denormalized)
    userId = Column("userId", String(450), nullable=True)
    userRole = Column("userRole", String(50), nullable=True)
    isAnonymous = Column("isAnonymous", Boolean, nullable=True)
    
    # Aggregate fields
    attachmentCount = Column("attachmentCount", Integer, default=0)
    transcribedVoiceText = Column("transcribedVoiceText", Text, nullable=True)
    
    # ETL metadata
    extractedAt = Column("extractedAt", DateTime, nullable=False, server_default=func.getutcdate())

    def __repr__(self):
        return f"<HotFactReport(reportId={self.reportId}, status={self.status})>"


class ColdFactReport(BaseAnalytics):
    """
    Maps to [cold].[Fact_Reports] in Analytics DB
    Historical reports (older than 90 days)
    """
    __tablename__ = "Fact_Reports"
    __table_args__ = {'schema': 'cold'}

    # Primary key
    reportId = Column("reportId", String(450), primary_key=True)
    
    # Core fields (less detail than hot)
    title = Column("title", String(500), nullable=False)
    status = Column("status", String(50), nullable=False)
    categoryId = Column("categoryId", String(100), nullable=False)
    
    # Timestamps
    createdAt = Column("createdAt", DateTime, nullable=False)
    updatedAt = Column("updatedAt", DateTime, nullable=False)
    
    # User info
    userRole = Column("userRole", String(50), nullable=True)
    isAnonymous = Column("isAnonymous", Boolean, nullable=True)
    
    # Aggregates
    attachmentCount = Column("attachmentCount", Integer, default=0)
    aiConfidence = Column("aiConfidence", Float, nullable=True)
    
    # ETL metadata
    extractedAt = Column("extractedAt", DateTime, nullable=False, server_default=func.getutcdate())

    def __repr__(self):
        return f"<ColdFactReport(reportId={self.reportId}, status={self.status})>"