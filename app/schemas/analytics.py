from pydantic import BaseModel
from typing import Dict, List

class MonthlyCategoryCount(BaseModel):
    year: int
    month: int
    category: str
    count: int


class DashboardStatsResponse(BaseModel):
    """Response schema for dashboard statistics"""
    totalReports: int
    hotReports: int
    coldReports: int
    statusBreakdown: Dict[str, int]
    categoryBreakdown: Dict[str, int]
    avgAiConfidence: float
    anonymousReports: int
    registeredReports: int
    
    monthlyCategoryCounts: List[MonthlyCategoryCount]

    class Config:
        from_attributes = True