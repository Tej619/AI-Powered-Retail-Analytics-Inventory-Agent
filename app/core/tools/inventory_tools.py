from typing import Optional, Type

from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

from app.services.bigquery_service import get_bigquery_service
from app.services.inventory_service import InventoryService
from app.utils.helpers import safe_float
from app.utils.logger import get_logger

logger = get_logger(__name__)


class QueryInventoryInput(BaseModel):
    """Input schema for inventory query tool."""
    product_id: Optional[str] = Field(None, description="Specific product ID to query")
    category: Optional[str] = Field(None, description="Filter by product category")
    status: Optional[str] = Field(
        None,
        description="Filter by status: in_stock, low_stock, out_of_stock, overstocked",
    )
    store_id: Optional[str] = Field(None, description="Filter by store/warehouse ID")
    limit: int = Field(20, description="Maximum number of results")


class QueryInventoryTool(BaseTool):
    """Query inventory levels across products and stores."""

    name: str = "query_inventory"
    description: str = (
        "Query current inventory levels. Can filter by product ID, category, "
        "stock status (low_stock, out_of_stock, overstocked), or store. "
        "Returns product names, SKUs, current quantities, and reorder points."
    )
    args_schema: Type[BaseModel] = QueryInventoryInput

    def _run(self, **kwargs) -> str:
        bq = get_bigquery_service()
        conditions = []
        params = []
        param_idx = 0

        if kwargs.get("product_id"):
            conditions.append(f"i.product_id = @p{param_idx}")
            params.append(("p" + str(param_idx), "STRING", kwargs["product_id"]))
            param_idx += 1

        if kwargs.get("category"):
            conditions.append(f"p.category = @p{param_idx}")
            params.append(("p" + str(param_idx), "STRING", kwargs["category"]))
            param_idx += 1

        if kwargs.get("status"):
            status = kwargs["status"]
            if status == "low_stock":
                conditions.append("i.quantity_on_hand > 0 AND i.quantity_on_hand <= i.reorder_point")
            elif status == "out_of_stock":
                conditions.append("i.quantity_on_hand = 0")
            elif status == "overstocked":
                conditions.append("i.quantity_on_hand > i.reorder_point * 3")
            elif status == "in_stock":
                conditions.append(
                    "i.quantity_on_hand > i.reorder_point "
                    "AND i.quantity_on_hand <= i.reorder_point * 3"
                )

        if kwargs.get("store_id"):
            conditions.append(f"i.store_id = @p{param_idx}")
            params.append(("p" + str(param_idx), "STRING", kwargs["store_id"]))
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        from google.cloud.bigquery import ScalarQueryParameter
        bq_params = [ScalarQueryParameter(name, type_, value) for name, type_, value in params]

        query = f"""
        SELECT
            i.product_id, p.name, p.sku, p.category, p.unit_price,
            i.store_id, i.quantity_on_hand, i.reorder_point, i.reorder_quantity,
            i.quantity_on_hand - i.reorder_point as buffer_units,
            CASE
                WHEN i.quantity_on_hand = 0 THEN 'out_of_stock'
                WHEN i.quantity_on_hand <= i.reorder_point THEN 'low_stock'
                WHEN i.quantity_on_hand > i.reorder_point * 3 THEN 'overstocked'
                ELSE 'in_stock'
            END as status
        FROM `{bq.full_table_name('inventory')}` i
        JOIN `{bq.full_table_name('products')}` p ON i.product_id = p.product_id
        {where_clause}
        ORDER BY i.quantity_on_hand ASC
        LIMIT @limit
        """

        bq_params.append(ScalarQueryParameter("limit", "INT64", kwargs.get("limit", 20)))

        df = bq.run_query(query, params=bq_params)

        if df.empty:
            return "No inventory records found matching the criteria."

        # Format results
        result_lines = [f"Found {len(df)} inventory records:\n"]
        for _, row in df.iterrows():
            result_lines.append(
                f"• {row['name']} (SKU: {row['sku']}) | "
                f"Store: {row['store_id']} | "
                f"Stock: {int(row['quantity_on_hand'])} units | "
                f"Reorder at: {int(row['reorder_point'])} | "
                f"Status: {row['status']} | "
                f"Price: ${safe_float(row['unit_price']):.2f}"
            )

        return "\n".join(result_lines)


class GetProductInfoInput(BaseModel):
    """Input schema for product info tool."""
    product_id: str = Field(..., description="Product ID to look up")
    include_sales: bool = Field(False, description="Include recent sales data")


class GetProductInfoTool(BaseTool):
    """Get detailed information about a specific product."""

    name: str = "get_product_info"
    description: str = (
        "Get detailed information about a specific product including "
        "name, SKU, category, pricing, and optionally recent sales performance."
    )
    args_schema: Type[BaseModel] = GetProductInfoInput

    def _run(self, product_id: str, include_sales: bool = False) -> str:
        from google.cloud.bigquery import ScalarQueryParameter
        bq = get_bigquery_service()

        query = f"""
        SELECT * FROM `{bq.full_table_name('products')}`
        WHERE product_id = @product_id
        """
        params = [ScalarQueryParameter("product_id", "STRING", product_id)]
        df = bq.run_query(query, params=params)

        if df.empty:
            return f"Product '{product_id}' not found."

        row = df.iloc[0]
        result = (
            f"Product: {row['name']}\n"
            f"  SKU: {row['sku']}\n"
            f"  Category: {row['category']}\n"
            f"  Brand: {row.get('brand', 'N/A')}\n"
            f"  Unit Cost: ${safe_float(row['unit_cost']):.2f}\n"
            f"  Unit Price: ${safe_float(row['unit_price']):.2f}\n"
            f"  Margin: {((safe_float(row['unit_price']) - safe_float(row['unit_cost'])) / safe_float(row['unit_price']) * 100):.1f}%\n"
        )

        if include_sales:
            sales_query = f"""
            SELECT
                SUM(quantity) as total_units,
                SUM(total_amount) as total_revenue,
                AVG(quantity) as avg_daily_units,
                COUNT(DISTINCT DATE(sale_date)) as days_sold
            FROM `{bq.full_table_name('sales')}`
            WHERE product_id = @product_id
                AND sale_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
            """
            sales_df = bq.run_query(sales_query, params=params)
            if not sales_df.empty:
                srow = sales_df.iloc[0]
                result += (
                    f"\n  Last 30 Days:\n"
                    f"    Units Sold: {int(srow['total_units'])}\n"
                    f"    Revenue: ${safe_float(srow['total_revenue']):,.2f}\n"
                    f"    Avg Daily: {safe_float(srow['avg_daily_units']):.1f} units\n"
                    f"    Days Active: {int(srow['days_sold'])}\n"
                )

        return result


class InventorySummaryInput(BaseModel):
    """Input for inventory summary."""
    store_id: Optional[str] = Field(None, description="Optional store filter")


class InventorySummaryTool(BaseTool):
    """Get a summary of inventory status across all products."""

    name: str = "get_inventory_summary"
    description: str = (
        "Get an aggregate summary of inventory: total products, counts by status "
        "(in stock, low stock, out of stock, overstocked), and total inventory value."
    )
    args_schema: Type[BaseModel] = InventorySummaryInput

    def _run(self, store_id: Optional[str] = None) -> str:
        service = InventoryService()
        summary = service.get_inventory_summary(store_id)

        return (
            f"Inventory Summary{' (Store: ' + store_id + ')' if store_id else ''}:\n"
            f"  Total Products: {summary.total_products}\n"
            f"  In Stock: {summary.in_stock}\n"
            f"  Low Stock: {summary.low_stock}\n"
            f"  Out of Stock: {summary.out_of_stock}\n"
            f"  Overstocked: {summary.overstocked}\n"
            f"  Total Inventory Value: ${summary.total_inventory_value:,.2f}\n"
            f"  Stock Health: {(summary.in_stock / max(summary.total_products, 1) * 100):.1f}%"
        )


def get_inventory_tools() -> list[BaseTool]:
    """Return all inventory-related tools."""
    return [
        QueryInventoryTool(),
        GetProductInfoTool(),
        InventorySummaryTool(),
    ]