from fastapi import APIRouter

from app.models.schemas import ForecastRequest, ForecastResponse
from app.services.forecast_service import ForecastService

router = APIRouter(prefix="/api/v1/forecasting", tags=["Forecasting"])

@router.post("/generate", response_model=ForecastResponse)
def generate_forecast(request: ForecastRequest):
    """Generate a demand forecast for a product."""
    service = ForecastService()
    return service.generate_forecast(request)

@router.get("/{forecast_id}")
def get_forecast(forecast_id: str):
    """Retrieve a previously generated forecast."""
    service = ForecastService()
    forecast = service.get_stored_forecast(forecast_id)
    if not forecast:
        return {"error": "Forecast not found"}
    return forecast