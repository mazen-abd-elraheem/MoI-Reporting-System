from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import csv
import io

from app.core.database import get_db_analytics
from app.services.analytics_service import AnalyticsService
from app.schemas.analytics import DashboardStatsResponse , MonthlyCategoryCount

router = APIRouter()

@router.get(
    "/dashboard/stats",
    response_model=DashboardStatsResponse,
    summary="Get Admin Dashboard KPIs"
)
def get_dashboard_stats(
    db: Session = Depends(get_db_analytics)
):
    """
    Get high-level statistics for the admin dashboard.
    Read-only query from the Analytics Database.
    """
    try:
        return AnalyticsService.get_dashboard_stats(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard stats: {str(e)}"
        )

@router.get(
    "/analytics/export",
    summary="Export data to CSV"
)
def export_analytics_csv(
    db: Session = Depends(get_db_analytics)
):
    """Download a CSV file of recent reports for offline analysis"""
    try:
        data = AnalyticsService.export_csv_data(db)
        
        stream = io.StringIO()
        csv_writer = csv.writer(stream)
        
        csv_writer.writerow([
            "ReportId", "Title", "Status", "Category", 
            "Confidence", "IsAnonymous", "CreatedAt"
        ])
        
        for row in data:
            csv_writer.writerow([
                row.reportId,
                row.title,
                row.status,
                row.categoryId,
                row.aiConfidence,
                row.isAnonymous,
                row.createdAt
            ])
        
        stream.seek(0)
        
        return StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=moi_analytics_export.csv"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export CSV: {str(e)}"
        )

@router.get(
    "/dashboard/cold/monthly-category-breakdown",
    summary="monthly category stats"
)
def get_cold_monthly_breakdown(
    db: Session = Depends(get_db_analytics)
):
    try:
        rows = AnalyticsService.get_cold_monthly_category_breakdown(db)


        data = [
            MonthlyCategoryCount(
                year=row.report_year,
                month=row.report_month,
                category=row.categoryId,
                count=row.count
            )
            for row in rows
        ]

        return data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch cold monthly breakdown: {str(e)}"
        )

@router.get(
    "/dashboard/hot/monthly-category-breakdown",
    summary="category stats for the past three months"
)
def get_hot_monthly_breakdown(
    db: Session = Depends(get_db_analytics)
):
    try:
        rows = AnalyticsService.get_hot_monthly_category_breakdown(db)

        # map each tuple to a Pydantic object
        data = [
            MonthlyCategoryCount(
                year=row.report_year,
                month=row.report_month,
                category=row.categoryId,
                count=row.count
            )
            for row in rows
        ]
        return data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch hot monthly breakdown: {str(e)}"
        )