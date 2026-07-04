import random
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd
from google.cloud import bigquery

from app.config import get_settings
from app.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

CATEGORIES = ["electronics", "clothing", "grocery", "home_garden", "sports", "beauty"]
STORES = ["warehouse-1", "store-nyc-01", "store-la-02", "store-chi-03"]
CHANNELS = ["in_store", "online", "mobile"]

PRODUCTS_TEMPLATES = [
    ("Wireless Earbuds Pro", "electronics", "TechBrand", 25.0, 79.99),
    ("4K HDMI Cable 6ft", "electronics", "CableCo", 3.5, 14.99),
    ("Organic Cotton T-Shirt", "clothing", "EcoWear", 8.0, 29.99),
    ("Denim Jeans Slim Fit", "clothing", "DenimCo", 18.0, 59.99),
    ("Arabica Coffee Beans 1lb", "grocery", "BeanSource", 6.0, 16.99),
    ("Almond Butter Organic", "grocery", "NutButters", 4.5, 12.99),
    ("Garden Hose 50ft", "home_garden", "GardenPro", 12.0, 34.99),
    ("Ceramic Plant Pot Set", "home_garden", "PotteryCo", 8.0, 24.99),
    ("Yoga Mat Premium 6mm", "sports", "FlexFit", 10.0, 39.99),
    ("Running Shoes Air", "sports", "SprintMax", 35.0, 99.99),
    ("Hydrating Face Serum", "beauty", "GlowLab", 5.0, 32.99),
    ("Bamboo Toothbrush 4pk", "beauty", "EcoSmile", 2.0, 9.99),
]

def generate_data():
    settings = get_settings()
    logger.info("generating_seed_data")
    
    products = []
    inventory = []
    sales = []
    
    # Generate Products
    for i, (name, cat, brand, cost, price) in enumerate(PRODUCTS_TEMPLATES):
        pid = f"PROD-{1000 + i}"
        sku = f"SKU-{cat[:3].upper()}-{1000 + i}"
        products.append({
            "product_id": pid,
            "sku": sku,
            "name": name,
            "category": cat,
            "brand": brand,
            "unit_cost": cost,
            "unit_price": price,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        
        # Generate Inventory for each store
        for store in STORES:
            qty = random.randint(0, 200)
            reorder_pt = random.randint(20, 50)
            inventory.append({
                "inventory_id": str(uuid.uuid4()),
                "product_id": pid,
                "store_id": store,
                "quantity_on_hand": qty,
                "quantity_reserved": random.randint(0, max(1, qty // 4)),
                "reorder_point": reorder_pt,
                "reorder_quantity": reorder_pt * 2,
                "warehouse_location": f"Aisle-{random.randint(1, 20)}",
                "last_restocked": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            
            # Generate 180 days of sales data
            base_demand = random.uniform(2, 15) # avg daily demand
            for day_offset in range(180):
                sale_date = datetime.now(timezone.utc) - timedelta(days=day_offset)
                
                # Add seasonality (higher on weekends)
                dow = sale_date.weekday()
                if dow >= 5: # Weekend
                    multiplier = random.uniform(1.2, 1.5)
                else:
                    multiplier = random.uniform(0.7, 1.1)
                    
                # Add slight upward trend
                trend = 1 + (180 - day_offset) * 0.001
                
                qty_sold = max(0, int(random.gauss(base_demand * multiplier * trend, base_demand * 0.3)))
                
                if qty_sold > 0:
                    sales.append({
                        "sale_id": str(uuid.uuid4()),
                        "product_id": pid,
                        "store_id": store,
                        "quantity": qty_sold,
                        "unit_price": price * random.uniform(0.95, 1.05), # slight price variance
                        "total_amount": qty_sold * price * random.uniform(0.95, 1.05),
                        "sale_date": sale_date.isoformat(),
                        "customer_id": f"CUST-{random.randint(1000, 9999)}",
                        "channel": random.choices(CHANNELS, weights=[0.6, 0.3, 0.1])[0],
                    })

    logger.info(
        "data_generated",
        products=len(products),
        inventory_records=len(inventory),
        sales_records=len(sales),
    )
    
    # Load into BigQuery
    client = bigquery.Client(project=settings.gcp_project_id)
    dataset = settings.gcp_bigquery_dataset
    
    for table_name, data in [("products", products), ("inventory", inventory), ("sales", sales)]:
        df = pd.DataFrame(data)
        table_ref = f"{settings.gcp_project_id}.{dataset}.{table_name}"
        
        logger.info(f"loading_{table_name}", rows=len(df))
        
        job = client.load_table_from_dataframe(
            df, table_ref, 
            job_config=bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        )
        job.result(timeout=300)
        logger.info(f"{table_name}_loaded_successfully", output_rows=job.output_rows)

if __name__ == "__main__":
    generate_data()