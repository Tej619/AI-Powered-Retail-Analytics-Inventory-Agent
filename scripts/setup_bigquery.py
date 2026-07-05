import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.cloud import bigquery

from app.config import get_settings
from app.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

def setup_bigquery():
    settings = get_settings()
    client = bigquery.Client(project=settings.gcp_project_id)
    dataset_id = f"{settings.gcp_project_id}.{settings.gcp_bigquery_dataset}"
    
    logger.info("starting_bigquery_setup", dataset=dataset_id)

    # 1. Create Dataset
    try:
        dataset = bigquery.Dataset(dataset_id)
        dataset.location = settings.gcp_region
        dataset.description = "Retail Analytics and Inventory Agent Dataset"
        client.create_dataset(dataset, timeout=30)
        logger.info("dataset_created", dataset=dataset_id)
    except Exception as e:
        if "Already Exists" in str(e):
            logger.info("dataset_already_exists", dataset=dataset_id)
        else:
            logger.error("dataset_creation_failed", error=str(e))
            sys.exit(1)

    # 2. Read and execute schema SQL
    try:
        with open("sql/schema.sql", "r") as f:
            sql_script = f.read()
            
        # Split by CREATE OR REPLACE TABLE to run individually
        statements = [s.strip() for s in sql_script.split("CREATE OR REPLACE TABLE") if s.strip()]
        
        for stmt in statements:
            full_sql = f"CREATE OR REPLACE TABLE {stmt}"
            try:
                job = client.query(full_sql)
                job.result(timeout=60)
                # Extract table name for logging
                table_name = stmt.split("`")[1] if "`" in stmt else "unknown"
                logger.info("table_created_or_updated", table=table_name)
            except Exception as e:
                logger.error("table_creation_failed", error=str(e), sql=full_sql[:200])
                
        logger.info("bigquery_setup_completed_successfully")
        
    except FileNotFoundError:
        logger.error("schema_sql_not_found", path="sql/schema.sql")
        sys.exit(1)

if __name__ == "__main__":
    setup_bigquery()