from sqlalchemy.orm import Session
from sqlalchemy import func , extract , case
from typing import List, Dict, Any, Tuple


from app.models.user import User
from app.models.analytics import HotFactReport, ColdFactReport
from app.schemas.analytics import DashboardStatsResponse
from app.models.report import Report


class AnalyticsService:
    """Business logic for Analytics DB queries"""

    # Define constants here to avoid repetition
    TARGET_CATEGORIES = [
        'infrastructure', 'utilities', 'crime', 'traffic', 
        'public_nuisance', 'environmental', 'other'
    ]
    TARGET_STATUSES = [
        'Submitted', 'Assigned', 'Inprogress', 'Resolved', 'Rejected'
    ]

    # ==========================================
    # INTERNAL HELPER METHODS
    # ==========================================
    @staticmethod
    def _build_empty_matrix() -> Dict:
        """Creates the initial structure with all zeros."""
        return {
            cat: {stat: 0 for stat in AnalyticsService.TARGET_STATUSES} 
            for cat in AnalyticsService.TARGET_CATEGORIES
        }

    @staticmethod
    def _query_matrix(db: Session, model) -> Dict:
        """
        Generic helper to query any table (Hot or Cold) 
        and return the Category vs Status matrix.
        """
        # 1. Start with 0s
        results = AnalyticsService._build_empty_matrix()
        
        # 2. Query the DB
        query_data = db.query(
            model.categoryId,
            model.status,
            func.count(model.reportId).label('count')
        ).filter(
            model.categoryId.in_(AnalyticsService.TARGET_CATEGORIES),
            model.status.in_(AnalyticsService.TARGET_STATUSES)
        ).group_by(
            model.categoryId, 
            model.status
        ).all()

        # 3. Update the zeros with actual counts
        for cat, status, count in query_data:
            if cat in results and status in results[cat]:
                results[cat][status] = count
        
        return results

    # ==========================================
    # PUBLIC METHODS (Endpoints use these)
    # ==========================================

    @staticmethod
    def get_hot_stats_matrix(db: Session) -> Dict:
        """Returns matrix for ACTIVE (Hot) reports only."""
        return AnalyticsService._query_matrix(db, HotFactReport)

    @staticmethod
    def get_cold_stats_matrix(db: Session) -> Dict:
        """Returns matrix for ARCHIVED (Cold) reports only."""
        try:
            return AnalyticsService._query_matrix(db, ColdFactReport)
        except Exception:
            # If cold table doesn't exist yet, return empty zeros
            return AnalyticsService._build_empty_matrix()

    @staticmethod
    def get_dashboard_stats(db: Session) -> DashboardStatsResponse:
        """
        Get high-level KPIs for admin dashboard.
        """
        # Total reports (hot + cold)
        hot_count = db.query(func.count(HotFactReport.reportId)).scalar() or 0
        
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

        # Return the response object (Fixed indentation)
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

    @staticmethod
    def export_csv_data(db: Session) -> List[HotFactReport]:
        """Get recent reports for CSV export"""
        return db.query(HotFactReport).order_by(
            HotFactReport.createdAt.desc()
        ).limit(10000).all()

    @staticmethod
    def _query_status_counts(db: Session, model) -> dict:
        """Helper to count reports by status only (ignoring category)."""
        # 1. Start with 0s
        results = {status: 0 for status in AnalyticsService.TARGET_STATUSES}
        
        # 2. Query DB
        query_data = db.query(
            model.status,
            func.count(model.reportId).label('count')
        ).filter(
            model.status.in_(AnalyticsService.TARGET_STATUSES)
        ).group_by(
            model.status
        ).all()

        # 3. Fill values
        for status, count in query_data:
            if status in results:
                results[status] = count
        
        return results

    @staticmethod
    def get_hot_status_counts(db: Session) -> dict:
        """Get status counts for ACTIVE reports"""
        return AnalyticsService._query_status_counts(db, HotFactReport)

    @staticmethod
    def get_cold_status_counts(db: Session) -> dict:
        """Get status counts for ARCHIVED reports"""
        try:
            return AnalyticsService._query_status_counts(db, ColdFactReport)
        except Exception:
            # Return 0s if cold table is missing
            return {status: 0 for status in AnalyticsService.TARGET_STATUSES}
