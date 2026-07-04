import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
from google.cloud.bigquery import ScalarQueryParameter

from app.models.enums import ForecastMethod
from app.models.schemas import ForecastPoint, ForecastRequest, ForecastResponse
from app.services.bigquery_service import BigQueryService, get_bigquery_service
from app.services.openai_service import OpenAIService, get_openai_service
from app.utils.errors import ForecastingError
from app.utils.helpers import generate_cache_key, now_utc, safe_float
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ForecastService:
    """AI-powered demand forecasting service."""

    def __init__(
        self,
        bq: Optional[BigQueryService] = None,
        openai: Optional[OpenAIService] = None,
    ) -> None:
        self.bq = bq or get_bigquery_service()
        self.openai = openai or get_openai_service()

    def _get_historical_demand(
        self,
        product_id: str,
        days: int = 180,
    ) -> pd.DataFrame:
        """Fetch historical daily demand from BigQuery."""
        query = f"""
        SELECT
            DATE(sale_date) as date,
            SUM(quantity) as quantity,
            SUM(total_amount) as revenue,
            COUNT(DISTINCT sale_id) as transaction_count
        FROM `{self.bq.full_table_name('sales')}`
        WHERE product_id = @product_id
            AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
        GROUP BY DATE(sale_date)
        ORDER BY date
        """

        params = [
            ScalarQueryParameter("product_id", "STRING", product_id),
            ScalarQueryParameter("days", "INT64", days),
        ]

        df = self.bq.run_query(query, params=params)

        if df.empty:
            raise ForecastingError(
                f"No historical sales data found for product {product_id}",
                details={"product_id": product_id},
            )

        # Ensure continuous date range (fill missing days with 0)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        full_range = pd.date_range(start=df.index.min(), end=df.index.max(), freq="D")
        df = df.reindex(full_range, fill_value=0)
        df.index.name = "date"
        df = df.reset_index()

        return df

    def _get_product_info(self, product_id: str) -> dict:
        """Get product metadata for context in forecasting."""
        query = f"""
        SELECT product_id, name, sku, category, unit_price, unit_cost
        FROM `{self.bq.full_table_name('products')}`
        WHERE product_id = @product_id
        """
        params = [ScalarQueryParameter("product_id", "STRING", product_id)]
        df = self.bq.run_query(query, params=params)
        if df.empty:
            return {"product_id": product_id, "name": product_id, "category": "unknown"}
        return df.iloc[0].to_dict()

    def _moving_average_forecast(
        self,
        historical: pd.DataFrame,
        horizon: int,
        window: int = 7,
    ) -> tuple[list[ForecastPoint], float]:
        """Simple moving average forecast."""
        values = historical["quantity"].values
        ma = np.convolve(values, np.ones(window) / window, mode="valid")
        last_ma = ma[-1] if len(ma) > 0 else np.mean(values)

        std = np.std(values[-window * 3:]) if len(values) >= window * 3 else np.std(values)

        points = []
        last_date = historical["date"].iloc[-1]
        for i in range(1, horizon + 1):
            date = last_date + timedelta(days=i)
            points.append(
                ForecastPoint(
                    date=date.to_pydatetime(),
                    predicted_demand=max(0, round(last_ma, 2)),
                    lower_bound=max(0, round(last_ma - 1.96 * std, 2)),
                    upper_bound=round(last_ma + 1.96 * std, 2),
                )
            )

        return points, float(last_ma)

    def _exponential_smoothing_forecast(
        self,
        historical: pd.DataFrame,
        horizon: int,
        alpha: float = 0.3,
    ) -> tuple[list[ForecastPoint], float]:
        """Exponential smoothing forecast."""
        values = historical["quantity"].values.astype(float)
        smoothed = [values[0]]
        for t in range(1, len(values)):
            smoothed.append(alpha * values[t] + (1 - alpha) * smoothed[-1])

        last_smoothed = smoothed[-1]

        # Calculate residuals for confidence intervals
        residuals = values - np.array(smoothed)
        std = np.std(residuals)

        points = []
        last_date = historical["date"].iloc[-1]
        for i in range(1, horizon + 1):
            date = last_date + timedelta(days=i)
            points.append(
                ForecastPoint(
                    date=date.to_pydatetime(),
                    predicted_demand=max(0, round(last_smoothed, 2)),
                    lower_bound=max(0, round(last_smoothed - 1.96 * std, 2)),
                    upper_bound=round(last_smoothed + 1.96 * std, 2),
                )
            )

        return points, float(last_smoothed)

    def _ai_forecast(
        self,
        historical: pd.DataFrame,
        horizon: int,
        product_info: dict,
        confidence_interval: float,
    ) -> tuple[list[ForecastPoint], float, str]:
        """
        Use OpenAI to generate forecasts considering patterns,
        seasonality, and context that statistical methods miss.
        """
        # Prepare historical data for the prompt
        recent_30 = historical.tail(30)
        data_str = "\n".join(
            f"  {row['date'].strftime('%Y-%m-%d')}: {int(row['quantity'])} units, ${safe_float(row['revenue']):.2f}"
            for _, row in recent_30.iterrows()
        )

        # Calculate basic stats for context
        avg_30 = safe_float(recent_30["quantity"].mean())
        avg_90 = safe_float(historical.tail(90)["quantity"].mean())
        std_90 = safe_float(historical.tail(90)["quantity"].std(), default=avg_90 * 0.3)
        total_90 = safe_float(historical.tail(90)["quantity"].sum())

        # Detect day-of-week patterns
        dow_pattern = historical.groupby(historical["date"].dt.dayofweek)["quantity"].mean()
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        dow_str = ", ".join(f"{dow_names[i]}: {v:.1f}" for i, v in dow_pattern.items())

        prompt = f"""You are a retail demand forecasting expert. Analyze the following historical data and generate a {horizon}-day demand forecast.

PRODUCT: {product_info.get('name', 'Unknown')} (SKU: {product_info.get('sku', 'N/A')}, Category: {product_info.get('category', 'N/A')})

STATISTICS:
- 30-day avg daily demand: {avg_30:.1f} units
- 90-day avg daily demand: {avg_90:.1f} units
- 90-day demand std dev: {std_90:.1f} units
- 90-day total demand: {int(total_90)} units
- Day-of-week pattern: {dow_str}

LAST 30 DAYS OF DATA:
{data_str}

Generate a JSON forecast with this exact structure:
{{
    "predicted_avg_daily": <float>,
    "trend_direction": "increasing" | "decreasing" | "stable",
    "trend_percentage": <float, e.g. 0.15 for 15% increase>,
    "reasoning": "<brief explanation of your forecast>",
    "daily_forecasts": [
        {{
            "day_offset": 1,
            "date": "YYYY-MM-DD",
            "predicted_demand": <float>,
            "lower_bound": <float>,
            "upper_bound": <float>
        }}
    ]
}}

Rules:
- The date for day_offset N is {horizon} days from the last historical date ({historical['date'].iloc[-1].strftime('%Y-%m-%d')})
- Generate exactly {horizon} daily forecast points
- Consider day-of-week patterns (weekends may differ from weekdays)
- Lower/upper bounds should reflect {confidence_interval:.0%} confidence interval
- Demand cannot be negative; use 0 as minimum
- Be realistic - don't predict extreme changes without strong evidence
- Return ONLY valid JSON"""

        messages = [
            {"role": "system", "content": "You are a precise demand forecasting AI. Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        result = self.openai.chat_completion_json(messages=messages, temperature=0.15)

        # Parse the forecast points
        points = []
        for fc in result.get("daily_forecasts", [])[:horizon]:
            points.append(
                ForecastPoint(
                    date=datetime.strptime(fc["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    predicted_demand=max(0, safe_float(fc["predicted_demand"])),
                    lower_bound=max(0, safe_float(fc["lower_bound"])),
                    upper_bound=safe_float(fc["upper_bound"]),
                )
            )

        # Fill any missing days
        if len(points) < horizon:
            last_date = historical["date"].iloc[-1]
            avg_pred = safe_float(result.get("predicted_avg_daily", avg_30))
            for i in range(len(points) + 1, horizon + 1):
                date = last_date + timedelta(days=i)
                points.append(
                    ForecastPoint(
                        date=date.to_pydatetime(),
                        predicted_demand=max(0, round(avg_pred, 2)),
                        lower_bound=max(0, round(avg_pred - 1.96 * std_90, 2)),
                        upper_bound=round(avg_pred + 1.96 * std_90, 2),
                    )
                )

        return (
            points,
            safe_float(result.get("predicted_avg_daily", avg_30)),
            result.get("reasoning", "AI-generated forecast"),
        )

    def generate_forecast(self, request: ForecastRequest) -> ForecastResponse:
        """
        Generate a demand forecast using the specified method.

        Args:
            request: ForecastRequest with product_id, method, horizon, etc.

        Returns:
            ForecastResponse with predicted demand points and metadata
        """
        logger.info(
            "generating_forecast",
            product_id=request.product_id,
            method=request.method.value,
            horizon=request.horizon_days,
        )

        # Fetch data
        historical = self._get_historical_demand(request.product_id)
        product_info = self._get_product_info(request.product_id)

        if len(historical) < 7:
            raise ForecastingError(
                f"Insufficient historical data: {len(historical)} days available, minimum 7 required",
                details={"product_id": request.product_id, "days_available": len(historical)},
            )

        # Generate forecast based on method
        trend_direction = "stable"
        trend_percentage = 0.0
        reasoning = ""

        if request.method == ForecastMethod.MOVING_AVERAGE:
            points, avg_daily = self._moving_average_forecast(
                historical, request.horizon_days
            )
            reasoning = f"7-day moving average forecast based on {len(historical)} days of historical data."

        elif request.method == ForecastMethod.EXPONENTIAL_SMOOTHING:
            points, avg_daily = self._exponential_smoothing_forecast(
                historical, request.horizon_days
            )
            reasoning = f"Exponential smoothing (α=0.3) forecast based on {len(historical)} days of historical data."

        elif request.method == ForecastMethod.AI_FORECAST:
            points, avg_daily, reasoning = self._ai_forecast(
                historical,
                request.horizon_days,
                product_info,
                request.confidence_interval,
            )
            # Parse trend from AI response if available
            # (already embedded in reasoning)

        elif request.method == ForecastMethod.SEASONAL_DECOMPOSITION:
            # Fallback to AI forecast for seasonal (it handles seasonality)
            points, avg_daily, reasoning = self._ai_forecast(
                historical,
                request.horizon_days,
                product_info,
                request.confidence_interval,
            )
            reasoning = f"Seasonal-aware AI forecast: {reasoning}"

        else:
            points, avg_daily = self._moving_average_forecast(
                historical, request.horizon_days
            )

        # Calculate trend from historical data
        recent = historical.tail(30)["quantity"].mean()
        older = historical.tail(90).head(60)["quantity"].mean() if len(historical) >= 90 else recent
        if older > 0:
            trend_percentage = (recent - older) / older
            if trend_percentage > 0.05:
                trend_direction = "increasing"
            elif trend_percentage < -0.05:
                trend_direction = "decreasing"

        # Calculate totals
        predicted_total = sum(p.predicted_demand for p in points)
        historical_avg = safe_float(historical["quantity"].mean())

        # Generate forecast ID
        import uuid
        forecast_id = str(uuid.uuid4())

        # Store forecast in BigQuery
        self._store_forecast(forecast_id, request, points, reasoning)

        logger.info(
            "forecast_generated",
            forecast_id=forecast_id,
            product_id=request.product_id,
            predicted_total=round(predicted_total, 2),
            trend=trend_direction,
        )

        return ForecastResponse(
            forecast_id=forecast_id,
            product_id=request.product_id,
            product_name=product_info.get("name", request.product_id),
            method=request.method,
            horizon_days=request.horizon_days,
            confidence_interval=request.confidence_interval,
            historical_avg_daily=round(historical_avg, 2),
            predicted_avg_daily=round(avg_daily, 2),
            predicted_total=round(predicted_total, 2),
            trend_direction=trend_direction,
            trend_percentage=round(trend_percentage, 4),
            points=points,
            generated_at=now_utc(),
        )

    def _store_forecast(
        self,
        forecast_id: str,
        request: ForecastRequest,
        points: list[ForecastPoint],
        reasoning: str,
    ) -> None:
        """Persist forecast results to BigQuery."""
        rows = [
            {
                "forecast_id": forecast_id,
                "product_id": request.product_id,
                "method": request.method.value,
                "horizon_days": request.horizon_days,
                "confidence_interval": request.confidence_interval,
                "forecast_date": points[0].date,
                "predicted_total": sum(p.predicted_demand for p in points),
                "trend_direction": "stable",
                "reasoning": reasoning,
                "created_at": now_utc().isoformat(),
                "points_json": json.dumps(
                    [
                        {
                            "date": p.date.isoformat(),
                            "predicted_demand": p.predicted_demand,
                            "lower_bound": p.lower_bound,
                            "upper_bound": p.upper_bound,
                        }
                        for p in points
                    ]
                ),
            }
        ]

        try:
            self.bq.insert_rows("forecasts", rows)
        except Exception as e:
            logger.warning("forecast_storage_failed", error=str(e), forecast_id=forecast_id)
            # Non-fatal: forecast is still returned to user

    def get_stored_forecast(self, forecast_id: str) -> Optional[dict]:
        """Retrieve a previously generated forecast."""
        query = f"""
        SELECT * FROM `{self.bq.full_table_name('forecasts')}`
        WHERE forecast_id = @forecast_id
        """
        params = [ScalarQueryParameter("forecast_id", "STRING", forecast_id)]
        df = self.bq.run_query(query, params=params)
        if df.empty:
            return None
        return df.iloc[0].to_dict()