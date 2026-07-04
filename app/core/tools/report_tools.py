from typing import Type

from langchain.pydantic_v1 import BaseModel, Field
from langchain_core.tools import BaseTool

from app.models.enums import ReportType
from app.models.schemas import ReportRequest
from app.services.report_service import ReportService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CreateReportInput(BaseModel):
    """Input for report creation."""
    report_type: str = Field(
        ...,
        description=(
            "Type of report: inventory_summary, sales_performance, "
            "demand_forecast, customer_insights, replenishment, anomaly_detection"
        ),
    )
    title: str = Field(..., description="Report title")
    days: int = Field(30, description="Time period in days for the report", ge=1, le=365)
    category: str = Field("", description="Optional category filter")


class CreateReportTool(BaseTool):
    """Generate an automated retail analytics report."""

    name: str = "create_report"
    description: str = (
        "Generate a comprehensive retail analytics report with AI-generated narrative. "
        "Available types: inventory_summary (stock levels & status), "
        "sales_performance (revenue, units, trends), "
        "demand_forecast (recent forecasts summary), "
        "customer_insights (AI-generated insights), "
        "replenishment (items needing reorder), "
        "anomaly_detection (statistical outliers). "
        "Returns a report ID and executive summary."
    )
    args_schema: Type[BaseModel] = CreateReportInput

    def _run(
        self,
        report_type: str,
        title: str,
        days: int = 30,
        category: str = "",
    ) -> str:
        try:
            service = ReportService()
            parameters = {"days": days}
            if category:
                parameters["category"] = category

            request = ReportRequest(
                report_type=ReportType(report_type),
                title=title,
                parameters=parameters,
            )

            report = service.create_report(request)

            if report.status.value == "failed":
                return f"Report generation failed: {report.error_message}"

            result = (
                f"Report Generated: {report.title}\n"
                f"  ID: {report.report_id}\n"
                f"  Type: {report.report_type.value}\n"
                f"  Status: {report.status.value}\n\n"
                f"EXECUTIVE SUMMARY:\n{report.summary}\n"
            )

            # Add key data points based on type
            if report.content:
                if "summary" in report.content:
                    s = report.content["summary"]
                    result += f"\nKEY METRICS:\n"
                    if "total_products" in s:
                        result += f"  Total Products: {s['total_products']}\n"
                    if "out_of_stock_count" in s:
                        result += f"  Out of Stock: {s['out_of_stock_count']}\n"
                    if "low_stock_count" in s:
                        result += f"  Low Stock: {s['low_stock_count']}\n"
                    if "total_inventory_value" in s:
                        result += f"  Inventory Value: ${s['total_inventory_value']:,.2f}\n"
                    if "total_revenue" in s:
                        result += f"  Total Revenue: ${s['total_revenue']:,.2f}\n"
                    if "total_units_sold" in s:
                        result += f"  Units Sold: {s['total_units_sold']:,}\n"

            return result

        except Exception as e:
            logger.error("report_tool_failed", error=str(e))
            return f"Failed to generate report: {str(e)}"


class GetReportInput(BaseModel):
    report_id: str = Field(..., description="ID of the report to retrieve")


class GetReportTool(BaseTool):
    """Retrieve a previously generated report."""

    name: str = "get_report"
    description: str = "Retrieve a previously generated report by its ID."
    args_schema: Type[BaseModel] = GetReportInput

    def _run(self, report_id: str) -> str:
        service = ReportService()
        report = service.get_report(report_id)

        if not report:
            return f"Report '{report_id}' not found."

        return (
            f"Report: {report.title}\n"
            f"  ID: {report.report_id}\n"
            f"  Type: {report.report_type.value}\n"
            f"  Status: {report.status.value}\n"
            f"  Created: {report.created_at}\n"
            f"  Summary: {report.summary or 'N/A'}\n"
        )


def get_report_tools() -> list[BaseTool]:
    return [CreateReportTool(), GetReportTool()]