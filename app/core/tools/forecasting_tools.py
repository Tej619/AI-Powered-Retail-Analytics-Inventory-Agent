from typing import Optional, Type

from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from app.models.enums import ForecastMethod
from app.models.schemas import ForecastRequest
from app.services.forecast_service import ForecastService, get_forecast_service
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GenerateForecastInput(BaseModel):
    """Input for forecast generation."""
    product_id: str = Field(..., description="Product ID to forecast")
    horizon_days: int = Field(30, description="Number of days to forecast", ge=1, le=365)
    method: str = Field(
        "ai_forecast",
        description="Forecast method: ai_forecast, moving_average, exponential_smoothing",
    )


class GenerateForecastTool(BaseTool):
    """Generate a demand forecast for a product."""

    name: str = "generate_forecast"
    description: str = (
        "Generate a demand forecast for a specific product. "
        "Returns predicted daily demand, trend direction, and confidence intervals. "
        "Use 'ai_forecast' for best results (considers patterns and seasonality), "
        "'moving_average' for simple baseline, or 'exponential_smoothing' for trend-aware baseline."
    )
    args_schema: Type[BaseModel] = GenerateForecastInput

    def _run(self, product_id: str, horizon_days: int = 30, method: str = "ai_forecast") -> str:
        try:
            service = get_forecast_service()
            request = ForecastRequest(
                product_id=product_id,
                method=ForecastMethod(method),
                horizon_days=horizon_days,
            )

            forecast = service.generate_forecast(request)

            result = (
                f"Forecast for {forecast.product_name} ({forecast.product_id}):\n"
                f"  Method: {forecast.method.value}\n"
                f"  Horizon: {forecast.horizon_days} days\n"
                f"  Historical Avg Daily: {forecast.historical_avg_daily:.1f} units\n"
                f"  Predicted Avg Daily: {forecast.predicted_avg_daily:.1f} units\n"
                f"  Predicted Total: {forecast.predicted_total:.0f} units\n"
                f"  Trend: {forecast.trend_direction} ({forecast.trend_percentage:+.1%})\n"
                f"  Confidence: {forecast.confidence_interval:.0%}\n\n"
                f"  First 7 days prediction:\n"
            )

            for point in forecast.points[:7]:
                result += (
                    f"    {point.date.strftime('%Y-%m-%d')}: "
                    f"{point.predicted_demand:.0f} units "
                    f"({point.lower_bound:.0f} - {point.upper_bound:.0f})\n"
                )

            if len(forecast.points) > 7:
                result += f"    ... and {len(forecast.points) - 7} more days\n"

            result += f"\n  Forecast ID: {forecast.forecast_id}"
            return result

        except Exception as e:
            logger.error("forecast_tool_failed", error=str(e), product_id=product_id)
            return f"Failed to generate forecast: {str(e)}"


class AnalyzeTrendsInput(BaseModel):
    """Input for trend analysis."""
    product_id: Optional[str] = Field(None, description="Specific product (optional)")
    category: Optional[str] = Field(None, description="Category filter (optional)")
    days: int = Field(30, description="Number of days to analyze")


class AnalyzeTrendsTool(BaseTool):
    """Analyze sales trends over time."""

    name: str = "analyze_trends"
    description: str = (
        "Analyze sales trends over a time period. Can filter by product or category. "
        "Returns week-over-week changes, top movers, and trend direction."
    )
    args_schema: Type[BaseModel] = AnalyzeTrendsInput

    def _run(
        self,
        product_id: Optional[str] = None,
        category: Optional[str] = None,
        days: int = 30,
    ) -> str:
        from google.cloud.bigquery import ScalarQueryParameter
        from app.services.bigquery_service import get_bigquery_service

        bq = get_bigquery_service()
        conditions = [f"s.sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)"]
        params = []
        idx = 0

        if product_id:
            conditions.append(f"s.product_id = @p{idx}")
            params.append(ScalarQueryParameter(f"p{idx}", "STRING", product_id))
            idx += 1
        if category:
            conditions.append(f"p.category = @p{idx}")
            params.append(ScalarQueryParameter(f"p{idx}", "STRING", category))
            idx += 1

        where = " AND ".join(conditions)

        query = f"""
        WITH weekly AS (
            SELECT
                p.product_id, p.name, p.category,
                DATE_TRUNC(s.sale_date, WEEK) as week,
                SUM(s.quantity) as units,
                SUM(s.total_amount) as revenue
            FROM `{bq.full_table_name('sales')}` s
            JOIN `{bq.full_table_name('products')}` p ON s.product_id = p.product_id
            WHERE {where}
            GROUP BY p.product_id, p.name, p.category, DATE_TRUNC(s.sale_date, WEEK)
        ),
        with_lag AS (
            SELECT *,
                LAG(units) OVER (PARTITION BY product_id ORDER BY week) as prev_units,
                LAG(revenue) OVER (PARTITION BY product_id ORDER BY week) as prev_rev
            FROM weekly
        )
        SELECT
            product_id, name, category, week,
            units, revenue, prev_units, prev_rev,
            CASE WHEN prev_units > 0 THEN (units - prev_units) * 100.0 / prev_units ELSE 0 END as units_chg_pct,
            CASE WHEN prev_rev > 0 THEN (revenue - prev_rev) * 100.0 / prev_rev ELSE 0 END as rev_chg_pct
        FROM with_lag
        WHERE prev_units IS NOT NULL
        ORDER BY ABS(units_chg_pct) DESC
        LIMIT 10
        """

        df = bq.run_query(query, params=params or None)

        if df.empty:
            return f"No trend data found for the specified criteria ({days} days)."

        result = f"Top Trend Changes (last {days} days):\n\n"
        for _, row in df.iterrows():
            emoji = "📈" if row["units_chg_pct"] > 0 else "📉"
            result += (
                f"{emoji} {row['name']} ({row['category']})\n"
                f"   Units: {int(row['units'])} ({row['units_chg_pct']:+.1f}% vs prior week)\n"
                f"   Revenue: ${row['revenue']:,.0f} ({row['rev_chg_pct']:+.1f}% vs prior week)\n\n"
            )

        return result


def get_forecasting_tools() -> list[BaseTool]:
    return [GenerateForecastTool(), AnalyzeTrendsTool()]