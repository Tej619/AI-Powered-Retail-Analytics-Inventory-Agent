from typing import Type

from langchain.pydantic_v1 import BaseModel, Field
from langchain_core.tools import BaseTool

from app.services.insight_service import InsightService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ExtractInsightsInput(BaseModel):
    """Input for insight extraction."""
    days: int = Field(30, description="Number of days of data to analyze", ge=1, le=365)
    limit: int = Field(5, description="Maximum number of insights", ge=1, le=20)


class ExtractInsightsTool(BaseTool):
    """Generate AI-powered customer insights from retail data."""

    name: str = "extract_insights"
    description: str = (
        "Analyze recent retail data to generate AI-powered customer and business insights. "
        "Identifies demand spikes/drops, stockout risks, seasonal patterns, "
        "pricing opportunities, and trend changes. Returns actionable insights "
        "with confidence scores and recommendations."
    )
    args_schema: Type[BaseModel] = ExtractInsightsInput

    def _run(self, days: int = 30, limit: int = 5) -> str:
        try:
            service = InsightService()
            batch = service.generate_insights(days=days, limit=limit)

            if not batch.insights:
                return f"No significant insights found in the last {days} days."

            result = f"AI-Generated Insights (last {days} days):\n\n"
            for i, insight in enumerate(batch.insights, 1):
                confidence_bar = "█" * int(insight.confidence * 10) + "░" * (10 - int(insight.confidence * 10))
                result += (
                    f"{i}. [{insight.insight_type.value.upper()}] {insight.title}\n"
                    f"   {insight.description}\n"
                    f"   Confidence: [{confidence_bar}] {insight.confidence:.0%}\n"
                )
                if insight.metric_name and insight.metric_value is not None:
                    result += f"   Metric: {insight.metric_name} = {insight.metric_value}\n"
                if insight.recommendation:
                    result += f"   → {insight.recommendation}\n"
                result += "\n"

            return result

        except Exception as e:
            logger.error("insight_tool_failed", error=str(e))
            return f"Failed to generate insights: {str(e)}"


class ExtractFromReportInput(BaseModel):
    """Input for unstructured report extraction."""
    report_text: str = Field(
        ...,
        description="The raw text of the retail report to extract data from",
    )
    source: str = Field("manual_input", description="Source of the report (e.g., email, pdf, meeting_notes)")


class ExtractFromReportTool(BaseTool):
    """Extract structured data from unstructured retail reports."""

    name: str = "extract_from_unstructured_report"
    description: str = (
        "Extract structured data from unstructured retail reports, emails, "
        "or notes. Identifies products mentioned, sales figures, inventory "
        "updates, key metrics, action items, and overall sentiment. "
        "Use this when a user pastes report text and wants it analyzed."
    )
    args_schema: Type[BaseModel] = ExtractFromReportInput

    def _run(self, report_text: str, source: str = "manual_input") -> str:
        try:
            from app.models.schemas import UnstructuredReport
            service = InsightService()

            report = UnstructuredReport(raw_text=report_text, source=source)
            extracted = service.extract_from_unstructured(report)

            result = "Extracted Data:\n\n"

            if extracted.products_mentioned:
                result += f"Products Mentioned: {', '.join(extracted.products_mentioned)}\n\n"

            if extracted.key_metrics:
                result += "Key Metrics:\n"
                for k, v in extracted.key_metrics.items():
                    if v is not None:
                        if isinstance(v, float):
                            result += f"  {k.replace('_', ' ').title()}: {v:,.2f}\n"
                        else:
                            result += f"  {k.replace('_', ' ').title()}: {v}\n"
                result += "\n"

            if extracted.sales_figures:
                result += "Sales Figures:\n"
                for sf in extracted.sales_figures:
                    line = f"  • {sf.get('product', 'Unknown')}"
                    if sf.get("quantity"):
                        line += f" | Qty: {sf['quantity']}"
                    if sf.get("revenue"):
                        line += f" | Revenue: ${sf['revenue']:,.2f}"
                    if sf.get("period"):
                        line += f" | Period: {sf['period']}"
                    result += line + "\n"
                result += "\n"

            if extracted.inventory_updates:
                result += "Inventory Updates:\n"
                for iu in extracted.inventory_updates:
                    line = f"  • {iu.get('product', 'Unknown')}"
                    if iu.get("current_stock") is not None:
                        line += f" | Stock: {iu['current_stock']}"
                    if iu.get("status"):
                        line += f" | Status: {iu['status']}"
                    result += line + "\n"
                result += "\n"

            if extracted.action_items:
                result += "Action Items:\n"
                for ai in extracted.action_items:
                    result += f"  □ {ai}\n"
                result += "\n"

            result += f"Sentiment: {extracted.sentiment.upper()}\n"
            result += f"\nSummary: {extracted.summary}\n"

            return result

        except Exception as e:
            logger.error("extraction_tool_failed", error=str(e))
            return f"Failed to extract data: {str(e)}"


def get_insight_tools() -> list[BaseTool]:
    return [ExtractInsightsTool(), ExtractFromReportTool()]