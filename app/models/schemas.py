from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    ForecastMethod,
    InsightType,
    InventoryStatus,
    ProductCategory,
    ReportStatus,
    ReportType,
)


# ── Product Schemas ──────────────────────────────────────────────

class ProductBase(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50, description="Stock Keeping Unit")
    name: str = Field(..., min_length=1, max_length=200)
    category: ProductCategory
    brand: str = Field(default="", max_length=100)
    unit_cost: float = Field(..., ge=0)
    unit_price: float = Field(..., ge=0)
    supplier_id: str = Field(default="", max_length=50)


class ProductCreate(ProductBase):
    pass


class ProductResponse(ProductBase):
    product_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Inventory Schemas ────────────────────────────────────────────

class InventoryBase(BaseModel):
    product_id: str
    store_id: str = Field(default="warehouse-1", max_length=50)
    quantity_on_hand: int = Field(..., ge=0)
    quantity_reserved: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=20, ge=0)
    reorder_quantity: int = Field(default=100, ge=0)
    warehouse_location: str = Field(default="", max_length=50)


class InventoryUpdate(BaseModel):
    quantity_on_hand: Optional[int] = Field(None, ge=0)
    quantity_reserved: Optional[int] = Field(None, ge=0)
    reorder_point: Optional[int] = Field(None, ge=0)
    reorder_quantity: Optional[int] = Field(None, ge=0)


class InventoryResponse(InventoryBase):
    inventory_id: str
    status: InventoryStatus
    last_restocked: Optional[datetime] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventorySummary(BaseModel):
    total_products: int
    in_stock: int
    low_stock: int
    out_of_stock: int
    overstocked: int
    total_inventory_value: float
    store_id: Optional[str] = None


# ── Sales Schemas ────────────────────────────────────────────────

class SalesRecord(BaseModel):
    sale_id: str
    product_id: str
    store_id: str
    quantity: int = Field(..., ge=1)
    unit_price: float = Field(..., ge=0)
    total_amount: float
    sale_date: datetime
    customer_id: Optional[str] = None
    channel: str = Field(default="in_store", pattern="^(in_store|online|mobile)$")


class SalesAggregation(BaseModel):
    product_id: str
    product_name: str
    category: ProductCategory
    total_quantity: int
    total_revenue: float
    avg_daily_quantity: float
    period_start: datetime
    period_end: datetime


# ── Forecasting Schemas ──────────────────────────────────────────

class ForecastRequest(BaseModel):
    product_id: str
    method: ForecastMethod = ForecastMethod.AI_FORECAST
    horizon_days: int = Field(default=30, ge=1, le=365)
    confidence_interval: float = Field(default=0.95, ge=0.5, le=0.999)
    include_seasonality: bool = True


class ForecastPoint(BaseModel):
    date: datetime
    predicted_demand: float = Field(..., ge=0)
    lower_bound: float
    upper_bound: float


class ForecastResponse(BaseModel):
    forecast_id: str
    product_id: str
    product_name: str
    method: ForecastMethod
    horizon_days: int
    confidence_interval: float
    historical_avg_daily: float
    predicted_avg_daily: float
    predicted_total: float
    trend_direction: str = Field(pattern="^(increasing|decreasing|stable)$")
    trend_percentage: float
    points: list[ForecastPoint]
    generated_at: datetime
    model_config = {"from_attributes": True}


# ── Report Schemas ───────────────────────────────────────────────

class ReportRequest(BaseModel):
    report_type: ReportType
    title: str = Field(..., min_length=1, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    format: str = Field(default="json", pattern="^(json|csv)$")


class ReportResponse(BaseModel):
    report_id: str
    report_type: ReportType
    title: str
    status: ReportStatus
    content: Optional[dict[str, Any]] = None
    summary: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Customer Insight Schemas ─────────────────────────────────────

class CustomerInsight(BaseModel):
    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    product_ids: list[str] = Field(default_factory=list)
    category: Optional[ProductCategory] = None
    metric_value: Optional[float] = None
    metric_name: Optional[str] = None
    recommendation: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InsightBatch(BaseModel):
    insights: list[CustomerInsight]
    total_count: int
    generated_at: datetime


# ── Natural Language Chat Schemas ────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tools_used: list[str] = Field(default_factory=list)
    data: Optional[dict[str, Any]] = None
    intermediate_steps: Optional[list[dict[str, Any]]] = None


# ── Unstructured Report Extraction ───────────────────────────────

class UnstructuredReport(BaseModel):
    raw_text: str = Field(..., min_length=10)
    source: str = Field(default="manual_input", max_length=100)
    report_date: Optional[datetime] = None


class ExtractedData(BaseModel):
    products_mentioned: list[str] = Field(default_factory=list)
    sales_figures: list[dict[str, Any]] = Field(default_factory=list)
    inventory_updates: list[dict[str, Any]] = Field(default_factory=list)
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    action_items: list[str] = Field(default_factory=list)
    sentiment: str = Field(default="neutral", pattern="^(positive|negative|neutral)$")
    summary: str = ""


# ── Reorder Point Schemas ────────────────────────────────────────

class ReorderPointRequest(BaseModel):
    product_id: str
    lead_time_days: int = Field(default=7, ge=1, le=90)
    service_level: float = Field(default=0.95, ge=0.5, le=0.999)
    review_period_days: int = Field(default=1, ge=1, le=30)


class ReorderPointResponse(BaseModel):
    product_id: str
    product_name: str
    current_reorder_point: int
    recommended_reorder_point: int
    recommended_order_quantity: int
    safety_stock: int
    avg_daily_demand: float
    demand_std_dev: float
    lead_time_days: int
    service_level: float
    reasoning: str


# ── Generic Response Wrappers ────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    environment: str
    uptime_seconds: float
    checks: dict[str, Any]


class ErrorResponse(BaseModel):
    error: dict[str, Any]