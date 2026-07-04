from fastapi import APIRouter, Query

from app.models.schemas import ExtractedData, InsightBatch, UnstructuredReport
from app.services.insight_service import InsightService

router = APIRouter(prefix="/api/v1/insights", tags=["Insights"])

@router.get("/generate", response_model=InsightBatch)
def generate_insights(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(5, ge=1, le=20),
):
    """Generate AI-powered customer and business insights from recent data."""
    service = InsightService()
    return service.generate_insights(days=days, limit=limit)

@router.post("/extract", response_model=ExtractedData)
def extract_from_unstructured(report: UnstructuredReport):
    """Extract structured data from an unstructured retail report using AI."""
    service = InsightService()
    return service.extract_from_unstructured(report)