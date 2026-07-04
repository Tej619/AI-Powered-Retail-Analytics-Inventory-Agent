from enum import Enum


class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    GROCERY = "grocery"
    HOME_GARDEN = "home_garden"
    SPORTS = "sports"
    BEAUTY = "beauty"
    TOYS = "toys"
    AUTOMOTIVE = "automotive"
    HEALTH = "health"
    OTHER = "other"


class InventoryStatus(str, Enum):
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    OVERSTOCKED = "overstocked"
    DISCONTINUED = "discontinued"


class ForecastMethod(str, Enum):
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    AI_FORECAST = "ai_forecast"
    SEASONAL_DECOMPOSITION = "seasonal_decomposition"


class ReportType(str, Enum):
    INVENTORY_SUMMARY = "inventory_summary"
    SALES_PERFORMANCE = "sales_performance"
    DEMAND_FORECAST = "demand_forecast"
    CUSTOMER_INSIGHTS = "customer_insights"
    REPLENISHMENT = "replenishment"
    ANOMALY_DETECTION = "anomaly_detection"


class ReportStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class InsightType(str, Enum):
    DEMAND_SPIKE = "demand_spike"
    DEMAND_DROP = "demand_drop"
    SEASONAL_PATTERN = "seasonal_pattern"
    STOCKOUT_RISK = "stockout_risk"
    OVERSTOCK_RISK = "overstock_risk"
    PRICING_OPPORTUNITY = "pricing_opportunity"
    CUSTOMER_SEGMENT = "customer_segment"
    TREND_CHANGE = "trend_change"


class AgentToolName(str, Enum):
    QUERY_INVENTORY = "query_inventory"
    QUERY_SALES = "query_sales"
    GET_PRODUCT_INFO = "get_product_info"
    GENERATE_FORECAST = "generate_forecast"
    GET_FORECAST = "get_forecast"
    CREATE_REPORT = "create_report"
    GET_REPORT = "get_report"
    EXTRACT_INSIGHTS = "extract_insights"
    CALCULATE_REORDER_POINT = "calculate_reorder_point"
    ANALYZE_TRENDS = "analyze_trends"