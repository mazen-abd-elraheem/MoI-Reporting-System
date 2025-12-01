from sqlalchemy.orm import Session
from sqlalchemy import func , extract
from typing import List

from app.models.analytics import HotFactReport, ColdFactReport
from app.schemas.analytics import DashboardStatsResponse

class AnalyticsService:
    """Business logic for Analytics DB queries"""
    
    @staticmethod
    def get_dashboard_stats(db: Session) -> DashboardStatsResponse:
        """
        Get high-level KPIs for admin dashboard.
        Queries the Analytics DB (hot table).
        """
        
        # Total reports (hot + cold)
        hot_count = db.query(func.count(HotFactReport.reportId)).scalar() or 0
        
        # Try to get cold count (may fail if cold table empty)
        try:
            cold_count = db.query(func.count(ColdFactReport.reportId)).scalar() or 0
        except:
            cold_count = 0
        
        total_reports = hot_count + cold_count
        
        # Reports by status (from hot table)
        status_counts = db.query(
            HotFactReport.status,
            func.count(HotFactReport.reportId).label('count')
        ).group_by(HotFactReport.status).all()
        
        # Reports by category
        category_counts = db.query(
            HotFactReport.categoryId,
            func.count(HotFactReport.reportId).label('count')
        ).group_by(HotFactReport.categoryId).all()
        
        # Average AI confidence
        avg_confidence = db.query(
            func.avg(HotFactReport.aiConfidence)
        ).scalar() or 0.0
        
        # Anonymous vs Registered
        anonymous_count = db.query(
            func.count(HotFactReport.reportId)
        ).filter(HotFactReport.isAnonymous == True).scalar() or 0

    @staticmethod
    def get_cold_monthly_category_breakdown(db: Session):
        """Returns (year, month, category, count) for COLD database."""
        return db.query(
            extract('year', ColdFactReport.createdAt).label('report_year'),
            extract('month', ColdFactReport.createdAt).label('report_month'),
            ColdFactReport.categoryId,
            func.count().label('count')
        ).group_by(
            extract('year', ColdFactReport.createdAt),
            extract('month', ColdFactReport.createdAt),
            ColdFactReport.categoryId
        ).order_by(
            'report_year',
            'report_month'
        ).all()

    @staticmethod
    def get_hot_monthly_category_breakdown(db: Session):
        """Returns (year, month, category, count) for HOT database."""
        return db.query(
            extract('year', HotFactReport.createdAt).label('report_year'),
            extract('month', HotFactReport.createdAt).label('report_month'),
            HotFactReport.categoryId,
            func.count().label('count')
        ).group_by(
            extract('year', HotFactReport.createdAt),
            extract('month', HotFactReport.createdAt),
            HotFactReport.categoryId
        ).order_by(
            'report_year',
            'report_month'
        ).all()




        return DashboardStatsResponse(
            totalReports=total_reports,
            hotReports=hot_count,
            coldReports=cold_count,
            statusBreakdown={row.status: row.count for row in status_counts},
            categoryBreakdown={row.categoryId: row.count for row in category_counts},
            avgAiConfidence=float(avg_confidence),
            anonymousReports=anonymous_count,
            registeredReports=hot_count - anonymous_count
        )
    
    @staticmethod
    def export_csv_data(db: Session) -> List[HotFactReport]:
        """Get recent reports for CSV export"""
        return db.query(HotFactReport).order_by(
            HotFactReport.createdAt.desc()
        ).limit(10000).all()