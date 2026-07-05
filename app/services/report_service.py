import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from google.cloud.bigquery import ScalarQueryParameter

from app.models.enums import ReportStatus, ReportType
from app.models.schemas import ReportRequest, ReportResponse
from app.services.bigquery_service import BigQueryService, get_bigquery_service
from app.services.openai_service import OpenAIService, get_openai_service
from app.utils.errors import BigQueryError
from app.utils.helpers import now_utc
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ReportService:
    """Automated report generation service."""

    def __init__(
        self,
        bq: Optional[BigQueryService] = None,
        openai: Optional[OpenAIService] = None,
    ) -> None:
        self.bq = bq or get_bigquery_service()
        self.openai = openai or get_openai_service()

    def create_report(self, request: ReportRequest) -> ReportResponse:
        """
        Generate a report of the specified type.

        Orchestrates data fetching, analysis, and narrative generation.
        """
        report_id = str(uuid.uuid4())
        logger.info("creating_report", report_id=report_id, type=request.report_type.value)

        try:
            # Fetch data based on report type
            if request.report_type == ReportType.INVENTORY_SUMMARY:
                content = self._generate_inventory_report(request.parameters)
            elif request.report_type == ReportType.SALES_PERFORMANCE:
                content = self._generate_sales_report(request.parameters)
            elif request.report_type == ReportType.DEMAND_FORECAST:
                content = self._generate_forecast_report(request.parameters)
            elif request.report_type == ReportType.CUSTOMER_INSIGHTS:
                content = self._generate_insights_report(request.parameters)
            elif request.report_type == ReportType.REPLENISHMENT:
                content = self._generate_replenishment_report(request.parameters)
            elif request.report_type == ReportType.ANOMALY_DETECTION:
                content = self._generate_anomaly_report(request.parameters)
            else:
                content = {"error": f"Unknown report type: {request.report_type}"}

            # Generate AI narrative summary
            summary = self._generate_narrative(request.report_type.value, content)

            # Store report
            self._store_report(report_id, request, content, summary, ReportStatus.COMPLETED)

            return ReportResponse(
                report_id=report_id,
                report_type=request.report_type,
                title=request.title,
                status=ReportStatus.COMPLETED,
                content=content,
                summary=summary,
                created_at=now_utc(),
                completed_at=now_utc(),
            )

        except Exception as e:
            logger.error("report_generation_failed", report_id=report_id, error=str(e))
            self._store_report(
                report_id, request, None, None,
                ReportStatus.FAILED, str(e),
            )
            return ReportResponse(
                report_id=report_id,
                report_type=request.report_type,
                title=request.title,
                status=ReportStatus.FAILED,
                error_message=str(e),
                created_at=now_utc(),
            )

    def _generate_inventory_report(self, params: dict) -> dict[str, Any]:
        """Generate inventory summary report data."""
        store_id = params.get("store_id")

        # Overall summary
        summary_query = f"""
        SELECT
            COUNT(DISTINCT i.product_id) as total_products,
            COUNTIF(i.quantity_on_hand = 0) as out_of_stock_count,
            COUNTIF(i.quantity_on_hand > 0 AND i.quantity_on_hand <= i.reorder_point) as low_stock_count,
            COUNTIF(i.quantity_on_hand > i.reorder_point * 3) as overstocked_count,
            SUM(i.quantity_on_hand * p.unit_cost) as total_inventory_value,
            AVG(i.quantity_on_hand) as avg_stock_level
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p ON i.product_id = p.product_id
        {"WHERE i.store_id = @store_id" if store_id else ""}
        """

        query_params = []
        if store_id:
            query_params.append(ScalarQueryParameter("store_id", "STRING", store_id))

        summary_df = self.bq.run_query(summary_query, params=query_params or None)

        # Category breakdown
        category_query = f"""
        SELECT
            p.category,
            COUNT(DISTINCT i.product_id) as product_count,
            SUM(i.quantity_on_hand) as total_units,
            SUM(i.quantity_on_hand * p.unit_cost) as total_value,
            COUNTIF(i.quantity_on_hand <= i.reorder_point) as items_below_reorder
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p ON i.product_id = p.product_id
        {"WHERE i.store_id = @store_id" if store_id else ""}
        GROUP BY p.category
        ORDER BY total_value DESC
        """

        category_df = self.bq.run_query(category_query, params=query_params or None)

        # Top low-stock items
        low_stock_query = f"""
        SELECT
            p.product_id, p.name, p.sku, p.category,
            i.quantity_on_hand, i.reorder_point, i.reorder_quantity,
            i.store_id
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p ON i.product_id = p.product_id
        WHERE i.quantity_on_hand <= i.reorder_point
            {"AND i.store_id = @store_id" if store_id else ""}
        ORDER BY i.quantity_on_hand ASC
        LIMIT 20
        """

        low_stock_df = self.bq.run_query(low_stock_query, params=query_params or None)

        return {
            "summary": summary_df.to_dict(orient="records")[0] if not summary_df.empty else {},
            "by_category": category_df.to_dict(orient="records"),
            "low_stock_items": low_stock_df.to_dict(orient="records"),
            "generated_at": now_utc().isoformat(),
        }

    def _generate_sales_report(self, params: dict) -> dict[str, Any]:
        """Generate sales performance report data."""
        days = params.get("days", 30)
        category = params.get("category")

        where_clauses = [f"s.sale_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)"]
        query_params = []

        if category:
            where_clauses.append("p.category = @category")
            query_params.append(ScalarQueryParameter("category", "STRING", category))

        where_sql = " AND ".join(where_clauses)

        # Top products
        top_products_query = f"""
        SELECT
            p.product_id, p.name, p.sku, p.category,
            SUM(s.quantity) as total_units,
            SUM(s.total_amount) as total_revenue,
            SUM(s.total_amount) / NULLIF(SUM(s.quantity), 0) as avg_unit_revenue,
            COUNT(DISTINCT DATE(s.sale_date)) as days_sold,
            SUM(s.quantity) / COUNT(DISTINCT DATE(s.sale_date)) as avg_daily_units
        FROM `{self.bq.full_table_name('sales')}` s
        JOIN `{self.bq.full_table_name('products')}` p ON s.product_id = p.product_id
        WHERE {where_sql}
        GROUP BY p.product_id, p.name, p.sku, p.category
        ORDER BY total_revenue DESC
        LIMIT 20
        """

        top_df = self.bq.run_query(top_products_query, params=query_params or None)

        # Daily trend
        daily_query = f"""
        SELECT
            DATE(s.sale_date) as date,
            SUM(s.quantity) as total_units,
            SUM(s.total_amount) as total_revenue,
            COUNT(DISTINCT s.sale_id) as transaction_count,
            COUNT(DISTINCT s.customer_id) as unique_customers
        FROM `{self.bq.full_table_name('sales')}` s
        JOIN `{self.bq.full_table_name('products')}` p ON s.product_id = p.product_id
        WHERE {where_sql}
        GROUP BY DATE(s.sale_date)
        ORDER BY date
        """

        daily_df = self.bq.run_query(daily_query, params=query_params or None)

        # Channel breakdown
        channel_query = f"""
        SELECT
            s.channel,
            SUM(s.quantity) as total_units,
            SUM(s.total_amount) as total_revenue,
            COUNT(DISTINCT s.sale_id) as transaction_count,
            AVG(s.total_amount) as avg_transaction_value
        FROM `{self.bq.full_table_name('sales')}` s
        JOIN `{self.bq.full_table_name('products')}` p ON s.product_id = p.product_id
        WHERE {where_sql}
        GROUP BY s.channel
        """

        channel_df = self.bq.run_query(channel_query, params=query_params or None)

        # Compute overall stats
        total_revenue = safe_total(top_df, "total_revenue")
        total_units = safe_total(top_df, "total_units")

        return {
            "period_days": days,
            "total_revenue": total_revenue,
            "total_units_sold": total_units,
            "top_products": top_df.to_dict(orient="records"),
            "daily_trend": daily_df.to_dict(orient="records"),
            "by_channel": channel_df.to_dict(orient="records"),
            "generated_at": now_utc().isoformat(),
        }

    def _generate_forecast_report(self, params: dict) -> dict[str, Any]:
        """Generate demand forecast summary report."""
        days = params.get("days", 30)

        query = f"""
        SELECT
            f.product_id, p.name, p.category,
            f.method, f.horizon_days, f.predicted_total,
            f.trend_direction, f.reasoning,
            f.created_at
        FROM `{self.bq.full_table_name('forecasts')}` f
        JOIN `{self.bq.full_table_name('products')}` p ON f.product_id = p.product_id
        WHERE f.created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        ORDER BY f.created_at DESC
        LIMIT 50
        """

        df = self.bq.run_query(query)
        return {
            "recent_forecasts": df.to_dict(orient="records"),
            "total_forecasts": len(df),
            "generated_at": now_utc().isoformat(),
        }

    def _generate_insights_report(self, params: dict) -> dict[str, Any]:
        """Generate customer insights report."""
        days = params.get("days", 30)

        query = f"""
        SELECT * FROM `{self.bq.full_table_name('customer_insights')}`
        WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        ORDER BY created_at DESC
        LIMIT 50
        """

        df = self.bq.run_query(query)
        return {
            "insights": df.to_dict(orient="records"),
            "total_count": len(df),
            "by_type": df["insight_type"].value_counts().to_dict() if not df.empty else {},
            "generated_at": now_utc().isoformat(),
        }

    def _generate_replenishment_report(self, params: dict) -> dict[str, Any]:
        """Generate replenishment recommendations report."""
        query = f"""
        SELECT
            p.product_id, p.name, p.sku, p.category, p.unit_cost,
            i.store_id,
            i.quantity_on_hand as current_stock,
            i.reorder_point,
            i.reorder_quantity,
            i.quantity_on_hand - i.reorder_point as deficit,
            CASE
                WHEN i.quantity_on_hand <= i.reorder_point THEN
                    i.reorder_quantity - i.quantity_on_hand
                ELSE 0
            END as recommended_order_qty,
            (i.reorder_quantity - i.quantity_on_hand) * p.unit_cost as estimated_cost
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p ON i.product_id = p.product_id
        WHERE i.quantity_on_hand <= i.reorder_point
        ORDER BY deficit ASC
        """

        df = self.bq.run_query(query)
        total_cost = df["estimated_cost"].sum() if not df.empty else 0

        return {
            "items_needing_reorder": df.to_dict(orient="records"),
            "total_items": len(df),
            "total_estimated_cost": float(total_cost),
            "generated_at": now_utc().isoformat(),
        }

    def _generate_anomaly_report(self, params: dict) -> dict[str, Any]:
        """Generate anomaly detection report using statistical methods."""
        query = f"""
        WITH daily_sales AS (
            SELECT
                product_id,
                DATE(sale_date) as date,
                SUM(quantity) as daily_qty,
                SUM(total_amount) as daily_revenue
            FROM `{self.bq.full_table_name('sales')}`
            WHERE sale_date >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
            GROUP BY product_id, DATE(sale_date)
        ),
        stats AS (
            SELECT
                product_id,
                AVG(daily_qty) as avg_qty,
                STDDEV(daily_qty) as std_qty,
                AVG(daily_revenue) as avg_rev,
                STDDEV(daily_revenue) as std_rev
            FROM daily_sales
            GROUP BY product_id
            HAVING COUNT(*) >= 14
        ),
        anomalies AS (
            SELECT
                d.product_id,
                p.name,
                p.category,
                d.date,
                d.daily_qty,
                s.avg_qty,
                s.std_qty,
                (d.daily_qty - s.avg_qty) / NULLIF(s.std_qty, 0) as z_score_qty,
                d.daily_revenue,
                (d.daily_revenue - s.avg_rev) / NULLIF(s.std_rev, 0) as z_score_rev
            FROM daily_sales d
            JOIN stats s ON d.product_id = s.product_id
            JOIN `{self.bq.full_table_name('products')}` p ON d.product_id = p.product_id
            WHERE
                ABS((d.daily_qty - s.avg_qty) / NULLIF(s.std_qty, 0)) > 2.5
                OR ABS((d.daily_revenue - s.avg_rev) / NULLIF(s.std_rev, 0)) > 2.5
        )
        SELECT * FROM anomalies
        ORDER BY ABS(z_score_qty) DESC
        LIMIT 50
        """

        df = self.bq.run_query(query)
        return {
            "anomalies": df.to_dict(orient="records"),
            "total_anomalies": len(df),
            "date_range": "last_60_days",
            "threshold": "2.5_standard_deviations",
            "generated_at": now_utc().isoformat(),
        }

    def _generate_narrative(self, report_type: str, content: dict) -> str:
        """Use OpenAI to generate a human-readable narrative summary of the report."""
        # Truncate content for the prompt
        content_str = json.dumps(content, indent=2, default=str)[:4000]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a retail analytics expert writing an executive summary. "
                    "Be concise, data-driven, and actionable. Use bullet points for key findings. "
                    "Include specific numbers. Keep it under 300 words."
                ),
            },
            {
                "role": "user",
                "content": f"Write an executive summary for this {report_type} report:\n\n{content_str}",
            },
        ]

        try:
            response = self.openai.chat_completion(
                messages=messages,
                max_tokens=600,
                temperature=0.3,
            )
            return response.choices[0].message.content or "Report generated successfully."
        except Exception as e:
            logger.warning("narrative_generation_failed", error=str(e))
            return "Report generated. AI narrative unavailable."

    def _store_report(
        self,
        report_id: str,
        request: ReportRequest,
        content: Optional[dict],
        summary: Optional[str],
        status: ReportStatus,
        error: Optional[str] = None,
    ) -> None:
        """Persist report to BigQuery."""
        row = {
            "report_id": report_id,
            "report_type": request.report_type.value,
            "title": request.title,
            "status": status.value,
            "content_json": json.dumps(content, default=str) if content else None,
            "summary": summary,
            "error_message": error,
            "parameters": json.dumps(request.parameters),
            "created_at": now_utc().isoformat(),
            "completed_at": now_utc().isoformat() if status == ReportStatus.COMPLETED else None,
        }

        try:
            self.bq.insert_rows("reports", [row])
        except Exception as e:
            logger.warning("report_storage_failed", error=str(e), report_id=report_id)

    def get_report(self, report_id: str) -> Optional[ReportResponse]:
        """Retrieve a stored report."""
        query = f"""
        SELECT * FROM `{self.bq.full_table_name('reports')}`
        WHERE report_id = @report_id
        """
        params = [ScalarQueryParameter("report_id", "STRING", report_id)]
        df = self.bq.run_query(query, params=params)

        if df.empty:
            return None

        row = df.iloc[0]
        content = json.loads(row["content_json"]) if row.get("content_json") else None

        return ReportResponse(
            report_id=str(row["report_id"]),
            report_type=ReportType(row["report_type"]),
            title=str(row["title"]),
            status=ReportStatus(row["status"]),
            content=content,
            summary=row.get("summary"),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            completed_at=row.get("completed_at"),
        )


def safe_total(df: pd.DataFrame, col: str) -> float:
    """Safely sum a column."""
    if df.empty or col not in df.columns:
        return 0.0
    try:
        return float(df[col].sum())
    except (TypeError, ValueError):
        return 0.0