from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from google.cloud.bigquery import ScalarQueryParameter

from app.models.enums import InventoryStatus
from app.models.schemas import (
    InventoryResponse,
    InventorySummary,
    ReorderPointRequest,
    ReorderPointResponse,
)
from app.services.bigquery_service import BigQueryService, get_bigquery_service
from app.utils.errors import BigQueryError, NotFoundError
from app.utils.helpers import now_utc, safe_float
from app.utils.logger import get_logger

logger = get_logger(__name__)


class InventoryService:
    """Handles inventory tracking and management operations."""

    def __init__(self, bq: Optional[BigQueryService] = None) -> None:
        self.bq = bq or get_bigquery_service()

    def _calculate_status(self, qty_on_hand: int, reorder_point: int, reorder_qty: int) -> InventoryStatus:
        """Determine inventory status based on quantities."""
        if qty_on_hand == 0:
            return InventoryStatus.OUT_OF_STOCK
        if qty_on_hand <= reorder_point:
            return InventoryStatus.LOW_STOCK
        if qty_on_hand > reorder_point * 3:  # More than 3x reorder point
            return InventoryStatus.OVERSTOCKED
        return InventoryStatus.IN_STOCK

    def get_inventory_summary(self, store_id: Optional[str] = None) -> InventorySummary:
        """Get aggregate inventory summary."""
        where_clause = f"WHERE store_id = '{store_id}'" if store_id else ""

        query = f"""
        SELECT
            COUNT(DISTINCT i.product_id) as total_products,
            COUNTIF(i.quantity_on_hand = 0) as out_of_stock,
            COUNTIF(i.quantity_on_hand > 0 AND i.quantity_on_hand <= i.reorder_point) as low_stock,
            COUNTIF(i.quantity_on_hand > i.reorder_point * 3) as overstocked,
            SUM(i.quantity_on_hand * p.unit_cost) as total_value
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p
            ON i.product_id = p.product_id
        {where_clause}
        """

        df = self.bq.run_query(query)

        if df.empty:
            return InventorySummary(
                total_products=0,
                in_stock=0,
                low_stock=0,
                out_of_stock=0,
                overstocked=0,
                total_inventory_value=0.0,
                store_id=store_id,
            )

        row = df.iloc[0]
        total = int(row["total_products"])
        oos = int(row["out_of_stock"])
        low = int(row["low_stock"])
        over = int(row["overstocked"])
        in_stock = total - oos - low - over

        return InventorySummary(
            total_products=total,
            in_stock=max(0, in_stock),
            low_stock=low,
            out_of_stock=oos,
            overstocked=over,
            total_inventory_value=safe_float(row["total_value"]),
            store_id=store_id,
        )

    def get_product_inventory(self, product_id: str) -> list[InventoryResponse]:
        """Get inventory records for a specific product across all stores."""
        query = f"""
        SELECT
            i.*,
            p.name as product_name,
            p.sku,
            p.category,
            p.unit_cost,
            p.unit_price
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p
            ON i.product_id = p.product_id
        WHERE i.product_id = @product_id
        ORDER BY i.store_id
        """

        params = [ScalarQueryParameter("product_id", "STRING", product_id)]
        df = self.bq.run_query(query, params=params)

        if df.empty:
            raise NotFoundError("Product inventory", product_id)

        results = []
        for _, row in df.iterrows():
            status = self._calculate_status(
                int(row["quantity_on_hand"]),
                int(row["reorder_point"]),
                int(row["reorder_quantity"]),
            )
            results.append(
                InventoryResponse(
                    inventory_id=str(row.get("inventory_id", "")),
                    product_id=product_id,
                    store_id=str(row["store_id"]),
                    quantity_on_hand=int(row["quantity_on_hand"]),
                    quantity_reserved=int(row.get("quantity_reserved", 0)),
                    reorder_point=int(row["reorder_point"]),
                    reorder_quantity=int(row["reorder_quantity"]),
                    warehouse_location=str(row.get("warehouse_location", "")),
                    status=status,
                    last_restocked=row.get("last_restocked"),
                    updated_at=row.get("updated_at", now_utc()),
                )
            )

        return results

    def get_low_stock_items(self, threshold_multiplier: float = 1.0) -> pd.DataFrame:
        """Get all items at or below their reorder point."""
        query = f"""
        SELECT
            i.product_id,
            p.name as product_name,
            p.sku,
            p.category,
            p.unit_price,
            i.store_id,
            i.quantity_on_hand,
            i.reorder_point,
            i.reorder_quantity,
            i.quantity_on_hand - i.reorder_point as units_below_reorder
        FROM `{self.bq.full_table_name('inventory')}` i
        JOIN `{self.bq.full_table_name('products')}` p
            ON i.product_id = p.product_id
        WHERE i.quantity_on_hand <= i.reorder_point * @threshold
        ORDER BY units_below_reorder ASC
        """

        params = [ScalarQueryParameter("threshold", "FLOAT64", threshold_multiplier)]
        return self.bq.run_query(query, params=params)

    def calculate_reorder_point(self, req: ReorderPointRequest) -> ReorderPointResponse:
        """
        Calculate optimal reorder point using statistical methods.

        Formula:
            Reorder Point = (Avg Daily Demand × Lead Time) + Safety Stock
            Safety Stock = Z-score × √(Lead Time × Demand Variance)
        """
        # Fetch historical demand data
        query = f"""
        WITH daily_demand AS (
            SELECT
                DATE(sale_date) as day,
                SUM(quantity) as demand
            FROM `{self.bq.full_table_name('sales')}`
            WHERE product_id = @product_id
                AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 180 DAY)
            GROUP BY DATE(sale_date)
        )
        SELECT
            AVG(demand) as avg_daily_demand,
            STDDEV(demand) as demand_stddev,
            COUNT(*) as days_with_data,
            MAX(demand) as max_daily_demand,
            MIN(demand) as min_daily_demand
        FROM daily_demand
        """

        params = [ScalarQueryParameter("product_id", "STRING", req.product_id)]
        df = self.bq.run_query(query, params=params)

        if df.empty or df.iloc[0]["days_with_data"] < 7:
            raise BigQueryError(
                "Insufficient historical data for reorder point calculation",
                details={"product_id": req.product_id, "days_available": 0},
            )

        row = df.iloc[0]
        avg_demand = safe_float(row["avg_daily_demand"])
        std_dev = safe_float(row["demand_stddev"], default=avg_demand * 0.3)

        # Z-score for service level (approximation using normal distribution)
        z_scores = {
            0.90: 1.28, 0.91: 1.34, 0.92: 1.41, 0.93: 1.48,
            0.94: 1.55, 0.95: 1.645, 0.96: 1.75, 0.97: 1.88,
            0.98: 2.05, 0.99: 2.33, 0.999: 3.09,
        }
        z = z_scores.get(req.service_level, 1.645)

        # Calculate safety stock and reorder point
        safety_stock = z * (std_dev * (req.lead_time_days ** 0.5))
        reorder_point = (avg_demand * req.lead_time_days) + safety_stock

        # Economic Order Quantity (simplified)
        # Get unit cost for EOQ
        cost_query = f"""
        SELECT unit_cost, unit_price FROM `{self.bq.full_table_name('products')}`
        WHERE product_id = @product_id
        """
        cost_df = self.bq.run_query(cost_query, params=params)
        unit_cost = safe_float(cost_df.iloc[0]["unit_cost"]) if not cost_df.empty else 10.0

        # Simplified EOQ: sqrt(2 * D * S / H)
        # D = annual demand, S = ordering cost (assume $50), H = holding cost (assume 25% of unit cost)
        annual_demand = avg_demand * 365
        ordering_cost = 50.0
        holding_cost_pct = 0.25
        holding_cost = unit_cost * holding_cost_pct

        if holding_cost > 0 and annual_demand > 0:
            import math
            eoq = math.sqrt(2 * annual_demand * ordering_cost / holding_cost)
            order_qty = max(int(eoq), int(reorder_point * 0.5))
        else:
            order_qty = int(reorder_point * 2)

        # Get current reorder point
        current_query = f"""
        SELECT reorder_point FROM `{self.bq.full_table_name('inventory')}`
        WHERE product_id = @product_id LIMIT 1
        """
        current_df = self.bq.run_query(current_query, params=params)
        current_rp = int(current_df.iloc[0]["reorder_point"]) if not current_df.empty else 0

        # Get product name
        product_name = cost_df.iloc[0].get("unit_price", "") if not cost_df.empty else req.product_id
        name_query = f"""
        SELECT name FROM `{self.bq.full_table_name('products')}`
        WHERE product_id = @product_id
        """
        name_df = self.bq.run_query(name_query, params=params)
        product_name = str(name_df.iloc[0]["name"]) if not name_df.empty else req.product_id

        # Trend direction
        trend_query = f"""
        WITH recent AS (
            SELECT AVG(demand) as avg_demand
            FROM (
                SELECT DATE(sale_date) as day, SUM(quantity) as demand
                FROM `{self.bq.full_table_name('sales')}`
                WHERE product_id = @product_id
                    AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                GROUP BY DATE(sale_date)
            )
        ),
        older AS (
            SELECT AVG(demand) as avg_demand
            FROM (
                SELECT DATE(sale_date) as day, SUM(quantity) as demand
                FROM `{self.bq.full_table_name('sales')}`
                WHERE product_id = @product_id
                    AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
                    AND sale_date < DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
                GROUP BY DATE(sale_date)
            )
        )
        SELECT
            r.avg_demand as recent_avg,
            o.avg_demand as older_avg,
            CASE
                WHEN o.avg_demand > 0 THEN (r.avg_demand - o.avg_demand) / o.avg_demand
                ELSE 0
            END as trend_pct
        FROM recent r CROSS JOIN older o
        """
        trend_df = self.bq.run_query(trend_query, params=params)

        reasoning = (
            f"Based on {int(row['days_with_data'])} days of historical data: "
            f"average daily demand is {avg_demand:.1f} units (σ={std_dev:.1f}), "
            f"lead time is {req.lead_time_days} days. "
            f"Safety stock of {safety_stock:.0f} units calculated at {req.service_level:.0%} "
            f"service level (z={z:.2f}). "
        )

        if not trend_df.empty:
            recent = safe_float(trend_df.iloc[0]["recent_avg"])
            older = safe_float(trend_df.iloc[0]["older_avg"])
            if older > 0:
                change = (recent - older) / older
                if change > 0.1:
                    reasoning += f"Demand is trending UP {change:.0%} (recent: {recent:.1f}/day vs prior: {older:.1f}/day). "
                elif change < -0.1:
                    reasoning += f"Demand is trending DOWN {abs(change):.0%} (recent: {recent:.1f}/day vs prior: {older:.1f}/day). "
                else:
                    reasoning += f"Demand is STABLE (recent: {recent:.1f}/day vs prior: {older:.1f}/day). "

        if current_rp > 0:
            diff = reorder_point - current_rp
            if abs(diff) > current_rp * 0.2:
                reasoning += (
                    f"Recommended reorder point is {diff:+.0f} units "
                    f"({'higher' if diff > 0 else 'lower'}) than current setting of {current_rp}."
                )
            else:
                reasoning += f"Current reorder point of {current_rp} is close to recommended value."

        return ReorderPointResponse(
            product_id=req.product_id,
            product_name=product_name,
            current_reorder_point=current_rp,
            recommended_reorder_point=int(round(reorder_point)),
            recommended_order_quantity=order_qty,
            safety_stock=int(round(safety_stock)),
            avg_daily_demand=round(avg_demand, 2),
            demand_std_dev=round(std_dev, 2),
            lead_time_days=req.lead_time_days,
            service_level=req.service_level,
            reasoning=reasoning,
        )

    def update_inventory(self, product_id: str, store_id: str, updates: dict) -> bool:
        """Update inventory quantities."""
        set_clauses = []
        params = []
        param_idx = 0

        for field, value in updates.items():
            if field in ("quantity_on_hand", "quantity_reserved", "reorder_point", "reorder_quantity"):
                set_clauses.append(f"{field} = @{field}")
                params.append(ScalarQueryParameter(field, "INT64", int(value)))
                param_idx += 1

        if not set_clauses:
            return False

        set_clauses.append("updated_at = CURRENT_TIMESTAMP()")
        params.append(ScalarQueryParameter("product_id", "STRING", product_id))
        params.append(ScalarQueryParameter("store_id", "STRING", store_id))

        query = f"""
        UPDATE `{self.bq.full_table_name('inventory')}`
        SET {', '.join(set_clauses)}
        WHERE product_id = @product_id AND store_id = @store_id
        """

        self.bq.run_query(query, params=params)
        logger.info("inventory_updated", product_id=product_id, store_id=store_id, fields=list(updates.keys()))
        return True