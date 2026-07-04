from fastapi import APIRouter

from app.models.schemas import ReportRequest, ReportResponse
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])

@router.post("/generate", response_model=ReportResponse)
def generate_report(request: ReportRequest):
    """Generate a comprehensive retail analytics report."""
    service = ReportService()
    return service.create_report(request)

@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str):
    """Retrieve a previously generated report."""
    service = ReportService()
    report = service.get_report(report_id)
    if not report:
        return {"error": "Report not found"}
    return report