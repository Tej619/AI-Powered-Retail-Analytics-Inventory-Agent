-- ============================================
-- BigQuery Schema for Retail Analytics Agent
-- ============================================

-- Products Table
CREATE OR REPLACE TABLE `retail_analytics.products` (
    product_id STRING NOT OPTIONS(description="Unique product identifier"),
    sku STRING NOT NULL OPTIONS(description="Stock Keeping Unit"),
    name STRING NOT NULL OPTIONS(description="Product name"),
    category STRING OPTIONS(description="Product category"),
    brand STRING OPTIONS(description="Brand name"),
    unit_cost FLOAT64 OPTIONS(description="Cost per unit"),
    unit_price FLOAT64 OPTIONS(description="Selling price per unit"),
    created_at TIMESTAMP NOT NULL OPTIONS(description="Record creation time"),
    updated_at TIMESTAMP NOT NULL OPTIONS(description="Last update time")
) PARTITION BY DATE(created_at)
CLUSTER BY category;

-- Inventory Table
CREATE OR REPLACE TABLE `retail_analytics.inventory` (
    inventory_id STRING NOT NULL OPTIONS(description="Unique inventory record ID"),
    product_id STRING NOT NULL OPTIONS(description="Reference to product"),
    store_id STRING NOT NULL OPTIONS(description="Store or warehouse ID"),
    quantity_on_hand INT64 NOT NULL OPTIONS(description="Current available quantity"),
    quantity_reserved INT64 OPTIONS(description="Quantity reserved for orders"),
    reorder_point INT64 OPTIONS(description="Threshold to trigger reorder"),
    reorder_quantity INT64 OPTIONS(description="Standard order quantity"),
    warehouse_location STRING OPTIONS(description="Physical location in warehouse"),
    last_restocked TIMESTAMP OPTIONS(description="Last restock date"),
    updated_at TIMESTAMP NOT NULL OPTIONS(description="Last update time")
) CLUSTER BY store_id, product_id;

-- Sales Table
CREATE OR REPLACE TABLE `retail_analytics.sales` (
    sale_id STRING NOT NULL OPTIONS(description="Unique sale transaction ID"),
    product_id STRING NOT NULL OPTIONS(description="Product sold"),
    store_id STRING NOT NULL OPTIONS(description="Store where sale occurred"),
    quantity INT64 NOT NULL OPTIONS(description="Quantity sold"),
    unit_price FLOAT64 NOT NULL OPTIONS(description="Price at time of sale"),
    total_amount FLOAT64 NOT NULL OPTIONS(description="Total sale amount"),
    sale_date TIMESTAMP NOT NULL OPTIONS(description="Time of sale"),
    customer_id STRING OPTIONS(description="Customer identifier"),
    channel STRING OPTIONS(description="Sales channel: in_store, online, mobile")
) PARTITION BY DATE(sale_date)
CLUSTER BY product_id, store_id;

-- Forecasts Table
CREATE OR REPLACE TABLE `retail_analytics.forecasts` (
    forecast_id STRING NOT NULL OPTIONS(description="Unique forecast ID"),
    product_id STRING NOT NULL OPTIONS(description="Product being forecasted"),
    method STRING OPTIONS(description="Forecasting method used"),
    horizon_days INT64 OPTIONS(description="Number of days forecasted"),
    confidence_interval FLOAT64 OPTIONS(description="Statistical confidence level"),
    forecast_date TIMESTAMP OPTIONS(description="Start date of forecast"),
    predicted_total FLOAT64 OPTIONS(description="Total predicted demand"),
    trend_direction STRING OPTIONS(description="increasing, decreasing, or stable"),
    reasoning STRING OPTIONS(description="AI or statistical reasoning"),
    points_json STRING OPTIONS(description="JSON array of daily forecast points"),
    created_at TIMESTAMP NOT NULL OPTIONS(description="Forecast generation time")
) PARTITION BY DATE(created_at);

-- Reports Table
CREATE OR REPLACE TABLE `retail_analytics.reports` (
    report_id STRING NOT NULL OPTIONS(description="Unique report ID"),
    report_type STRING NOT NULL OPTIONS(description="Type of report generated"),
    title STRING NOT NULL OPTIONS(description="Report title"),
    status STRING NOT NULL OPTIONS(description="pending, generating, completed, failed"),
    content_json STRING OPTIONS(description="JSON payload of report data"),
    summary STRING OPTIONS(description="AI-generated executive summary"),
    error_message STRING OPTIONS(description="Error message if failed"),
    parameters STRING OPTIONS(description="Input parameters used"),
    created_at TIMESTAMP NOT NULL OPTIONS(description="Report request time"),
    completed_at TIMESTAMP OPTIONS(description="Report completion time")
) PARTITION BY DATE(created_at);

-- Customer Insights Table
CREATE OR REPLACE TABLE `retail_analytics.customer_insights` (
    insight_id STRING NOT NULL OPTIONS(description="Unique insight ID"),
    insight_type STRING NOT NULL OPTIONS(description="Type of insight"),
    title STRING NOT NULL OPTIONS(description="Insight title"),
    description STRING NOT NULL OPTIONS(description="Detailed description"),
    confidence FLOAT64 OPTIONS(description="AI confidence score 0-1"),
    product_ids STRING OPTIONS(description="JSON array of related product IDs"),
    category STRING OPTIONS(description="Related category"),
    metric_value FLOAT64 OPTIONS(description="Key metric value"),
    metric_name STRING OPTIONS(description="Name of the metric"),
    recommendation STRING OPTIONS(description="Actionable recommendation"),
    created_at TIMESTAMP NOT NULL OPTIONS(description="Insight generation time")
) PARTITION BY DATE(created_at);