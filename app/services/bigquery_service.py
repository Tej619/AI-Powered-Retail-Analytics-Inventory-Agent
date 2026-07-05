import json
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from google.cloud import bigquery
from google.cloud.bigquery import QueryJob, ScalarQueryParameter

from app.config import get_settings
from app.utils.errors import BigQueryError
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BigQueryService:
    """
    Singleton service for BigQuery operations.
    Manages connection, queries, and data loading.
    """

    _instance: Optional["BigQueryService"] = None
    _client: Optional[bigquery.Client] = None

    def __new__(cls) -> "BigQueryService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._client is not None:
            return

        settings = get_settings()
        try:
            client_kwargs: dict[str, Any] = {"project": settings.gcp_project_id}

            if settings.gcp_service_account_key_path:
                client_kwargs["credentials"] = (
                    settings.gcp_service_account_key_path
                )

            self._client = bigquery.Client(**client_kwargs)
            self._dataset_id = f"{settings.gcp_project_id}.{settings.gcp_bigquery_dataset}"
            logger.info("bigquery_client_initialized", dataset=self._dataset_id)

        except Exception as e:
            logger.error("bigquery_init_failed", error=str(e))
            raise BigQueryError(
                f"Failed to initialize BigQuery client: {e}",
                details={"project": settings.gcp_project_id},
            )

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            raise BigQueryError("BigQuery client not initialized")
        return self._client

    @property
    def dataset(self) -> bigquery.DatasetReference:
        return self.client.dataset(self._dataset_id.split(".")[-1])

    def full_table_name(self, table: str) -> str:
        return f"{self._dataset_id}.{table}"

    def ensure_dataset(self) -> None:
        """Create dataset if it doesn't exist."""
        try:
            self.client.get_dataset(self.dataset)
        except Exception:
            dataset = bigquery.Dataset(self.dataset)
            dataset.location = get_settings().gcp_region
            dataset.description = "Retail Analytics and Inventory Agent Dataset"
            self.client.create_dataset(dataset, timeout=30)
            logger.info("dataset_created", dataset=self._dataset_id)

    def run_query(
        self,
        query: str,
        params: Optional[list[ScalarQueryParameter]] = None,
        timeout: int = 60,
    ) -> pd.DataFrame:
        """
        Execute a SQL query and return results as a DataFrame.

        Args:
            query: SQL query string
            params: Optional query parameters for parameterized queries
            timeout: Query timeout in seconds

        Returns:
            pandas DataFrame with query results

        Raises:
            BigQueryError: If query execution fails
        """
        job: Optional[QueryJob] = None
        try:
            job_config = bigquery.QueryJobConfig(
                query_parameters=params or [],
                use_legacy_sql=False,
            )

            logger.debug(
                "executing_query",
                query=query[:500],
                params_count=len(params or []),
            )

            job = self.client.query(query, job_config=job_config)
            result = job.result(timeout=timeout)
            df = result.to_dataframe()

            duration_ms = None
            try:
                if hasattr(job, 'metadata') and job.metadata:
                    duration_ms = job.metadata.duration_ms
                elif hasattr(job, 'stats') and job.stats:
                    duration_ms = job.stats.get('query', {}).get('totalTimeMs')
            except Exception:
                pass

            logger.info(
                "query_completed",
                rows=len(df),
                bytes_processed=job.total_bytes_processed,
                duration_ms=duration_ms,
            )

            return df

        except Exception as e:
            logger.error(
                "query_failed",
                error=str(e),
                query=query[:500],
                job_id=job.job_id if job else None,
            )
            raise BigQueryError(
                f"Query execution failed: {e}",
                query=query,
                details={"job_id": job.job_id if job else None},
            )

    def insert_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        ignore_unknown: bool = True,
    ) -> int:
        """
        Insert rows into a BigQuery table.

        Args:
            table: Table name (without dataset prefix)
            rows: List of row dictionaries
            ignore_unknown: Skip columns not in schema

        Returns:
            Number of rows inserted
        """
        if not rows:
            return 0

        full_table = self.full_table_name(table)
        errors = []

        try:
            errors = self.client.insert_rows_json(
                full_table,
                rows,
                ignore_unknown_values=ignore_unknown,
            )

            if errors:
                logger.error("insert_errors", errors=errors, table=full_table)
                raise BigQueryError(
                    f"Insert failed with {len(errors)} errors",
                    details={"table": full_table, "errors": errors[:5]},
                )

            logger.info("rows_inserted", table=table, count=len(rows))
            return len(rows)

        except BigQueryError:
            raise
        except Exception as e:
            logger.error("insert_failed", error=str(e), table=full_table)
            raise BigQueryError(f"Failed to insert rows: {e}", details={"table": full_table})

    def insert_dataframe(
        self,
        table: str,
        df: pd.DataFrame,
        write_disposition: str = "WRITE_APPEND",
    ) -> None:
        """
        Load a DataFrame into a BigQuery table.

        Args:
            table: Target table name
            df: pandas DataFrame to load
            write_disposition: WRITE_APPEND, WRITE_TRUNCATE, or WRITE_EMPTY
        """
        if df.empty:
            return

        full_table = self.full_table_name(table)

        try:
            job_config = bigquery.LoadJobConfig(
                write_disposition=write_disposition,
                autodetect=True,
            )

            job = self.client.load_table_from_dataframe(df, full_table, job_config=job_config)
            job.result(timeout=120)

            logger.info(
                "dataframe_loaded",
                table=table,
                rows=len(df),
                output_rows=job.output_rows,
            )

        except Exception as e:
            logger.error("dataframe_load_failed", error=str(e), table=full_table)
            raise BigQueryError(f"Failed to load DataFrame: {e}", details={"table": full_table})

    def get_table_schema(self, table: str) -> list[bigquery.SchemaField]:
        """Retrieve the schema of a table."""
        full_table = self.full_table_name(table)
        table_ref = self.client.get_table(full_table)
        return table_ref.schema

    def table_exists(self, table: str) -> bool:
        """Check if a table exists."""
        try:
            self.client.get_table(self.full_table_name(table))
            return True
        except Exception:
            return False


# Module-level singleton accessor
def get_bigquery_service() -> BigQueryService:
    return BigQueryService()