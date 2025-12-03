from pydantic import BaseModel
from typing import Dict, List
from app.schemas.user import UserDemographicResponse,UserListResponse




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
    demographiCounts : List[UserDemographicResponse]
    UsersList : List[UserListResponse]

    class Config:
        from_attributes = True
class CategoryStatusStats(BaseModel):
    # Dictionary where Key = Category Name, Value = Dict of Status Counts
    # Example: {"crime": {"Resolved": 10, "Submitted": 2}}
    matrix: Dict[str, Dict[str, int]]

class StatusCountStats(BaseModel):
    # Example: { "Submitted": 120, "Resolved": 45, "Rejected": 2 }
    counts: Dict[str, int]