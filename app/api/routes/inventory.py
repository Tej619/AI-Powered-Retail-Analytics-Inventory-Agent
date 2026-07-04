from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.models.schemas import (
    InventoryResponse,
    InventorySummary,
    ReorderPointRequest,
    ReorderPointResponse,
)
from app.services.inventory_service import InventoryService

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])

@router.get("/summary", response_model=InventorySummary)
def get_inventory_summary(store_id: Optional[str] = Query(None)):
    """Get aggregate inventory status summary."""
    service = InventoryService()
    return service.get_inventory_summary(store_id)

@router.get("/product/{product_id}", response_model=list[InventoryResponse])
def get_product_inventory(product_id: str):
    """Get inventory levels for a specific product across all stores."""
    service = InventoryService()
    return service.get_product_inventory(product_id)

@router.get("/alerts/low-stock")
def get_low_stock_alerts(threshold: float = Query(1.0, ge=0.1, le=5.0)):
    """Get items currently at or below their reorder point."""
    service = InventoryService()
    df = service.get_low_stock_items(threshold)
    return {"items": df.to_dict(orient="records"), "count": len(df)}

@router.post("/reorder-point", response_model=ReorderPointResponse)
def calculate_reorder_point(request: ReorderPointRequest):
    """Calculate statistically optimal reorder point and safety stock."""
    service = InventoryService()
    return service.calculate_reorder_point(request)