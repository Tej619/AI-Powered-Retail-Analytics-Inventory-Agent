import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from google.cloud.bigquery import ScalarQueryParameter

from app.models.enums import InsightType, ProductCategory
from app.models.schemas import (
    CustomerInsight,
    ExtractedData,
    InsightBatch,
    UnstructuredReport,
)
from app.services.bigquery_service import BigQueryService, get_bigquery_service
from app.services.openai_service import OpenAIService, get_openai_service
from app.utils.helpers import now_utc
from app.utils.logger import get_logger

logger = get_logger(__name__)


class InsightService:
    """Generates customer insights from data and unstructured text."""

    def __init__(
        self,
        bq: Optional[BigQueryService] = None,
        openai: Optional[OpenAIService] = None,
    ) -> None:
        self.bq = bq or get_bigquery_service()
        self.openai = openai or get_openai_service()

    def extract_from_unstructured(self, report: UnstructuredReport) -> ExtractedData:
        """
        Extract structured data from an unstructured retail report
        using OpenAI function calling for reliable extraction.
        """
        logger.info(
            "extracting_from_unstructured",
            source=report.source,
            text_length=len(report.raw_text),
        )

        extraction_schema = {
            "type": "object",
            "properties": {
                "products_mentioned": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of product names or SKUs mentioned",
                },
                "sales_figures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "quantity": {"type": "number"},
                            "revenue": {"type": "number"},
                            "period": {"type": "string"},
                            "channel": {"type": "string"},
                        },
                    },
                    "description": "Any sales figures mentioned",
                },
                "inventory_updates": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product": {"type": "string"},
                            "current_stock": {"type": "number"},
                            "status": {"type": "string"},
                            "location": {"type": "string"},
                        },
                    },
                    "description": "Inventory level updates mentioned",
                },
                "key_metrics": {
                    "type": "object",
                    "properties": {
                        "total_revenue": {"type": "number"},
                        "total_units_sold": {"type": "number"},
                        "average_order_value": {"type": "number"},
                        "conversion_rate": {"type": "number"},
                        "customer_count": {"type": "number"},
                    },
                    "description": "Key performance metrics extracted",
                },
                "action_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Actionable items or recommendations mentioned",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "negative", "neutral"],
                    "description": "Overall sentiment of the report",
                },
                "summary": {
                    "type": "string",
                    "description": "A concise summary of the report in 2-3 sentences",
                },
            },
            "required": ["products_mentioned", "sales_figures", "inventory_updates",
                         "key_metrics", "action_items", "sentiment", "summary"],
        }

        system_prompt = """You are a retail data extraction specialist. 
Extract structured information from the provided retail report.
Be precise with numbers - only extract figures explicitly stated in the text.
If a field has no data, use empty arrays/objects rather than making up values.
Pay attention to product names, quantities, monetary amounts, and dates."""

        result = self.openai.extract_with_schema(
            text=report.raw_text,
            system_prompt=system_prompt,
            output_schema=extraction_schema,
        )

        logger.info(
            "extraction_complete",
            products=len(result.get("products_mentioned", [])),
            sales_figures=len(result.get("sales_figures", [])),
            sentiment=result.get("sentiment"),
        )

        return ExtractedData(**result)

    def generate_insights(self, days: int = 30, limit: int = 10) -> InsightBatch:
        """
        Analyze recent sales and inventory data to generate
        actionable customer insights using AI.
        """
        logger.info("generating_insights", days=days, limit=limit)

        # Fetch recent performance data
        performance_data = self._fetch_performance_data(days)
        inventory_data = self._fetch_inventory_status()
        trend_data = self._fetch_trend_data(days)

        if performance_data.empty and inventory_data.empty:
            return InsightBatch(
                insights=[],
                total_count=0,
                generated_at=now_utc(),
            )

        # Use AI to generate insights
        insights = self._ai_generate_insights(
            performance_data, inventory_data, trend_data, limit
        )

        # Store insights
        self._store_insights(insights)

        return InsightBatch(
            insights=insights,
            total_count=len(insights),
            generated_at=now_utc(),
        )

    def _fetch_performance_data(self, days: int) -> pd.DataFrame:
        """Fetch recent product performance metrics."""
        query = f"""
        SELECT
            p.product_id, p.name, p.sku, p.category,
            SUM(s.quantity) as total_units,
            SUM(s.total_amount) as total_revenue,
            COUNT(DISTINCT DATE(s.sale_date)) as days_sold,
            SUM(s.quantity) / NULLIF(COUNT(DISTINCT DATE(s.sale_date)), 0) as avg_daily_units,
            COUNT(DISTINCT s.customer_id) as unique_customers,
            AVG(s.total_amount) as avg_order_value
        FROM `{self.bq.full_table_name('sales')}` s
        JOIN `{self.bq.full_table_name('products')}` p ON s.product_id = p.product_id
        WHERE s.sale_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
        GROUP BY p.product_id, p.name, p.sku, p.category
        HAVING days_sold >= 3
        ORDER BY total_revenue DESC
        LIMIT 50
        """

        params = [ScalarQueryParameter("days", "INT64", days)]
        return self.bq.run_query(query, params=params)

    def _fetch_inventory_status(self) -> pd.DataFrame:
        """Fetch current inventory status for all products."""
        query = f"""
        SELECT
            i.product_id, p.name, p.category,
            i.quantity_on_hand, i.reorder_point, i.reorder_quantity,
            CASE
                WHEN i.quantity_on_hand = 0 THEN 'out_of_stock'
                WHEN i.quantity_on_hand <= i.reorder_point THEN 'low_stock'
                WHEN i.quantity_on_hand > i.reorder_point * 3 THEN 'overstocked'
                ELSE 'in_stock'
            END as status
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p ON i.product_id = p.product_id
        WHERE i.quantity_on_hand <= i.reorder_point OR i.quantity_on_hand = 0
        ORDER BY i.quantity_on_hand ASC
        LIMIT 30
        """

        return self.bq.run_query(query)

    def _fetch_trend_data(self, days: int) -> pd.DataFrame:
        """Fetch week-over-week trend data."""
        query = f"""
        WITH weekly AS (
            SELECT
                p.product_id, p.name, p.category,
                DATE_TRUNC(s.sale_date, WEEK) as week,
                SUM(s.quantity) as weekly_units,
                SUM(s.total_amount) as weekly_revenue
            FROM `{self.bq.full_table_name('sales')}` s
            JOIN `{self.bq.full_table_name('products')}` p ON s.product_id = p.product_id
            WHERE s.sale_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
            GROUP BY p.product_id, p.name, p.category, DATE_TRUNC(s.sale_date, WEEK)
        ),
        with_lag AS (
            SELECT
                *,
                LAG(weekly_units) OVER (PARTITION BY product_id ORDER BY week) as prev_units,
                LAG(weekly_revenue) OVER (PARTITION BY product_id ORDER BY week) as prev_revenue
            FROM weekly
        )
        SELECT
            product_id, name, category,
            week, weekly_units, weekly_revenue,
            prev_units, prev_revenue,
            CASE
                WHEN prev_units > 0 THEN
                    (weekly_units - prev_units) / prev_units
                ELSE NULL
            END as units_change_pct,
            CASE
                WHEN prev_revenue > 0 THEN
                    (weekly_revenue - prev_revenue) / prev_revenue
                ELSE NULL
            END as revenue_change_pct
        FROM with_lag
        WHERE prev_units IS NOT NULL
        ORDER BY ABS(units_change_pct) DESC
        LIMIT 30
        """

        params = [ScalarQueryParameter("days", "INT64", days)]
        return self.bq.run_query(query, params=params)

    def _ai_generate_insights(
        self,
        performance: pd.DataFrame,
        inventory: pd.DataFrame,
        trends: pd.DataFrame,
        limit: int,
    ) -> list[CustomerInsight]:
        """Use OpenAI to analyze data and generate structured insights."""

        perf_str = performance.to_json(orient="records", default_handler=str)[:3000] if not performance.empty else "No data"
        inv_str = inventory.to_json(orient="records", default_handler=str)[:2000] if not inventory.empty else "No data"
        trend_str = trends.to_json(orient="records", default_handler=str)[:2000] if not trends.empty else "No data"

        insight_schema = {
            "type": "object",
            "properties": {
                "insights": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "insight_type": {
                                "type": "string",
                                "enum": [
                                    "demand_spike", "demand_drop", "seasonal_pattern",
                                    "stockout_risk", "overstock_risk", "pricing_opportunity",
                                    "customer_segment", "trend_change",
                                ],
                            },
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "confidence": {"type": "number"},
                            "product_ids": {"type": "array", "items": {"type": "string"}},
                            "category": {"type": "string"},
                            "metric_value": {"type": "number"},
                            "metric_name": {"type": "string"},
                            "recommendation": {"type": "string"},
                        },
                        "required": ["insight_type", "title", "description", "confidence"],
                    },
                },
            },
            "required": ["insights"],
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a retail analytics AI that generates actionable business insights. "
                    "Analyze the data provided and generate the most important insights. "
                    "Each insight should be specific, data-backed, and include a recommendation. "
                    f"Generate at most {limit} insights. Focus on the highest-impact findings."
                ),
            },
            {
                "role": "user",
                "content": f"""Analyze this retail data and generate insights:

RECENT PERFORMANCE (top products):
{perf_str}

INVENTORY ALERTS (low/out of stock):
{inv_str}

WEEK-OVER-WEEK TRENDS:
{trend_str}""",
            },
        ]

        try:
            result = self.openai.extract_with_schema(
                text=messages[1]["content"],
                system_prompt=messages[0]["content"],
                output_schema=insight_schema,
            )
        except Exception as e:
            logger.error("ai_insight_generation_failed", error=str(e))
            return []

        insights = []
        for item in result.get("insights", [])[:limit]:
            insights.append(
                CustomerInsight(
                    insight_id=str(uuid.uuid4()),
                    insight_type=InsightType(item["insight_type"]),
                    title=item["title"],
                    description=item["description"],
                    confidence=float(item.get("confidence", 0.7)),
                    product_ids=item.get("product_ids", []),
                    category=ProductCategory(item["category"]) if item.get("category") else None,
                    metric_value=item.get("metric_value"),
                    metric_name=item.get("metric_name"),
                    recommendation=item.get("recommendation"),
                    created_at=now_utc(),
                )
            )

        return insights

    def _store_insights(self, insights: list[CustomerInsight]) -> None:
        """Store generated insights in BigQuery."""
        if not insights:
            return

        rows = [
            {
                "insight_id": i.insight_id,
                "insight_type": i.insight_type.value,
                "title": i.title,
                "description": i.description,
                "confidence": i.confidence,
                "product_ids": json.dumps(i.product_ids),
                "category": i.category.value if i.category else None,
                "metric_value": i.metric_value,
                "metric_name": i.metric_name,
                "recommendation": i.recommendation,
                "created_at": i.created_at.isoformat(),
            }
            for i in insights
        ]

        try:
            self.bq.insert_rows("customer_insights", rows)
        except Exception as e:
            logger.warning("insight_storage_failed", error=str(e))