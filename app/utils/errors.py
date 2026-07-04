from typing import Any, Optional


class RetailAgentError(Exception):
    """Base exception for all application errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ConfigurationError(RetailAgentError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="CONFIGURATION_ERROR",
            status_code=500,
            details=details,
        )


class BigQueryError(RetailAgentError):
    """Raised when BigQuery operations fail."""

    def __init__(self, message: str, query: str = "", details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="BIGQUERY_ERROR",
            status_code=502,
            details={**(details or {}), "query": query[:500]} if query else details,
        )


class OpenAIError(RetailAgentError):
    """Raised when OpenAI API calls fail."""

    def __init__(self, message: str, model: str = "", details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="OPENAI_ERROR",
            status_code=502,
            details={**(details or {}), "model": model} if model else details,
        )


class AgentExecutionError(RetailAgentError):
    """Raised when the LangChain agent fails to complete."""

    def __init__(self, message: str, iterations: int = 0, details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="AGENT_EXECUTION_ERROR",
            status_code=502,
            details={**(details or {}), "iterations": iterations},
        )


class ForecastingError(RetailAgentError):
    """Raised when demand forecasting fails."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="FORECASTING_ERROR",
            status_code=422,
            details=details,
        )


class ValidationError(RetailAgentError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str = "", details: Optional[dict] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details={**(details or {}), "field": field} if field else details,
        )


class NotFoundError(RetailAgentError):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} with id '{resource_id}' not found",
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "id": resource_id},
        )